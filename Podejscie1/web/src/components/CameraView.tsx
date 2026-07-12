import { useEffect, useRef, useState } from 'react'
import { BackendError, type PredictResult } from '../lib/backendClient'
import { drawPrediction } from '../lib/drawOverlay'
import { verdictLabel, type Verdict } from '../lib/heuristic'

// Stałe konfiguracyjne — niewidoczne dla użytkownika
const BACKEND_URL = (() => {
  if (typeof window === 'undefined') return 'http://localhost:8000'
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:8000`
})()

const TARGET_MIN_KG = 90
const TARGET_MAX_KG = 110
const INFERENCE_EVERY_N_FRAMES = 5
const CONFIDENCE = 0.25
const CAMERA_HEIGHT_CM = 180

function classifyVerdict(kg: number): Verdict {
  if (kg < TARGET_MIN_KG) return 'thin'
  if (kg > TARGET_MAX_KG) return 'fat'
  return 'ok'
}

type Display = {
  result: PredictResult
  width: number
  height: number
}

export function CameraView() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const inferringRef = useRef(false)
  const frameCountRef = useRef(0)
  const rafRef = useRef(0)

  const [display, setDisplay] = useState<Display | null>(null)
  const displayRef = useRef<Display | null>(null)

  const [videoReady, setVideoReady] = useState(false)
  const [noDetection, setNoDetection] = useState(false)
  const [backendError, setBackendError] = useState<string | null>(null)

  const handleFile = (file: File) => {
    if (!file.type.startsWith('video/')) return
    const v = videoRef.current
    if (!v) return
    const url = URL.createObjectURL(file)
    v.src = url
    v.load()
    v.play().catch(() => undefined)
    setDisplay(null)
    displayRef.current = null
    setNoDetection(false)
    setBackendError(null)
    setVideoReady(false)
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const onFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  // Pętla RAF: rysuje wideo + overlay + inferencja co N klatek
  useEffect(() => {
    let stopped = false

    const loop = () => {
      if (stopped) return

      const canvas = canvasRef.current
      const video = videoRef.current
      if (!canvas || !video || video.readyState < 2) {
        rafRef.current = requestAnimationFrame(loop)
        return
      }

      const w = video.videoWidth
      const h = video.videoHeight
      if (!w || !h) {
        rafRef.current = requestAnimationFrame(loop)
        return
      }

      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }

      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.clearRect(0, 0, w, h)
        ctx.drawImage(video, 0, 0, w, h)
        const d = displayRef.current
        if (d && d.width === w && d.height === h) {
          drawPrediction(ctx, d.result.mask, 'upload')
        }
      }

      frameCountRef.current += 1
      if (
        !video.paused &&
        !inferringRef.current &&
        frameCountRef.current % INFERENCE_EVERY_N_FRAMES === 0
      ) {
        inferringRef.current = true
        void (async () => {
          try {
            const fd = new FormData()
            const blob = await new Promise<Blob | null>((res) =>
              canvas.toBlob(res, 'image/jpeg', 0.78),
            )
            if (!blob) return
            fd.append('image', blob, 'frame.jpg')
            fd.append('target_min_kg', String(TARGET_MIN_KG))
            fd.append('target_max_kg', String(TARGET_MAX_KG))
            fd.append('margin_thin_kg', '0')
            fd.append('margin_fat_kg', '0')
            fd.append('confidence_threshold', String(CONFIDENCE))
            fd.append('px_per_cm', '0')
            fd.append('camera_height_cm', String(CAMERA_HEIGHT_CM))

            const res = await fetch(`${BACKEND_URL}/predict`, {
              method: 'POST',
              body: fd,
            })
            if (!res.ok) {
              const data = await res.json().catch(() => ({})) as { detail?: string }
              if (res.status === 422) {
                setNoDetection(true)
              } else {
                setBackendError(data.detail ?? `HTTP ${res.status}`)
              }
              return
            }
            const result = await res.json() as PredictResult
            const next: Display = { result, width: w, height: h }
            displayRef.current = next
            setDisplay(next)
            setNoDetection(false)
            setBackendError(null)
          } catch (e) {
            if (e instanceof BackendError) {
              setBackendError(e.message)
            }
          } finally {
            inferringRef.current = false
          }
        })()
      }

      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)
    return () => {
      stopped = true
      cancelAnimationFrame(rafRef.current)
    }
  }, [])

  const verdict: Verdict = display ? classifyVerdict(display.result.massKg) : 'ok'

  const verdictStyle = (() => {
    if (!display) return { bar: 'bg-zinc-900 border-zinc-800', text: 'text-zinc-500', label: 'text-zinc-600' }
    if (verdict === 'thin') return { bar: 'bg-sky-950 border-sky-700', text: 'text-white', label: 'text-sky-300' }
    if (verdict === 'fat') return { bar: 'bg-orange-950 border-orange-700', text: 'text-white', label: 'text-orange-300' }
    return { bar: 'bg-emerald-950 border-emerald-700', text: 'text-white', label: 'text-emerald-300' }
  })()

  return (
    <div
      className="flex h-dvh flex-col bg-black"
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      {/* Wideo / canvas */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full object-contain"
        />
        <video
          ref={videoRef}
          className="hidden"
          playsInline
          muted
          loop
          onCanPlay={() => setVideoReady(true)}
        />

        {/* Upload overlay gdy brak wideo */}
        {!videoReady && (
          <label className="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-4 text-zinc-500 hover:text-zinc-300 transition-colors">
            <input
              type="file"
              accept="video/*"
              className="sr-only"
              onChange={onFileInput}
            />
            <svg className="h-16 w-16 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <span className="text-lg font-medium">Wgraj film testowy</span>
            <span className="text-sm opacity-60">lub przeciągnij i upuść</span>
          </label>
        )}

        {/* Błąd backendu */}
        {backendError && (
          <div className="absolute top-3 left-3 right-3 rounded-xl bg-red-950/90 border border-red-800 px-4 py-2 text-sm text-red-300">
            {backendError}
          </div>
        )}

        {/* Brak detekcji — subtelna informacja */}
        {videoReady && noDetection && !display && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 rounded-xl bg-black/70 px-4 py-2 text-sm text-zinc-400">
            Brak świni w kadrze
          </div>
        )}

        {/* Zmień film */}
        {videoReady && (
          <label className="absolute bottom-3 right-3 cursor-pointer rounded-xl border border-zinc-700 bg-black/70 px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors">
            <input type="file" accept="video/*" className="sr-only" onChange={onFileInput} />
            Zmień film
          </label>
        )}
      </div>

      {/* Pasek wyniku */}
      <div className={`shrink-0 border-t-2 px-6 py-5 ${verdictStyle.bar}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-zinc-500">Szacowana masa</p>
            <p className={`text-6xl font-bold tabular-nums leading-none mt-1 ${verdictStyle.text}`}>
              {display ? `${display.result.massKg.toFixed(1)} kg` : '— kg'}
            </p>
          </div>
          <p className={`text-4xl font-semibold text-right ${verdictStyle.label}`}>
            {display ? verdictLabel(verdict) : ''}
          </p>
        </div>
      </div>
    </div>
  )
}
