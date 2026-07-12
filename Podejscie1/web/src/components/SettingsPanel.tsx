import type { UserSettings } from '../lib/settings'

type Props = {
  open: boolean
  settings: UserSettings
  onChange: (s: UserSettings) => void
  onClose: () => void
}

export function SettingsPanel({ open, settings, onChange, onClose }: Props) {
  if (!open) return null

  const patch = (partial: Partial<UserSettings>) => onChange({ ...settings, ...partial })

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-3 sm:items-center"
      role="dialog"
      aria-modal
      aria-labelledby="settings-title"
    >
      <div className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-zinc-700 bg-zinc-900 p-5 shadow-xl sm:rounded-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h2 id="settings-title" className="text-xl font-semibold text-emerald-100">
            Ustawienia
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800"
          >
            Zamknij
          </button>
        </div>

        <div className="space-y-6 text-sm">

          {/* ── Backend ── */}
          <section>
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Backend (FastAPI)
            </p>
            <label className="block">
              <span className="text-zinc-400">Adres URL</span>
              <input
                type="url"
                value={settings.backendUrl}
                onChange={e => patch({ backendUrl: e.target.value })}
                placeholder="http://192.168.1.50:8000"
                className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono text-base text-white"
              />
            </label>
            <p className="mt-1 text-[11px] text-zinc-600">
              Backend musi być osiągalny w sieci (ten sam Wi-Fi co tablet).
              Domyślnie {`<protokół>://<host strony>:8000`}.
            </p>

            <div className="mt-3 grid grid-cols-2 gap-3">
              <label>
                <span className="text-zinc-400">Inferencja co N klatek</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={settings.inferenceEveryNFrames}
                  onChange={e =>
                    patch({ inferenceEveryNFrames: Number(e.target.value) })
                  }
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
              <label>
                <span className="text-zinc-400">Próg pewności (0–1)</span>
                <input
                  type="number"
                  min={0.05}
                  max={0.95}
                  step="0.05"
                  value={settings.confidenceThreshold}
                  onChange={e =>
                    patch({ confidenceThreshold: Number(e.target.value) })
                  }
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
            </div>
          </section>

          {/* ── Progi masy ── */}
          <section>
            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Progi masy
            </p>
            <p className="mb-3 text-[11px] text-zinc-600">
              Za chuda: poniżej (norma od − margines) · Za gruba: powyżej (norma do + margines).
            </p>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="text-zinc-400">Norma od (kg)</span>
                <input
                  type="number"
                  step="1"
                  value={settings.targetMinKg}
                  onChange={e => patch({ targetMinKg: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
              <label>
                <span className="text-zinc-400">Norma do (kg)</span>
                <input
                  type="number"
                  step="1"
                  value={settings.targetMaxKg}
                  onChange={e => patch({ targetMaxKg: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
              <label>
                <span className="text-zinc-400">Margines „za chuda" (kg)</span>
                <input
                  type="number"
                  step="1"
                  min={0}
                  value={settings.marginThinKg}
                  onChange={e => patch({ marginThinKg: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
              <label>
                <span className="text-zinc-400">Margines „za gruba" (kg)</span>
                <input
                  type="number"
                  step="1"
                  min={0}
                  value={settings.marginFatKg}
                  onChange={e => patch({ marginFatKg: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
            </div>
            <div className="mt-2 rounded-lg bg-zinc-800/60 px-3 py-2 text-[11px] text-zinc-400">
              Za chuda &lt; <span className="font-mono text-sky-400">{settings.targetMinKg - settings.marginThinKg} kg</span>
              {' · '}
              Norma <span className="font-mono text-emerald-400">{settings.targetMinKg - settings.marginThinKg}–{settings.targetMaxKg + settings.marginFatKg} kg</span>
              {' · '}
              Za gruba &gt; <span className="font-mono text-orange-400">{settings.targetMaxKg + settings.marginFatKg} kg</span>
            </div>
          </section>

          {/* ── Kamera ── */}
          <section>
            <p className="mb-1 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Geometria kamery
            </p>
            <p className="mb-3 text-[11px] text-zinc-600">
              Wysokość musi być stała przy każdym pomiarze. Skalę px/cm
              ustawisz w panelu „Kalibracja" na ekranie głównym.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="text-zinc-400">Wysokość kamery (cm)</span>
                <input
                  type="number"
                  step="1"
                  min={1}
                  value={settings.cameraHeightCm}
                  onChange={e => patch({ cameraHeightCm: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
              <label>
                <span className="text-zinc-400">Skala (px na 1 cm)</span>
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  value={settings.pxPerCm}
                  onChange={e => patch({ pxPerCm: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
                />
              </label>
            </div>
          </section>

          {/* ── Wyświetlanie ── */}
          <section>
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Wyświetlanie
            </p>
            <label className="block">
              <span className="text-zinc-400">Margines niepewności (± kg)</span>
              <input
                type="number"
                step="0.5"
                min={0}
                value={settings.uncertaintyKg}
                onChange={e => patch({ uncertaintyKg: Number(e.target.value) })}
                className="mt-1 w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-3 font-mono"
              />
            </label>
          </section>

        </div>
      </div>
    </div>
  )
}
