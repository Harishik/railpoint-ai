import type { Alert, EventSummary, Machine, Stats } from '../lib/types'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago, faultLabel, num } from '../lib/format'
import { Sparkline } from './Sparkline'

/**
 * `scroll` decides whether the body scrolls inside the card or the card sizes to
 * its content. It matters: a card whose body is `flex-1 overflow-auto` can be
 * shrunk to its header by a taller sibling in the same flex column, which is
 * how the schematic and waveform ended up 47px tall.
 */
export function Card({ title, aside, children, className = '', scroll = false, tone = 'panel' }: {
  title: string
  aside?: React.ReactNode
  children: React.ReactNode
  className?: string
  /**
   * `scroll` decides whether the body scrolls inside the card or the card sizes
   * to its content. It matters: a card whose body is `flex-1 overflow-auto` can
   * be shrunk to its header by a taller sibling in the same flex column, which
   * is how the schematic and waveform ended up 47px tall.
   */
  scroll?: boolean
  /**
   * Surface tier. Giving every panel the same border and background made the
   * console read as undifferentiated boxes — the waveform, which is the thing
   * an operator is actually reading, carried no more weight than a metadata
   * list. Elevation and padding now encode importance.
   */
  tone?: 'hero' | 'panel' | 'quiet'
}) {
  const surface =
    tone === 'hero'
      ? 'bg-surface-1 border border-line/70 rounded-xl'
      : tone === 'quiet'
        ? 'bg-transparent'
        : 'bg-surface-1 border border-line rounded-lg'

  return (
    <section
      className={`flex flex-col ${surface} ${scroll ? 'min-h-0' : 'shrink-0'} ${className}`}
      style={tone === 'hero' ? { boxShadow: 'var(--shadow-hero)' } : undefined}
    >
      <header
        className={`flex shrink-0 items-center justify-between gap-3 ${
          tone === 'quiet' ? 'pb-2' : tone === 'hero' ? 'px-4 pb-2.5 pt-3' : 'px-3 py-2'
        }`}
      >
        <h2 className={tone === 'hero' ? 't-title' : 't-micro text-ink-faint'}>{title}</h2>
        {aside}
      </header>
      <div
        className={`${scroll ? 'min-h-0 flex-1 overflow-auto' : ''} ${
          tone === 'quiet' ? '' : tone === 'hero' ? 'px-4 pb-4' : 'px-3 pb-3'
        }`}
      >
        {children}
      </div>
    </section>
  )
}

export function StatusBar({ stats, connected, notice, theme, onTheme }: {
  stats: Stats | null
  connected: boolean
  /** Overrides the Live/Reconnecting label while the base data is still
   *  loading, so the header cannot claim "Live" over an empty schematic. */
  notice?: string | null
  theme: 'dark' | 'light'
  onTheme: () => void
}) {
  // The question this bar answers is "does anything need me right now", not
  // "what are the seven counters". Attention count leads; the rest supports it.
  const attention = stats ? stats.warning + stats.critical : 0
  const worst = !stats || stats.critical > 0 ? 'fault' : attention > 0 ? 'degraded' : 'normal'
  const worstColour = `var(--color-${worst})`

  return (
    <header className="chrome sticky top-0 z-20 flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
      <div className="flex items-baseline gap-2.5">
        <span className="t-title">RailPoint&#8202;·&#8202;AI</span>
        <span className="t-label hidden text-ink-faint md:inline">
          철도 선로전환기 · Point machine operations
        </span>
      </div>

      {stats && (
        <div className="flex items-center gap-3">
          {/* The headline. One number, at display size, coloured by the worst
              state present — readable across a control room. */}
          <div className="flex items-baseline gap-1.5">
            <span className="t-display" style={{ color: attention ? worstColour : 'var(--color-ink)' }}>
              {attention === 0 ? stats.normal : attention}
            </span>
            <span className="t-label text-ink-dim">
              {attention === 0 ? 'all clear' : attention === 1 ? 'needs attention' : 'need attention'}
            </span>
          </div>

          {/* Fleet distribution as one continuous bar. Five separate counters
              made the reader do the comparison; a bar shows the proportion
              directly, and the counts stay available on hover. */}
          <FleetBar stats={stats} />
        </div>
      )}

      <div className="ml-auto flex items-center gap-3">
        <div className="flex items-center gap-1.5" title={connected ? 'Live feed connected' : 'Reconnecting'}>
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: notice ? 'var(--color-degraded)' : connected ? 'var(--color-normal)' : 'var(--color-degraded)',
              boxShadow: !notice && connected ? '0 0 0 3px color-mix(in oklch, var(--color-normal) 22%, transparent)' : 'none',
            }}
          />
          <span className="t-label text-ink-dim">
            {notice ?? (connected ? 'Live' : 'Reconnecting')}
          </span>
        </div>

        {stats && (
          <span
            className="t-label rounded-full border px-2 py-0.5"
            style={{
              borderColor: `color-mix(in oklch, ${stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)'} 45%, transparent)`,
              color: stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)',
              background: `color-mix(in oklch, ${stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)'} 10%, transparent)`,
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
          className="press t-label rounded-md border border-line px-2 py-1 text-ink-dim hover:border-line-strong hover:text-ink"
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? 'Light' : 'Dark'}
        </button>
      </div>
    </header>
  )
}

/** Fleet composition as a single proportional bar. */
function FleetBar({ stats }: { stats: Stats }) {
  const segments = [
    { key: 'normal', n: stats.normal, colour: 'var(--color-normal)', label: 'Normal' },
    { key: 'info', n: stats.info, colour: 'var(--color-transit)', label: 'Unsure' },
    { key: 'warning', n: stats.warning, colour: 'var(--color-degraded)', label: 'Warning' },
    { key: 'critical', n: stats.critical, colour: 'var(--color-fault)', label: 'Critical' },
  ].filter((s) => s.n > 0)
  const total = Math.max(1, segments.reduce((a, s) => a + s.n, 0))

  return (
    <div className="hidden items-center gap-2.5 sm:flex">
      <div
        className="flex h-1.5 w-28 overflow-hidden rounded-full bg-surface-3"
        role="img"
        aria-label={segments.map((s) => `${s.n} ${s.label}`).join(', ')}
      >
        {segments.map((s) => (
          <span
            key={s.key}
            title={`${s.label}: ${s.n}`}
            style={{
              width: `${(s.n / total) * 100}%`,
              background: s.colour,
              transition: 'width 420ms var(--ease-out-quint)',
            }}
          />
        ))}
      </div>
      <span className="t-label text-ink-faint">
        <span className="num text-ink-dim">{stats.machines}</span> machines ·{' '}
        <span className="num text-ink-dim">{stats.events_streamed}</span> throws
      </span>
    </div>
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
      <p className="t-label py-8 text-center text-ink-faint">
        No alerts. The fleet is operating within limits.
      </p>
    )
  }
  return (
    <ul className="stagger flex flex-col gap-1.5">
      {alerts.map((a) => {
        const triaged = a.state !== 'open'
        return (
          <li
            key={a.id}
            // A severity rail down the leading edge reads faster than a dot and
            // survives peripheral vision, which is how an alert list is
            // actually scanned in a control room.
            className="relative overflow-hidden rounded-md bg-surface-2 pl-2.5 pr-2 py-2 transition-opacity duration-200"
            style={{ opacity: triaged ? 0.62 : 1 }}
          >
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 w-[3px]"
              style={{ background: SEVERITY_COLOR[a.severity] }}
            />
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-baseline gap-1.5">
                  <span className="num t-label font-semibold text-ink">{a.machine_id}</span>
                  <span className="t-label truncate text-ink-dim">{faultLabel(a.fault)}</span>
                  {a.count > 1 && (
                    <span
                      className="num shrink-0 rounded-full bg-surface-3 px-1.5 text-[10px] text-ink-faint"
                      title={`Raised ${a.count} times on this machine`}
                    >
                      ×{a.count}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 truncate text-[11px] text-ink-faint">
                  {a.fault_ko} · {ago(a.last_ts ?? a.ts)} ago
                  {triaged && <span className="text-ink-dim"> · {a.state}</span>}
                </div>
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
        )
      })}
    </ul>
  )
}

function ActionButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="press rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-dim hover:border-line-strong hover:bg-surface-3 hover:text-ink"
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
            className={`t-label flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-colors duration-150 hover:bg-surface-2 aria-[current=true]:bg-surface-2 ${
              e.prediction.severity === 'normal' ? 'text-ink-faint' : 'text-ink'
            }`}
          >
            {/* A feed where every row shouts is a feed nobody reads. Normal
                throws are the overwhelming majority and recede to a hairline;
                anything else keeps its full-strength dot and text. */}
            <span
              className="shrink-0 rounded-full"
              style={{
                background: SEVERITY_COLOR[e.prediction.severity],
                width: e.prediction.severity === 'normal' ? 3 : 6,
                height: e.prediction.severity === 'normal' ? 3 : 6,
                opacity: e.prediction.severity === 'normal' ? 0.5 : 1,
              }}
            />
            <span className="num shrink-0">{e.machine_id}</span>
            <span className={`truncate ${e.prediction.severity === 'normal' ? '' : 'font-medium'}`}>
              {faultLabel(e.prediction.fault)}
            </span>
            <span className="num ml-auto shrink-0 text-ink-faint">{ago(e.ts)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}
