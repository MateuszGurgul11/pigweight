import { useState } from 'react'
import { CameraView } from './components/CameraView'
import { TestPanel } from './components/TestPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { loadSettings, saveSettings, type UserSettings } from './lib/settings'

type Tab = 'camera' | 'test'

export default function App() {
  const [tab, setTab] = useState<Tab>('test')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settings, setSettings] = useState<UserSettings>(loadSettings)

  const handleSettings = (s: UserSettings) => {
    setSettings(s)
    saveSettings(s)
  }

  return (
    <div className="flex h-dvh flex-col bg-[#0c1a12]">
      {/* Top bar */}
      <header className="shrink-0 flex items-center justify-between border-b border-zinc-800 bg-zinc-950 px-4 py-2">
        <h1 className="text-base font-semibold text-emerald-200 tracking-wide">
          WagaDlaSwin
        </h1>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setTab('camera')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === 'camera'
                ? 'bg-emerald-900/60 text-emerald-300'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            Kamera
          </button>
          <button
            onClick={() => setTab('test')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === 'test'
                ? 'bg-emerald-900/60 text-emerald-300'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            Testowanie
          </button>
          <div className="mx-2 h-5 w-px bg-zinc-800" />
          <button
            onClick={() => setSettingsOpen(true)}
            className="rounded-lg p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors"
            aria-label="Ustawienia"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l1.18 2.044a1 1 0 01-.205 1.251l-1.267 1.113a7.047 7.047 0 010 2.228l1.267 1.113a1 1 0 01.206 1.25l-1.18 2.045a1 1 0 01-1.187.447l-1.598-.54a6.993 6.993 0 01-1.929 1.115l-.33 1.652a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-1.18-2.044a1 1 0 01.205-1.251l1.267-1.114a7.05 7.05 0 010-2.227L1.821 7.773a1 1 0 01-.206-1.25l1.18-2.045a1 1 0 011.187-.447l1.598.54A6.993 6.993 0 017.51 3.456l.33-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'camera' && (
          <CameraView
            settings={settings}
            onSettingsChange={handleSettings}
            onSettingsClick={() => setSettingsOpen(true)}
          />
        )}
        {tab === 'test' && <TestPanel settings={settings} />}
      </div>

      <SettingsPanel
        open={settingsOpen}
        settings={settings}
        onChange={handleSettings}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
