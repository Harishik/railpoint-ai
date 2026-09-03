import { useConsole } from '../state/console'

/**
 * Status strip.
 *
 * Navigation lives in the sidebar, so this carries only the answer to "does
 * anything need me right now" — one number at display size, coloured by the
 * worst state present, with the fleet distribution as a single proportional bar
 * rather than five counters the reader has to compare.
 */
export function TopBar({ theme, onTheme }: { theme: 'dark' | 'light'; onTheme: () => void }) {
  const { stats, connected, bootError } = useConsole()
  const attention = stats ? stats.warning + stats.critical : 0
  const worst = !stats || stats.critical > 0 ? 'fault' : attention > 0 ? 'degraded' : 'normal'

  const segments = stats ? [
    { k: 'normal', n: stats.normal, c: 'var(--color-normal)', label: 'Normal' },
    { k: 'info', n: stats.info, c: 'var(--color-transit)', label: 'Unsure' },
    { k: 'warning', n: stats.warning, c: 'var(--color-degraded)', label: 'Warning' },
    { k: 'critical', n: stats.critical, c: 'var(--color-fault)', label: 'Critical' },
  ].filter((s) => s.n > 0) : []
  const total = Math.max(1, segments.reduce((a, s) => a + s.n, 0))

  return (
    <header className="chrome sticky top-0 z-20 flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 lg:px-5">
      {stats && (
        <div className="flex items-center gap-4">
          <div className="flex items-baseline gap-1.5">
            <span className="t-display" style={{ color: attention ? `var(--color-${worst})` : 'var(--color-ink)' }}>
              {attention === 0 ? stats.normal : attention}
            </span>
            <span className="t-label text-ink-dim">
              {attention === 0 ? 'all clear' : attention === 1 ? 'needs attention' : 'need attention'}
            </span>
          </div>

          <div className="hidden items-center gap-2.5 sm:flex">
            <div
              className="flex h-1.5 w-28 overflow-hidden rounded-full bg-surface-3"
              role="img"
              aria-label={segments.map((s) => `${s.n} ${s.label}`).join(', ')}
            >
              {segments.map((s) => (
                <span key={s.k} title={`${s.label}: ${s.n}`}
                  style={{ width: `${(s.n / total) * 100}%`, background: s.c, transition: 'width 420ms var(--ease-out-quint)' }} />
              ))}
            </div>
            <span className="t-label text-ink-faint">
              <span className="num text-ink-dim">{stats.machines}</span> machines ·{' '}
              <span className="num text-ink-dim">{stats.events_streamed}</span> throws
            </span>
          </div>
        </div>
      )}

      <div className="ml-auto flex items-center gap-3">
        <div className="flex items-center gap-1.5" title={connected ? 'Live feed connected' : 'Reconnecting'}>
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: bootError || !connected ? 'var(--color-degraded)' : 'var(--color-normal)',
              boxShadow: !bootError && connected ? '0 0 0 3px color-mix(in oklch, var(--color-normal) 22%, transparent)' : 'none',
            }}
          />
          <span className="t-label text-ink-dim">{bootError ?? (connected ? 'Live' : 'Reconnecting')}</span>
        </div>
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
