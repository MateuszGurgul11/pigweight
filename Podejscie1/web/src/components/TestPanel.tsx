import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BackendError,
  predictFromBlob,
  type PredictResult,
} from '../lib/backendClient'
import { drawPrediction } from '../lib/drawOverlay'
import { verdictLabel, type Verdict } from '../lib/heuristic'
import type { UserSettings } from '../lib/settings'

type Props = { settings: UserSettings }

type TestResult = {
  id: number
  label: string
  thumbUrl: string
  result: PredictResult
  imgWidth: number
  imgHeight: number
}

type VideoState = {
  url: string
  name: string
}

let nextId = 0

function grabCanvasBlob(
  source: HTMLVideoElement | ImageBitmap,
  w: number,
  h: number,
): Promise<Blob> {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')!
  ctx.drawImage(source, 0, 0, w, h)
  return new Promise<Blob>((resolve, reject) =>
    c.toBlob(b => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/jpeg', 0.85),
  )
}

function thumbFromVideo(video: HTMLVideoElement): string {
  const c = document.createElement('canvas')
  const scale = 120 / Math.max(video.videoWidth, 1)
  c.width = Math.round(video.videoWidth * scale)
  c.height = Math.round(video.videoHeight * scale)
  const ctx = c.getContext('2d')!
  ctx.drawImage(video, 0, 0, c.width, c.height)
  return c.toDataURL('image/jpeg', 0.6)
}

export function TestPanel({ settings }: Props) {
  const [results, setResults] = useState<TestResult[]>([])
  const [selected, setSelected] = useState<TestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // Video state
  const [video, setVideo] = useState<VideoState | null>(null)
  const [playing, setPlaying] = useState(false)
  const [videoTime, setVideoTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)
  const [liveResult, setLiveResult] = useState<PredictResult | null>(null)
  const [autoInfer, setAutoInfer] = useState(true)
  const [confThreshold, setConfThreshold] = useState(0.10)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const settingsRef = useRef(settings)
  settingsRef.current = settings
  const inferringRef = useRef(false)
  const autoInferRef = useRef(autoInfer)
  autoInferRef.current = autoInfer
  const confRef = useRef(confThreshold)
  confRef.current = confThreshold

  const testSettings = useCallback((): UserSettings => ({
    ...settingsRef.current,
    confidenceThreshold: confRef.current,
  }), [])

  // -- Image processing --
  const processImageFile = useCallback(async (file: File) => {
    setError(null)
    setLoading(true)
    try {
      const bmp = await createImageBitmap(file)
      const blob = await grabCanvasBlob(bmp, bmp.width, bmp.height)
      const result = await predictFromBlob(blob, testSettings(), undefined, { smooth: false })
      const thumbUrl = URL.createObjectURL(file)
      const entry: TestResult = {
        id: nextId++,
        label: file.name,
        thumbUrl,
        result,
        imgWidth: bmp.width,
        imgHeight: bmp.height,
      }
      setResults(prev => [entry, ...prev])
      setSelected(entry)
      drawImageResult(entry)
    } catch (e) {
      setError(humanError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  // -- Draw an image-based result on canvas --
  const drawImageResult = useCallback((entry: TestResult) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const img = new Image()
    img.onload = () => {
      canvas.width = entry.imgWidth
      canvas.height = entry.imgHeight
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, entry.imgWidth, entry.imgHeight)
      drawPrediction(ctx, entry.result.mask, 'upload')
      drawMassLabel(ctx, entry.result)
    }
    img.src = entry.thumbUrl
  }, [])

  const selectEntry = useCallback((entry: TestResult) => {
    setSelected(entry)
    // If we're in video mode, don't redraw canvas (video owns it)
    if (!video) drawImageResult(entry)
    else drawImageResult(entry)
  }, [drawImageResult, video])

  // -- File handler (images + videos) --
  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files)
    for (const f of arr) {
      if (f.type.startsWith('video/')) {
        // Switch to video mode
        if (video?.url) URL.revokeObjectURL(video.url)
        const url = URL.createObjectURL(f)
        setVideo({ url, name: f.name })
        setLiveResult(null)
        setSelected(null)
        setPlaying(false)
        return
      }
      if (f.type.startsWith('image/')) {
        await processImageFile(f)
      }
    }
  }, [processImageFile, video])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  // -- Video: load metadata --
  useEffect(() => {
    const v = videoRef.current
    if (!v || !video) return
    v.src = video.url
    v.load()
    const onMeta = () => setVideoDuration(v.duration)
    const onTime = () => setVideoTime(v.currentTime)
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    v.addEventListener('loadedmetadata', onMeta)
    v.addEventListener('timeupdate', onTime)
    v.addEventListener('play', onPlay)
    v.addEventListener('pause', onPause)
    return () => {
      v.removeEventListener('loadedmetadata', onMeta)
      v.removeEventListener('timeupdate', onTime)
      v.removeEventListener('play', onPlay)
      v.removeEventListener('pause', onPause)
    }
  }, [video])

  // -- Video: RAF loop for drawing + inference --
  useEffect(() => {
    if (!video) return
    let stopped = false
    let frameCount = 0

    const loop = () => {
      if (stopped) return
      const v = videoRef.current
      const canvas = canvasRef.current
      if (!v || !canvas || v.readyState < 2) {
        requestAnimationFrame(loop)
        return
      }

      const w = v.videoWidth
      const h = v.videoHeight
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(v, 0, 0, w, h)

      // Draw live overlay if available
      if (liveResultRef.current) {
        drawPrediction(ctx, liveResultRef.current.mask, 'upload')
        drawMassLabel(ctx, liveResultRef.current)
      }

      // Inference every ~10 frames while playing
      frameCount++
      if (
        !v.paused &&
        autoInferRef.current &&
        !inferringRef.current &&
        frameCount % 10 === 0
      ) {
        inferringRef.current = true
        void (async () => {
          try {
            const blob = await grabCanvasBlob(v, w, h)
            const result = await predictFromBlob(blob, testSettings(), undefined, { smooth: false })
            if (!stopped) {
              setLiveResult(result)
              liveResultRef.current = result
            }
          } catch {
            // skip frame on error
          } finally {
            inferringRef.current = false
          }
        })()
      }

      requestAnimationFrame(loop)
    }

    requestAnimationFrame(loop)
    return () => { stopped = true }
  }, [video])

  const liveResultRef = useRef<PredictResult | null>(null)
  useEffect(() => { liveResultRef.current = liveResult }, [liveResult])

  // -- Video controls --
  const togglePlay = () => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) v.play().catch(() => undefined)
    else v.pause()
  }

  const stepFrame = (dir: number) => {
    const v = videoRef.current
    if (!v) return
    v.pause()
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + dir / 30))
  }

  const inferCurrentFrame = async () => {
    const v = videoRef.current
    if (!v || v.readyState < 2) return
    setLoading(true)
    setError(null)
    try {
      const w = v.videoWidth
      const h = v.videoHeight
      const blob = await grabCanvasBlob(v, w, h)
      const result = await predictFromBlob(blob, testSettings(), undefined, { smooth: false })
      setLiveResult(result)
      liveResultRef.current = result

      const thumb = thumbFromVideo(v)
      const entry: TestResult = {
        id: nextId++,
        label: `${video?.name ?? 'video'} @${v.currentTime.toFixed(2)}s`,
        thumbUrl: thumb,
        result,
        imgWidth: w,
        imgHeight: h,
      }
      setResults(prev => [entry, ...prev])
      setSelected(entry)
    } catch (e) {
      setError(humanError(e))
    } finally {
      setLoading(false)
    }
  }

  const closeVideo = () => {
    if (video?.url) URL.revokeObjectURL(video.url)
    setVideo(null)
    setLiveResult(null)
    liveResultRef.current = null
    setPlaying(false)
    setVideoTime(0)
    setVideoDuration(0)
  }

  // -- Summary stats --
  const summary = results.length > 0
    ? {
        avgMass: results.reduce((s, r) => s + r.result.massKg, 0) / results.length,
        avgTime: results.reduce((s, r) => s + r.result.elapsedMs, 0) / results.length,
        avgScore: results.reduce((s, r) => s + r.result.score, 0) / results.length,
        count: results.length,
      }
    : null

  const displayResult = video ? liveResult : selected?.result ?? null

  return (
    <div className="flex h-full text-zinc-100">
      {/* Left: canvas + controls */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Upload zone */}
        <div
          className={`shrink-0 border-b border-zinc-800 px-4 py-3 ${dragOver ? 'bg-emerald-950/40' : 'bg-zinc-900/50'}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <div className="flex items-center gap-3">
            <label className="flex-1">
              <input
                type="file"
                accept="image/*,video/*"
                multiple
                onChange={e => { if (e.target.files) void handleFiles(e.target.files) }}
                className="block w-full cursor-pointer rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 file:mr-2 file:rounded-lg file:border-0 file:bg-emerald-700 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
              />
            </label>
            {video && (
              <button
                type="button"
                onClick={closeVideo}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Zamknij wideo
              </button>
            )}
            {results.length > 0 && (
              <button
                type="button"
                onClick={() => { setResults([]); setSelected(null); setError(null) }}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Wyczysc
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-[11px] text-zinc-500">YOLO confidence:</span>
            <input
              type="range"
              min={0.01}
              max={0.5}
              step={0.01}
              value={confThreshold}
              onChange={e => setConfThreshold(Number(e.target.value))}
              className="w-28 accent-emerald-500 h-1"
            />
            <span className="font-mono text-xs text-zinc-300 w-10">{confThreshold.toFixed(2)}</span>
          </div>
          {loading && <p className="mt-1 text-xs text-emerald-400">Przetwarzam...</p>}
          {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
          {dragOver && <p className="mt-1 text-xs text-emerald-300">Upusc zdjecia lub wideo tutaj</p>}
        </div>

        {/* Canvas preview */}
        <div className="relative flex-1 min-h-0 bg-black flex items-center justify-center overflow-hidden">
          <canvas ref={canvasRef} className="max-h-full max-w-full object-contain" />
          <video ref={videoRef} className="hidden" playsInline muted loop />
          {!video && !selected && (
            <p className="absolute text-sm text-zinc-500">
              Wgraj zdjecie lub wideo aby rozpoczac testowanie
            </p>
          )}
        </div>

        {/* Video controls */}
        {video && (
          <div className="shrink-0 border-t border-zinc-800 bg-zinc-900 px-4 py-2">
            <div className="flex items-center gap-2 mb-2">
              <button type="button" onClick={() => stepFrame(-1)} className="rounded bg-zinc-800 px-2 py-1 text-xs hover:bg-zinc-700">
                -1 kl
              </button>
              <button type="button" onClick={togglePlay} className="rounded bg-emerald-800 px-4 py-1 text-xs font-medium hover:bg-emerald-700">
                {playing ? 'Pauza' : 'Odtwarzaj'}
              </button>
              <button type="button" onClick={() => stepFrame(1)} className="rounded bg-zinc-800 px-2 py-1 text-xs hover:bg-zinc-700">
                +1 kl
              </button>
              <div className="h-4 w-px bg-zinc-700" />
              <button
                type="button"
                onClick={() => void inferCurrentFrame()}
                disabled={loading}
                className="rounded bg-cyan-800 px-3 py-1 text-xs font-medium hover:bg-cyan-700 disabled:opacity-50"
              >
                Zapisz klatke
              </button>
              <div className="h-4 w-px bg-zinc-700" />
              <label className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoInfer}
                  onChange={e => setAutoInfer(e.target.checked)}
                  className="accent-emerald-500"
                />
                Auto-inferencja
              </label>
              <span className="ml-auto font-mono text-xs text-zinc-500">
                {formatTime(videoTime)} / {formatTime(videoDuration)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={videoDuration || 1}
              step={0.01}
              value={videoTime}
              onChange={e => {
                const v = videoRef.current
                if (v) v.currentTime = Number(e.target.value)
              }}
              className="w-full accent-emerald-500 h-1.5"
            />
            <p className="mt-1 text-[10px] text-zinc-600 truncate">{video.name}</p>
          </div>
        )}

        {/* Result bar */}
        {displayResult && <SelectedBar result={displayResult} />}
      </div>

      {/* Right sidebar */}
      <div className="w-[380px] shrink-0 border-l border-zinc-800 bg-zinc-900/60 overflow-y-auto">
        {/* Summary */}
        {summary && (
          <div className="border-b border-zinc-800 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-400 mb-2">
              Podsumowanie ({summary.count} prob)
            </p>
            <div className="grid grid-cols-3 gap-2 text-center">
              <StatBox label="Srednia masa" value={`${summary.avgMass.toFixed(1)} kg`} />
              <StatBox label="Sredni czas" value={`${summary.avgTime.toFixed(0)} ms`} />
              <StatBox label="Sredni YOLO" value={`${(summary.avgScore * 100).toFixed(0)}%`} />
            </div>
          </div>
        )}

        {/* Diagnostics */}
        {displayResult && <DiagnosticsPanel result={displayResult} />}

        {/* History */}
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-400 mb-2">
            Historia
          </p>
          {results.length === 0 && (
            <p className="text-xs text-zinc-600">Brak wynikow</p>
          )}
          <div className="space-y-1.5">
            {results.map(r => (
              <button
                key={r.id}
                type="button"
                onClick={() => selectEntry(r)}
                className={`flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left transition-colors ${
                  selected?.id === r.id
                    ? 'bg-emerald-900/40 ring-1 ring-emerald-700'
                    : 'hover:bg-zinc-800'
                }`}
              >
                <img
                  src={r.thumbUrl}
                  alt=""
                  className="h-10 w-14 rounded object-cover bg-zinc-800"
                />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs text-zinc-300">{r.label}</p>
                  <p className="text-sm font-semibold text-white">
                    {r.result.massKg.toFixed(1)} kg
                  </p>
                </div>
                <VerdictBadge verdict={r.result.verdict} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// -- Sub-components --

function SelectedBar({ result }: { result: PredictResult }) {
  const hasCm = result.dims.lengthCm > 0
  return (
    <div className="shrink-0 flex items-center justify-between border-t border-zinc-800 bg-zinc-900 px-4 py-2">
      <div className="flex items-center gap-4">
        <div>
          <p className="text-xs text-zinc-500">Masa</p>
          <p className="text-2xl font-bold text-white">{result.massKg.toFixed(1)} kg</p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Raw</p>
          <p className="text-lg font-semibold text-zinc-400">{result.massRawKg.toFixed(1)} kg</p>
        </div>
        <VerdictBadge verdict={result.verdict} />
      </div>
      <div className="text-right text-[11px] text-zinc-500">
        <p>YOLO {(result.score * 100).toFixed(0)}% | {result.elapsedMs.toFixed(0)} ms</p>
        <p>
          {hasCm
            ? `${result.dims.lengthCm.toFixed(0)} x ${result.dims.widthCm.toFixed(0)} cm`
            : `${result.dims.lengthPx.toFixed(0)} x ${result.dims.widthPx.toFixed(0)} px`}
          {' | '}
          {hasCm
            ? `${result.dims.areaCm2.toFixed(0)} cm2`
            : `${Math.round(result.mask.areaPx / 1000)}k px2`}
        </p>
      </div>
    </div>
  )
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const cls =
    verdict === 'ok'
      ? 'bg-emerald-900/60 text-emerald-300 border-emerald-700'
      : verdict === 'thin'
        ? 'bg-sky-900/60 text-sky-300 border-sky-700'
        : 'bg-orange-900/60 text-orange-300 border-orange-700'
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>
      {verdictLabel(verdict)}
    </span>
  )
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-zinc-800/60 px-2 py-1.5">
      <p className="text-[10px] text-zinc-500">{label}</p>
      <p className="text-sm font-semibold text-white">{value}</p>
    </div>
  )
}

function DiagnosticsPanel({ result }: { result: PredictResult }) {
  const [expandHu, setExpandHu] = useState(false)
  const feats = result.features

  const geoKeys = [
    ['area_px', 'Pole (px)'],
    ['length_px', 'Dlug (px)'],
    ['width_px', 'Szer (px)'],
    ['aspect_ratio', 'Aspect'],
    ['solidity', 'Solidity'],
    ['circularity', 'Circularity'],
    ['compactness', 'Compactness'],
    ['rectangularity', 'Rectangularity'],
    ['convexity', 'Convexity'],
    ['feret_ratio', 'Feret ratio'],
    ['ellipse_ratio', 'Ellipse ratio'],
  ] as const

  const wpKeys = Array.from({ length: 8 }, (_, i) => `wpn_${i}`)
  const huKeys = Array.from({ length: 7 }, (_, i) => `hu_${i}`)

  return (
    <div className="border-b border-zinc-800 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-400 mb-2">
        Diagnostyka
      </p>
      <div className="grid grid-cols-3 gap-x-3 gap-y-1 mb-3">
        {geoKeys.map(([key, label]) => {
          const v = feats[key]
          if (v === undefined) return null
          return (
            <div key={key}>
              <p className="text-[9px] text-zinc-600">{label}</p>
              <p className="font-mono text-xs text-zinc-300">
                {v > 1000 ? v.toFixed(0) : v.toFixed(3)}
              </p>
            </div>
          )
        })}
      </div>
      <p className="text-[10px] text-zinc-500 mb-1">Profil szerokosci (znormalizowany)</p>
      <div className="flex items-end gap-0.5 h-12 mb-3">
        {wpKeys.map(key => {
          const v = feats[key] ?? 0
          return (
            <div
              key={key}
              className="flex-1 bg-emerald-700/60 rounded-t"
              style={{ height: `${Math.max(2, v * 100)}%` }}
              title={`${key}: ${v.toFixed(3)}`}
            />
          )
        })}
      </div>
      <button
        type="button"
        onClick={() => setExpandHu(h => !h)}
        className="text-[10px] text-zinc-500 hover:text-zinc-300"
      >
        Momenty Hu {expandHu ? '▾' : '▸'}
      </button>
      {expandHu && (
        <div className="mt-1 grid grid-cols-4 gap-x-2 gap-y-0.5">
          {huKeys.map(key => {
            const v = feats[key]
            if (v === undefined) return null
            return (
              <div key={key}>
                <p className="text-[9px] text-zinc-600">{key}</p>
                <p className="font-mono text-[10px] text-zinc-400">{v.toExponential(2)}</p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// -- Helpers --

function drawMassLabel(ctx: CanvasRenderingContext2D, result: PredictResult) {
  const fontSize = Math.max(18, ctx.canvas.width / 30)
  ctx.font = `bold ${fontSize}px sans-serif`
  ctx.textBaseline = 'top'
  const label = `${result.massKg.toFixed(1)} kg`
  const tx = result.mask.bbox.x
  const ty = Math.max(0, result.mask.bbox.y - fontSize - 6)
  ctx.fillStyle = 'rgba(0,0,0,0.6)'
  const m = ctx.measureText(label)
  ctx.fillRect(tx - 4, ty, m.width + 8, fontSize + 6)
  ctx.fillStyle = '#4ade80'
  ctx.fillText(label, tx, ty + 2)
}

function humanError(e: unknown): string {
  if (e instanceof BackendError) return `${e.message} (HTTP ${e.status})`
  if (e instanceof Error) return e.message
  return String(e)
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec)) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
