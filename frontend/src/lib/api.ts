import { useCallback, useEffect, useRef, useState } from 'react'
import type { Alert, EventDetail, EventSummary, Machine, Stats } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  stats: () => get<Stats>('/api/stats'),
  machines: () => get<Machine[]>('/api/machines'),
  events: (machineId?: string) =>
    get<EventSummary[]>(`/api/events${machineId ? `?machine_id=${machineId}` : ''}`),
  event: (id: string) => get<EventDetail>(`/api/events/${id}`),
  alerts: () => get<Alert[]>('/api/alerts'),
  alertAction: (id: string, action: 'acknowledge' | 'resolve' | 'reopen') =>
    fetch(`/api/alerts/${id}/${action}`, { method: 'POST' }).then((r) => r.json() as Promise<Alert>),
}

type Push = { type: 'event'; event: EventSummary; machine: Machine } | { type: 'hello'; stats: Stats }

/**
 * Live feed. Reconnects with backoff rather than dying silently — an
 * operations console that has quietly stopped updating is actively dangerous,
 * so connection state is surfaced, never hidden.
 */
export function useStream(onPush: (msg: Push) => void) {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onPush)
  handler.current = onPush

  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout>
    let attempt = 0
    let closed = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/stream`)
      ws.onopen = () => { attempt = 0; setConnected(true) }
      ws.onmessage = (e) => handler.current(JSON.parse(e.data) as Push)
      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        attempt += 1
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempt, 15000))
      }
      ws.onerror = () => ws?.close()
    }
    connect()
    return () => { closed = true; clearTimeout(timer); ws?.close() }
  }, [])

  return connected
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const run = useCallback(() => {
    let live = true
    setLoading(true)
    fn()
      .then((d) => { if (live) { setData(d); setError(null) } })
      .catch((e: Error) => { if (live) setError(e.message) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(run, [run])
  return { data, error, loading, reload: run }
}
