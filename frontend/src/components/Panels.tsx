import type { Alert, EventSummary, Machine, Stats } from '../lib/types'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago, faultLabel, num } from '../lib/format'
import { Sparkline } from './Sparkline'

/**
 * `scroll` decides whether the body scrolls inside the card or the card sizes to
 * its content. It matters: a card whose body is `flex-1 overflow-auto` can be
 * shrunk to its header by a taller sibling in the same flex column, which is
 * how the schematic and waveform ended up 47px tall.
 */
export function Card({ title, aside, children, className = '', scroll = false }: {
  title: string
  aside?: React.ReactNode
  children: React.ReactNode
  className?: string
  scroll?: boolean
}) {
  return (
    <section
      className={`flex flex-col rounded-lg border border-line bg-surface-1 ${scroll ? 'min-h-0' : 'shrink-0'} ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-3 py-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.09em] text-ink-faint">{title}</h2>
        {aside}
      </header>
      <div className={scroll ? 'min-h-0 flex-1 overflow-auto p-3' : 'p-3'}>{children}</div>
    </section>
  )
}

export function StatusBar({ stats, connected, theme, onTheme }: {
  stats: Stats | null; connected: boolean; theme: 'dark' | 'light'; onTheme: () => void
}) {
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-surface-1 px-4 py-2.5">
      <div className="flex items-baseline gap-2.5">
        <span className="text-[15px] font-semibold tracking-tight">RailPoint&#8202;·&#8202;AI</span>
        <span className="hidden text-[11px] text-ink-faint sm:inline">
          철도 선로전환기 · Point machine operations
        </span>
      </div>

      <div className="flex items-center gap-1.5" title={connected ? 'Live feed connected' : 'Reconnecting'}>
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: connected ? 'var(--color-normal)' : 'var(--color-degraded)' }}
        />
        <span className="text-[12px] text-ink-dim">{connected ? 'Live' : 'Reconnecting'}</span>
      </div>

      {stats && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
          <Stat label="Machines" value={stats.machines} />
          <Stat label="Normal" value={stats.normal} colour="var(--color-normal)" />
          <Stat label="Warning" value={stats.warning} colour="var(--color-degraded)" />
          <Stat label="Critical" value={stats.critical} colour="var(--color-fault)" />
          <Stat label="Events" value={stats.events_streamed} />
          <Stat label="Open alerts" value={stats.open_alerts} />
        </div>
      )}

      <div className="ml-auto flex items-center gap-3">
        {stats && (
          <span
            className="rounded border px-1.5 py-0.5 text-[11px]"
            style={{
              borderColor: stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)',
              color: stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)',
            }}
            title={
              stats.model_source === 'trained'
                ? 'Serving the trained encoder'
                : 'Trained model not yet available — serving the linear probe fallback'
            }
          >
            {stats.model_source === 'trained' ? 'model' : 'fallback'}&#8202;·&#8202;{stats.model_version}
          </span>
        )}
        <button
          onClick={onTheme}
          className="rounded border border-line px-2 py-1 text-[12px] text-ink-dim transition-colors duration-150 hover:border-line-strong hover:text-ink"
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? 'Light' : 'Dark'}
        </button>
      </div>
    </header>
  )
}

function Stat({ label, value, colour }: { label: string; value: number; colour?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-ink-faint">{label}</span>
      <span className="num font-medium" style={colour ? { color: colour } : undefined}>{value}</span>
    </span>
  )
}

export function FleetTable({ machines, selected, onSelect }: {
  machines: Machine[]; selected: string | null; onSelect: (id: string) => void
}) {
  const sorted = [...machines].sort((a, b) => a.health.health - b.health.health)
  return (
    <table className="w-full border-collapse text-[12px]">
      <thead>
        <tr className="text-left text-ink-faint">
          <th className="pb-1.5 font-medium">Machine</th>
          <th className="pb-1.5 font-medium">Position</th>
          <th className="pb-1.5 pr-2 text-right font-medium">Health</th>
          <th className="pb-1.5 pr-2 font-medium">Trend</th>
          <th className="pb-1.5 text-right font-medium">RUL</th>
          <th className="pb-1.5 text-right font-medium">Last</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((m) => (
          <tr
            key={m.id}
            onClick={() => onSelect(m.id)}
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') onSelect(m.id) }}
            aria-selected={selected === m.id}
            className="cursor-pointer border-t border-line/60 transition-colors duration-150 hover:bg-surface-2 aria-selected:bg-surface-2"
          >
            <td className="py-1.5">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: SEVERITY_COLOR[m.severity] }} />
                <span className="num">{m.id}</span>
              </span>
            </td>
            <td className="py-1.5" style={{ color: POSITION_COLOR[m.position] }}>{POSITION_LABEL[m.position]}</td>
            <td className="num py-1.5 pr-2 text-right">{(m.health.health * 100).toFixed(0)}%</td>
            <td className="py-1.5 pr-2"><Sparkline values={m.health.trend} colour={SEVERITY_COLOR[m.severity]} /></td>
            <td className="num py-1.5 text-right text-ink-dim">
              {m.health.rul_cycles == null ? '—' : `${num(m.health.rul_cycles, 0)}`}
            </td>
            <td className="num py-1.5 text-right text-ink-faint">{ago(m.last_event_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function AlertList({ alerts, onAction }: {
  alerts: Alert[]; onAction: (id: string, action: 'acknowledge' | 'resolve' | 'reopen') => void
}) {
  if (!alerts.length) {
    return (
      <p className="py-6 text-center text-[12px] text-ink-faint">
        No alerts. The fleet is operating within limits.
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {alerts.map((a) => (
        <li key={a.id} className="rise rounded-md border border-line bg-surface-2 px-2.5 py-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[a.severity] }} />
                <span className="num text-[12px] font-medium">{a.machine_id}</span>
                <span className="text-[12px] text-ink-dim">{faultLabel(a.fault)}</span>
              </div>
              <div className="mt-0.5 truncate text-[11px] text-ink-faint">{a.fault_ko} · {ago(a.ts)} ago</div>
            </div>
            <div className="flex shrink-0 gap-1">
              {a.state === 'open' && (
                <ActionButton onClick={() => onAction(a.id, 'acknowledge')}>Ack</ActionButton>
              )}
              {a.state !== 'resolved' && (
                <ActionButton onClick={() => onAction(a.id, 'resolve')}>Resolve</ActionButton>
              )}
              {a.state === 'resolved' && (
                <ActionButton onClick={() => onAction(a.id, 'reopen')}>Undo</ActionButton>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

function ActionButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-dim transition-colors duration-150 hover:border-line-strong hover:text-ink"
    >
      {children}
    </button>
  )
}

export function EventList({ events, selected, onSelect }: {
  events: EventSummary[]; selected: string | null; onSelect: (id: string) => void
}) {
  return (
    <ul className="flex flex-col gap-0.5">
      {events.map((e) => (
        <li key={e.id}>
          <button
            onClick={() => onSelect(e.id)}
            aria-current={selected === e.id}
            className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-[12px] transition-colors duration-150 hover:bg-surface-2 aria-[current=true]:bg-surface-2"
          >
            <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: SEVERITY_COLOR[e.prediction.severity] }} />
            <span className="num shrink-0 text-ink-dim">{e.machine_id}</span>
            <span className="truncate">{faultLabel(e.prediction.fault)}</span>
            <span className="num ml-auto shrink-0 text-ink-faint">{ago(e.ts)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
