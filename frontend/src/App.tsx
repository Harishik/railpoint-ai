import { useCallback, useEffect } from 'react'
import { Navigate, Route, Routes, useParams, useSearchParams } from 'react-router-dom'
import { RailCompact, Sidebar } from './shell/Sidebar'
import { StatusStrip } from './shell/StatusStrip'
import { Inspector } from './shell/Inspector'
import { Territory } from './pages/Territory'
import { Fleet } from './pages/Fleet'
import { Alerts } from './pages/Alerts'
import { Diagnostics } from './pages/Diagnostics'
import { Model } from './pages/Model'
import { useConsole } from './state/console'

/**
 * The console shell.
 *
 * A fixed two-column frame — rail, then a workspace that scrolls under a status
 * strip that does not. Nothing about the frame moves as you navigate, so the
 * counters, the serving model and the feed state stay in exactly the same place
 * on every page. That is the property a wall display needs and the one a page
 * of stacked cards cannot give you.
 */
export function App() {
  const { openAlerts } = useConsole()
  const latest = openAlerts[0]
  const [params, setParams] = useSearchParams()

  // The inspector lives in the URL rather than in component state, so it is
  // linkable and a link to one machine opens on whichever workspace it was sent
  // from. The write replaces rather than pushes: inspecting eight turnouts in a
  // row should not bury the previous page under eight history entries. Escape
  // and the close button are what dismiss it.
  const selected = params.get('m')
  const select = useCallback((id: string | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id === null || id === next.get('m')) next.delete('m')
      else next.set('m', id)
      return next
    }, { replace: true })
  }, [setParams])

  // Roving focus along the plan. A control-room console has to be operable
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
    <div className="grid h-full w-full overflow-hidden lg:grid-cols-[238px_minmax(0,1fr)]"
      style={{ background: 'var(--color-bg)' }}>
      <a href="#workspace"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[1000] focus:px-3 focus:py-1.5"
        style={{ background: 'var(--color-raised)', color: 'var(--color-ink)' }}>
        Skip to content
      </a>
      {/* Announced politely so a screen-reader user hears new alarms without
          losing their place. aria-live, never focus theft. */}
      <p aria-live="polite" className="sr-only">
        {latest ? `${latest.severity} alert: ${latest.message}` : ''}
      </p>

      <Sidebar />

      <main id="workspace" className="grid min-w-0 grid-rows-[auto_auto_minmax(0,1fr)] overflow-hidden">
        <RailCompact />
        <StatusStrip />
        <div className="min-w-0 overflow-y-auto overflow-x-hidden">
          <Routes>
            <Route path="/" element={<Territory selected={selected} onSelect={select} />} />
            <Route path="/fleet" element={<Fleet selected={selected} onSelect={select} />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/events/:eventId" element={<Diagnostics />} />
            <Route path="/machines/:machineId" element={<MachineRedirect />} />
            <Route path="/model" element={<Model />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>

      {selected && <Inspector id={selected} onClose={() => select(null)} />}
    </div>
  )
}

/** The machine view is a drawer now, not a page. Old links still resolve. */
function MachineRedirect() {
  const { machineId } = useParams()
  return <Navigate to={`/fleet?m=${machineId ?? ''}`} replace />
}
