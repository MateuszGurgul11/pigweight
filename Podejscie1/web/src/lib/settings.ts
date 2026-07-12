/**
 * Globalne ustawienia aplikacji — wszystkie konfigurowane przez UI lub
 * pobierane z localStorage. Wersja po przejściu na backend (FastAPI +
 * XGBoost), więc nie ma już współczynnika `calibration` (heurystyka area^1.5
 * znika) ani trybu detekcji (zawsze backend; gdy nieosiągalny → komunikat
 * w UI).
 */
export type UserSettings = {
  /** Granice „normy" (kg) — werdykt liczony backendem, ale wyświetlany w UI */
  targetMinKg: number
  targetMaxKg: number
  /** Marginesy poniżej/powyżej normy — strefa „bezpieczna" */
  marginThinKg: number
  marginFatKg: number
  /** Próg pewności detekcji YOLO (0–1) — przekazywany do /predict */
  confidenceThreshold: number
  /** Co N klatek RAF wysyłamy klatkę do backendu (rate-limit POSTów) */
  inferenceEveryNFrames: number
  /** Wyświetlany margines niepewności (± kg) */
  uncertaintyKg: number
  /**
   * Wysokość mocowania kamery nad podłogą (cm). Przekazywana do backendu jako
   * cecha modelu — XGBoost uczył się też po tej zmiennej.
   */
  cameraHeightCm: number
  /**
   * Skala obrazu: piksele na 1 cm na poziomie podłogi. 0 = brak kalibracji.
   * Backend liczy `area_cm2`, `length_cm` itd. tylko gdy > 0.
   */
  pxPerCm: number
  /** URL backendu FastAPI (np. http://192.168.1.50:8000) */
  backendUrl: string
}

export const DEFAULT_SETTINGS: UserSettings = {
  targetMinKg: 90,
  targetMaxKg: 110,
  marginThinKg: 0,
  marginFatKg: 0,
  confidenceThreshold: 0.25,
  inferenceEveryNFrames: 6,
  uncertaintyKg: 5,
  cameraHeightCm: 180,
  pxPerCm: 0,
  backendUrl: defaultBackendUrl(),
}

function defaultBackendUrl(): string {
  if (typeof window === 'undefined') return 'http://localhost:8000'
  const { protocol, hostname } = window.location
  // Gdy strona serwowana z RPi (np. http://pi.local), backend chodzi tam też.
  // W trybie dev (Vite na :5173) wskaż explicit port 8000.
  return `${protocol}//${hostname}:8000`
}

const STORAGE_KEY = 'wagadlaswin-settings-v6'

function sanitize(p: Partial<UserSettings>): Partial<UserSettings> {
  const result: Partial<UserSettings> = {}
  const numKeys: (keyof UserSettings)[] = [
    'targetMinKg', 'targetMaxKg', 'marginThinKg', 'marginFatKg',
    'confidenceThreshold', 'inferenceEveryNFrames', 'uncertaintyKg',
    'cameraHeightCm', 'pxPerCm',
  ]
  for (const k of numKeys) {
    const v = Number(p[k])
    if (k in p && Number.isFinite(v)) {
      ;(result as Record<string, unknown>)[k] = v
    }
  }
  if (typeof p.backendUrl === 'string' && p.backendUrl.trim().length > 0) {
    result.backendUrl = p.backendUrl.trim()
  }
  return result
}

export function loadSettings(): UserSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<UserSettings>
    return { ...DEFAULT_SETTINGS, ...sanitize(parsed) }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(s: UserSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}
