import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react'
import { api, useStream } from '../lib/api'
import type { Alert, EventSummary, Machine, ModelCard, Stats } from '../lib/types'

type AlertAction = 'acknowledge' | 'resolve' | 'reopen'

interface ConsoleValue {
  stats: Stats | null
  /** The serving model's own card. Fetched once — it changes only when the
   *  API restarts — and shared so the rail can state what is serving on every
   *  page without every page asking for it. */
  model: ModelCard | null
  machines: Machine[]
  events: EventSummary[]
  alerts: Alert[]
  openAlerts: Alert[]
  /** Machines that raised something in the last second — one attention pulse. */
  recent: Set<string>
  connected: boolean
  bootError: string | null
  onAlertAction: (id: string, action: AlertAction) => void
  eventsFor: (machineId: string | null) => EventSummary[]
  machine: (id: string | undefined) => Machine | null
}

const Ctx = createContext<ConsoleValue | null>(null)

/** Take the server's alert list, but keep the optimistic state of any alert
 *  whose own action is still in flight. Without this, a push-triggered refetch
 *  that lands between the click and the POST response reverts the row. */
function mergeAlerts(fresh: Alert[], prev: Alert[], pending: Set<string>): Alert[] {
  if (pending.size === 0) return fresh
  const local = new Map(prev.map((a) => [a.id, a]))
  return fresh.map((a) => (pending.has(a.id) ? (local.get(a.id) ?? a) : a))
}

/**
 * One live feed, shared by every workspace.
 *
 * The console is several pages over a single stream, not several pages each
 * opening their own — a socket per route would multiply load on the backend and
 * make the fleet counters disagree between tabs of the same app.
 */
export function ConsoleProvider({ children }: { children: React.ReactNode }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [model, setModel] = useState<ModelCard | null>(null)
  const [machines, setMachines] = useState<Machine[]>([])
  const [events, setEvents] = useState<EventSummary[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [recent, setRecent] = useState<Set<string>>(new Set())
  const [bootError, setBootError] = useState<string | null>(null)
  // Ids with an acknowledge/resolve POST still in flight. A push event can
  // trigger a full alert refetch at any moment, and replacing state wholesale
  // would roll the operator's optimistic update back under their cursor.
  const pendingAlerts = useRef<Set<string>>(new Set())

  const loadBase = useCallback(async () => {
    const [s, m, e, a] = await Promise.all([
      api.stats(), api.machines(), api.events(), api.alerts(),
    ])
    setStats(s); setMachines(m); setEvents(e); setAlerts(a)
    setBootError(null)
    // Not awaited with the rest: a missing experiment artefact should leave the
    // rail's serving block blank, never hold up the whole console.
    void api.model().then(setModel).catch(() => {})
  }, [])

  // The API loads torch and the model weights, which takes a while. A single
  // attempt at mount leaves the console permanently empty while the socket
  // connects and the header claims "Live" over nothing, so this retries.
  useEffect(() => {
    let cancelled = false
    let delay = 500
    const attempt = () => {
      void loadBase().catch(() => {
        if (cancelled) return
        setBootError('Waiting for the API…')
        delay = Math.min(delay * 1.6, 5000)
        window.setTimeout(attempt, delay)
      })
    }
    attempt()
    return () => { cancelled = true }
  }, [loadBase])

  const connected = useStream(
    useCallback((msg) => {
      if (msg.type !== 'event') return
      setEvents((prev) => [msg.event, ...prev].slice(0, 120))
      setMachines((prev) => prev.map((m) => (m.id === msg.machine.id ? msg.machine : m)))
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

  const onAlertAction = useCallback((id: string, action: AlertAction) => {
    // Optimistic: an operations console must feel immediate. Reconciled from
    // the server response, and every action is reversible via Undo.
    setAlerts((prev) => prev.map((a) => (a.id === id
      ? { ...a, state: action === 'acknowledge' ? 'acknowledged' : action === 'resolve' ? 'resolved' : 'open' }
      : a)))
    pendingAlerts.current.add(id)
    void api.alertAction(id, action)
      .then((updated) => setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a))))
      .finally(() => pendingAlerts.current.delete(id))
  }, [])

  const value = useMemo<ConsoleValue>(() => ({
    stats, model, machines, events, alerts,
    openAlerts: alerts.filter((a) => a.state === 'open'),
    recent, connected, bootError, onAlertAction,
    eventsFor: (id) => (id ? events.filter((e) => e.machine_id === id) : events),
    machine: (id) => machines.find((m) => m.id === id) ?? null,
  }), [stats, model, machines, events, alerts, recent, connected, bootError, onAlertAction])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useConsole(): ConsoleValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useConsole must be used inside ConsoleProvider')
  return v
}
