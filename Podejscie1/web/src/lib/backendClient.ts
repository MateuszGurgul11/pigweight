/**
 * Klient HTTP do backendu FastAPI (`backend/app/main.py`).
 *
 * Nie trzymamy bazowego URL w stałej — bierzemy go z `UserSettings.backendUrl`
 * przy każdym wywołaniu, żeby zmiana w panelu ustawień działała natychmiast.
 */
import type { UserSettings } from './settings'
import type { Verdict } from './heuristic'

export type Health = {
  ok: boolean
  hasYolo: boolean
  hasXgb: boolean
  version: string
  yoloError?: string | null
  xgbError?: string | null
  biasKg: number
}

export type PredictBBox = { x: number; y: number; w: number; h: number }
export type PredictMask = {
  polygon: [number, number][]
  areaPx: number
  bbox: PredictBBox
}
export type PredictDims = {
  lengthPx: number
  widthPx: number
  lengthCm: number
  widthCm: number
  areaCm2: number
}
export type PredictResult = {
  massKg: number
  massRawKg: number
  verdict: Verdict
  score: number
  mask: PredictMask
  dims: PredictDims
  features: Record<string, number>
  elapsedMs: number
}

export type CalibrateResult = {
  biasKg: number
  samples: number
  predictedKg: number
  knownKg: number
}

export class BackendError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'BackendError'
  }
}

function trimUrl(u: string): string {
  return u.replace(/\/+$/, '')
}

async function parseError(res: Response): Promise<BackendError> {
  let detail = res.statusText
  try {
    const data = await res.json() as { detail?: string }
    if (data?.detail) detail = data.detail
  } catch { /* not JSON */ }
  return new BackendError(detail, res.status)
}

export async function checkHealth(settings: UserSettings, signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${trimUrl(settings.backendUrl)}/healthz`, { signal })
  if (!res.ok) throw await parseError(res)
  return res.json() as Promise<Health>
}

function buildPredictForm(blob: Blob, settings: UserSettings, opts?: { smooth?: boolean }): FormData {
  const fd = new FormData()
  fd.append('image', blob, 'frame.jpg')
  fd.append('target_min_kg', String(settings.targetMinKg))
  fd.append('target_max_kg', String(settings.targetMaxKg))
  fd.append('margin_thin_kg', String(settings.marginThinKg))
  fd.append('margin_fat_kg', String(settings.marginFatKg))
  fd.append('confidence_threshold', String(settings.confidenceThreshold))
  fd.append('px_per_cm', String(settings.pxPerCm))
  fd.append('camera_height_cm', String(settings.cameraHeightCm))
  if (opts?.smooth !== undefined) fd.append('smooth', String(opts.smooth))
  return fd
}

export async function predictFromBlob(
  blob: Blob,
  settings: UserSettings,
  signal?: AbortSignal,
  opts?: { smooth?: boolean },
): Promise<PredictResult> {
  const res = await fetch(`${trimUrl(settings.backendUrl)}/predict`, {
    method: 'POST',
    body: buildPredictForm(blob, settings, opts),
    signal,
  })
  if (!res.ok) throw await parseError(res)
  return res.json() as Promise<PredictResult>
}

/**
 * Pobiera klatkę z elementu media (video / img / canvas) jako JPEG i wysyła
 * do `/predict`. Zwraca również wymiary tej klatki — UI musi wiedzieć,
 * w jakim układzie współrzędnych są punkty maski.
 */
export async function predictFromMedia(
  source: HTMLVideoElement | HTMLImageElement | HTMLCanvasElement,
  settings: UserSettings,
  signal?: AbortSignal,
): Promise<{ result: PredictResult; width: number; height: number }> {
  const { canvas, w, h } = sourceToCanvas(source)
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.78),
  )
  if (!blob) throw new BackendError('Nie udało się wygenerować JPEG z klatki', 0)
  const result = await predictFromBlob(blob, settings, signal)
  return { result, width: w, height: h }
}

const _scratchCanvas =
  typeof document !== 'undefined' ? document.createElement('canvas') : null

function sourceToCanvas(
  source: HTMLVideoElement | HTMLImageElement | HTMLCanvasElement,
): { canvas: HTMLCanvasElement; w: number; h: number } {
  let w = 0
  let h = 0
  if (source instanceof HTMLVideoElement) {
    w = source.videoWidth
    h = source.videoHeight
  } else if (source instanceof HTMLImageElement) {
    w = source.naturalWidth
    h = source.naturalHeight
  } else {
    w = source.width
    h = source.height
  }
  if (!w || !h || !_scratchCanvas) {
    throw new BackendError('Klatka nie ma jeszcze wymiarów', 0)
  }
  if (_scratchCanvas.width !== w || _scratchCanvas.height !== h) {
    _scratchCanvas.width = w
    _scratchCanvas.height = h
  }
  const ctx = _scratchCanvas.getContext('2d')
  if (!ctx) throw new BackendError('Brak kontekstu 2D', 0)
  ctx.drawImage(source, 0, 0, w, h)
  return { canvas: _scratchCanvas, w, h }
}

export async function calibrate(
  source: HTMLVideoElement | HTMLImageElement | HTMLCanvasElement,
  knownKg: number,
  settings: UserSettings,
  signal?: AbortSignal,
): Promise<CalibrateResult> {
  const { canvas } = sourceToCanvas(source)
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.85),
  )
  if (!blob) throw new BackendError('Nie udało się wygenerować JPEG', 0)
  const fd = new FormData()
  fd.append('image', blob, 'calib.jpg')
  fd.append('mass_kg', String(knownKg))
  fd.append('px_per_cm', String(settings.pxPerCm))
  fd.append('camera_height_cm', String(settings.cameraHeightCm))
  fd.append('confidence_threshold', String(settings.confidenceThreshold))
  const res = await fetch(`${trimUrl(settings.backendUrl)}/calibrate`, {
    method: 'POST',
    body: fd,
    signal,
  })
  if (!res.ok) throw await parseError(res)
  return res.json() as Promise<CalibrateResult>
}
