import type { UserSettings } from './settings'

export type Verdict = 'thin' | 'ok' | 'fat'

/**
 * Klasyfikacja werdyktu na podstawie estymowanej masy z modelu XGBoost
 * (backend) i progów ustawionych przez użytkownika. Sama estymacja masy żyje
 * po stronie backendu — frontend dostaje gotową wartość kg.
 */
export function classifyVerdict(estimatedKg: number, s: UserSettings): Verdict {
  const thinLine = s.targetMinKg - s.marginThinKg
  const fatLine = s.targetMaxKg + s.marginFatKg
  if (estimatedKg < thinLine) return 'thin'
  if (estimatedKg > fatLine) return 'fat'
  return 'ok'
}

export function verdictLabel(v: Verdict): string {
  switch (v) {
    case 'thin':
      return 'Za chuda'
    case 'fat':
      return 'Za gruba'
    default:
      return 'W normie'
  }
}
