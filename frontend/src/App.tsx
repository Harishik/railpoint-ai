import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, useStream } from './lib/api'
import type { Alert, EventDetail, EventSummary, Machine, Stats } from './lib/types'
import { SEVERITY_COLOR, faultLabel, num } from './lib/format'
import { Schematic } from './components/Schematic'
import { Waveform } from './components/Waveform'
import { Evidence } from './components/Evidence'
import { AlertList, Card, EventList, FleetTable, StatusBar } from './components/Panels'

/** Take the server's alert list, but keep the optimistic state of any alert
 *  whose own action is still in flight. Without this, a push-triggered refetch
 *  that lands between the click and the POST response reverts the row. */
function mergeAlerts(fresh: Alert[], prev: Alert[], pending: Set<string>): Alert[] {
  if (pending.size === 0) return fresh
  const local = new Map(prev.map((a) => [a.id, a]))
  return fresh.map((a) => (pending.has(a.id) ? (local.get(a.id) ?? a) : a))
}

export function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [stats, setStats] = useState<Stats | null>(null)
  const [machines, setMachines] = useState<Machine[]>([])
  const [events, setEvents] = useState<EventSummary[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  // Ids with an acknowledge/resolve POST still in flight. A push event can
  // trigger a full alert refetch at any moment, and replacing state wholesale
  // would roll the operator's optimistic update back under their cursor.
  const pendingAlerts = useRef<Set<string>>(new Set())
  const [selectedMachine, setSelectedMachine] = useState<string | null>(null)
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null)
  const [detail, setDetail] = useState<EventDetail | null>(null)
  const [hoveredFeature, setHoveredFeature] = useState<string | null>(null)
  const [recent, setRecent] = useState<Set<string>>(new Set())

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  useEffect(() => {
    void Promise.all([api.stats(), api.machines(), api.events(), api.alerts()]).then(
      ([s, m, e, a]) => {
        setStats(s); setMachines(m); setEvents(e); setAlerts(a)
        if (e.length && !selectedEvent) setSelectedEvent(e[0].id)
      },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connected = useStream(
    useCallback((msg) => {
      if (msg.type !== 'event') return
      setEvents((prev) => [msg.event, ...prev].slice(0, 80))
      setMachines((prev) => prev.map((m) => (m.id === msg.machine.id ? msg.machine : m)))
      // One attention pulse on the schematic, then it settles — see index.css.
      if (msg.event.prediction.severity !== 'normal') {
        setRecent((prev) => new Set(prev).add(msg.machine.id))
        setTimeout(() => setRecent((prev) => {
          const next = new Set(prev); next.delete(msg.machine.id); return next
        }), 1000)
        void api.alerts().then((fresh) =>
          setAlerts((prev) => mergeAlerts(fresh, prev, pendingAlerts.current)),
        )
      }
      void api.stats().then(setStats)
    }, []),
  )

  useEffect(() => {
    if (!selectedEvent) return
    let live = true
    void api.event(selectedEvent).then((d) => { if (live) setDetail(d) }).catch(() => {})
    return () => { live = false }
  }, [selectedEvent])

  const visibleEvents = useMemo(
    () => (selectedMachine ? events.filter((e) => e.machine_id === selectedMachine) : events),
    [events, selectedMachine],
  )

  const onAlertAction = useCallback(
    (id: string, action: 'acknowledge' | 'resolve' | 'reopen') => {
      // Optimistic: an operations console must feel immediate. Reconciled from
      // the server response, and every action is reversible via Undo.
      setAlerts((prev) => prev.map((a) => (a.id === id
        ? { ...a, state: action === 'acknowledge' ? 'acknowledged' : action === 'resolve' ? 'resolved' : 'open' }
        : a)))
      pendingAlerts.current.add(id)
      void api.alertAction(id, action)
        .then((updated) =>
          setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a))),
        )
        .finally(() => pendingAlerts.current.delete(id))
    }, [],
  )

  // Arrow-key traversal across the fleet. A control-room console has to be
  // operable without a mouse, and the schematic is the primary surface.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!machines.length) return
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      // Only claim the arrow keys where they mean "move along the track". A
      // window-level handler that swallowed them everywhere also swallowed
      // horizontal scrolling and any other widget's own arrow handling.
      const inSchematic = !!target?.closest('[data-schematic]')
      const onBody = target === document.body || target === null
      if (!inSchematic && !onBody) return
      e.preventDefault()
      const ids = machines.map((m) => m.id)
      const at = selectedMachine ? ids.indexOf(selectedMachine) : -1
      const step = e.key === 'ArrowRight' ? 1 : -1
      const next = ids[(at + step + ids.length) % ids.length]
      setSelectedMachine(next)
      // Selection without focus leaves a screen-reader user's virtual cursor
      // behind, reading a node the app no longer considers selected.
      requestAnimationFrame(() => {
        document.querySelector<SVGGElement>(`[data-machine-node="${next}"]`)?.focus()
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [machines, selectedMachine])

  const selected = machines.find((m) => m.id === selectedMachine) ?? null
  const pred = detail?.prediction
  const openAlerts = alerts.filter((a) => a.state === 'open')
  const latestAlert = openAlerts[0]

  return (
    <div className="flex h-full flex-col bg-bg text-ink">
      <a
        href="#console"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[1000] focus:rounded focus:bg-surface-3 focus:px-3 focus:py-1.5"
      >
        Skip to console
      </a>
      {/* Announced politely so a screen-reader user hears new alarms without
          losing their place. aria-live, never focus theft. */}
      <p aria-live="polite" className="sr-only">
        {latestAlert ? `${latestAlert.severity} alert: ${latestAlert.message}` : ''}
      </p>
      <StatusBar stats={stats} connected={connected} theme={theme} onTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />

      <main id="console" className="grid flex-1 gap-3 overflow-auto p-3 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="flex flex-col gap-3">
          <Card
            title="Interlocking schematic"
            aside={
              selected ? (
                <button onClick={() => setSelectedMachine(null)} className="text-[11px] text-ink-faint underline-offset-2 hover:underline">
                  clear filter · {selected.id}
                </button>
              ) : (
                <span className="text-[11px] text-ink-faint">click a machine, or use ← →</span>
              )
            }
          >
            <Schematic machines={machines} selected={selectedMachine} recent={recent}
              onSelect={(id) => setSelectedMachine((cur) => (cur === id ? null : id))} />
          </Card>

          <Card
            title={detail ? `Event ${detail.id} · ${detail.machine_id}` : 'Waveform'}
            aside={
              pred && (
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="rounded px-1.5 py-0.5 font-medium"
                    style={{ background: `color-mix(in oklch, ${SEVERITY_COLOR[pred.severity]} 18%, transparent)`, color: SEVERITY_COLOR[pred.severity] }}>
                    {pred.fault_en}
                  </span>
                  <span className="text-ink-faint">{pred.fault_ko}</span>
                  <span className="num text-ink-dim">{(pred.confidence * 100).toFixed(0)}%</span>
                </div>
              )
            }
          >
            {detail ? (
              <Waveform event={detail} hoveredFeature={hoveredFeature} />
            ) : (
              /* Reserves the final height so arrival does not shift the layout. */
              <div className="h-[360px] animate-pulse rounded bg-surface-2" />
            )}
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            <Card title="Fleet" scroll className="max-h-[460px] min-h-[220px]">
              <FleetTable machines={machines} selected={selectedMachine} onSelect={(id) => setSelectedMachine((c) => (c === id ? null : id))} />
            </Card>
            <Card
              title="Evidence"
              scroll
              className="max-h-[460px] min-h-[220px]"
              aside={pred && (
                <span className="text-[11px] text-ink-faint">
                  {pred.set_size === 1 ? 'confident' : `${pred.set_size} candidates at 90%`}
                </span>
              )}
            >
              {detail ? (
                <>
                  {pred && pred.set_size > 1 && (
                    <p className="mb-2 rounded border border-line bg-surface-2 px-2 py-1.5 text-[11px] leading-snug text-ink-dim">
                      The model cannot separate{' '}
                      <span className="text-ink">{pred.prediction_set.map(faultLabel).join(', ')}</span>{' '}
                      at 90% coverage. Treat as a shortlist, not a diagnosis.
                    </p>
                  )}
                  <Evidence attributions={detail.attributions} onHover={setHoveredFeature} />
                </>
              ) : (
                <div className="h-32 animate-pulse rounded bg-surface-2" />
              )}
            </Card>
          </div>
        </div>

        <aside className="flex flex-col gap-3">
          <Card title="Alerts" scroll className="max-h-[38vh]"
            aside={<span className="num text-[11px] text-ink-faint">{openAlerts.length} open</span>}>
            <AlertList alerts={alerts.slice(0, 24)} onAction={onAlertAction} />
          </Card>

          {selected && (
            <Card title={`${selected.id} · health`}>
              <dl className="grid grid-cols-2 gap-y-2 text-[12px]">
                <dt className="text-ink-faint">Health index</dt>
                <dd className="num text-right">{(selected.health.health * 100).toFixed(1)}%</dd>
                <dt className="text-ink-faint">Remaining life</dt>
                <dd className="num text-right">
                  {selected.health.rul_cycles == null ? '—' : (
                    <>
                      {num(selected.health.rul_cycles, 0)}
                      {selected.health.rul_low != null && (
                        <span className="text-ink-faint"> ({num(selected.health.rul_low, 0)}–{num(selected.health.rul_high, 0)})</span>
                      )}
                      <span className="text-ink-faint"> cycles</span>
                    </>
                  )}
                </dd>
                <dt className="text-ink-faint">Throws seen</dt>
                <dd className="num text-right">{selected.events_today}</dd>
                <dt className="text-ink-faint">Type</dt>
                <dd className="num text-right">{selected.spec}</dd>
              </dl>
            </Card>
          )}

          <Card title="Event feed" scroll className="max-h-[46vh]"
            aside={<span className="text-[11px] text-ink-faint">{selectedMachine ?? 'all machines'}</span>}>
            <EventList events={visibleEvents.slice(0, 40)} selected={selectedEvent} onSelect={setSelectedEvent} />
          </Card>
        </aside>
      </main>
    </div>
  )
}
