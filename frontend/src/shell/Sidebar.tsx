import { NavLink } from 'react-router-dom'
import { useConsole } from '../state/console'

/**
 * Persistent navigation.
 *
 * A control room runs one screen for a whole shift, so navigation is always
 * visible rather than hidden behind a menu — you should never have to open
 * something to find out where you can go. Items are named for their contents
 * ("Territory", "Diagnostics") rather than vague umbrellas, because specificity
 * is what makes navigation predictable.
 */

type Item = { to: string; label: string; ko: string; icon: React.ReactNode; end?: boolean }

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ITEMS: Item[] = [
  {
    to: '/', end: true, label: 'Territory', ko: '선로도',
    icon: <svg viewBox="0 0 20 20" {...stroke}><path d="M2 7h16M2 13h16M8 7l4 6" /></svg>,
  },
  {
    to: '/fleet', label: 'Fleet', ko: '전체 기기',
    icon: <svg viewBox="0 0 20 20" {...stroke}><path d="M3 5h14M3 10h14M3 15h14" /></svg>,
  },
  {
    to: '/alerts', label: 'Alerts', ko: '경보',
    icon: <svg viewBox="0 0 20 20" {...stroke}><path d="M10 3v8M10 15v.5" /><circle cx="10" cy="10" r="7.5" /></svg>,
  },
  {
    to: '/diagnostics', label: 'Diagnostics', ko: '파형 분석',
    icon: <svg viewBox="0 0 20 20" {...stroke}><path d="M2 13l3-7 3 10 3-13 3 10 2-4h2" /></svg>,
  },
  {
    to: '/model', label: 'Model', ko: '모델',
    icon: <svg viewBox="0 0 20 20" {...stroke}><circle cx="10" cy="10" r="2.4" /><circle cx="10" cy="10" r="7.5" /><path d="M10 2.5v5M10 12.4v5M2.5 10h5M12.4 10h5" /></svg>,
  },
]

export function Sidebar() {
  const { openAlerts, stats } = useConsole()

  return (
    <nav
      aria-label="Console sections"
      className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-surface-1 px-2 py-1.5
                 lg:h-full lg:w-[188px] lg:flex-col lg:overflow-visible lg:border-b-0 lg:border-r lg:px-2.5 lg:py-3"
    >
      <div className="mb-1 hidden px-1.5 pb-2 lg:block">
        <div className="t-title">RailPoint&#8202;·&#8202;AI</div>
        <div className="t-label text-ink-faint">철도 선로전환기</div>
      </div>

      {ITEMS.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          end={it.end}
          className={({ isActive }) =>
            `press group relative flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors ${
              isActive ? 'bg-surface-3 text-ink' : 'text-ink-dim hover:bg-surface-2 hover:text-ink'
            }`
          }
        >
          {({ isActive }) => (
            <>
              {/* Current location is marked by more than colour: an active rail
                  on the leading edge survives a colour-blind read. */}
              <span
                aria-hidden
                className="absolute inset-y-1.5 left-0 w-[3px] rounded-full transition-opacity"
                style={{ background: 'var(--color-transit)', opacity: isActive ? 1 : 0 }}
              />
              <span className="h-[18px] w-[18px] shrink-0 opacity-90">{it.icon}</span>
              <span className="t-label font-medium">{it.label}</span>
              <span className="t-label hidden text-ink-faint lg:inline">{it.ko}</span>
              {it.to === '/alerts' && openAlerts.length > 0 && (
                <span
                  className="num ml-auto shrink-0 rounded-full px-1.5 text-[10px] font-semibold"
                  style={{
                    background: 'color-mix(in oklch, var(--color-fault) 20%, transparent)',
                    color: 'var(--color-fault)',
                  }}
                >
                  {openAlerts.length}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}

      {stats && (
        <div className="mt-auto hidden px-1.5 pt-3 lg:block">
          <div className="t-micro text-ink-faint">Serving</div>
          <div className="num mt-1 text-[11px] text-ink-dim">{stats.model_version}</div>
          <div
            className="t-label mt-0.5"
            style={{ color: stats.model_source === 'trained' ? 'var(--color-normal)' : 'var(--color-degraded)' }}
          >
            {stats.model_source === 'trained' ? 'trained encoder' : 'probe fallback'}
          </div>
        </div>
      )}
    </nav>
  )
}
