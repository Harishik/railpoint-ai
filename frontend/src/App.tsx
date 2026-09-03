import { useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Sidebar } from './shell/Sidebar'
import { TopBar } from './shell/TopBar'
import { Territory } from './pages/Territory'
import { Fleet } from './pages/Fleet'
import { Alerts } from './pages/Alerts'
import { Diagnostics } from './pages/Diagnostics'
import { MachinePage } from './pages/MachinePage'
import { Model } from './pages/Model'
import { useConsole } from './state/console'

export function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const { openAlerts } = useConsole()
  const latest = openAlerts[0]

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  // Roving focus along the schematic. A control-room console has to be operable
  // without a mouse, but the arrows move *focus* rather than navigating — a key
  // press that changes page under the operator is not traversal, it is a trap.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      const nodes = [...document.querySelectorAll<SVGGElement>('[data-machine-node]')]
      if (!nodes.length) return
      const inSchematic = !!target?.closest('[data-schematic]')
      if (!inSchematic && target !== document.body && target !== null) return
      e.preventDefault()
      const at = nodes.findIndex((n) => n === (target as unknown as SVGGElement) || (target ? n.contains(target) : false))
      const step = e.key === 'ArrowRight' ? 1 : -1
      nodes[(at + step + nodes.length) % nodes.length]?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full flex-col bg-bg text-ink lg:flex-row">
      <a
        href="#workspace"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[1000] focus:rounded focus:bg-surface-3 focus:px-3 focus:py-1.5"
      >
        Skip to content
      </a>
      {/* Announced politely so a screen-reader user hears new alarms without
          losing their place. aria-live, never focus theft. */}
      <p aria-live="polite" className="sr-only">
        {latest ? `${latest.severity} alert: ${latest.message}` : ''}
      </p>

      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar theme={theme} onTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
        <main id="workspace" className="min-h-0 flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Territory />} />
            <Route path="/fleet" element={<Fleet />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/events/:eventId" element={<Diagnostics />} />
            <Route path="/machines/:machineId" element={<MachinePage />} />
            <Route path="/model" element={<Model />} />
            <Route path="*" element={<Territory />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
