import { NavLink } from 'react-router-dom'
import { useConsole } from '../state/console'

/**
 * Left rail.
 *
 * A control room runs one screen for a whole shift, so navigation is always
 * visible rather than hidden behind a menu. Sections are numbered because the
 * console has a reading order — territory, then fleet, then what is wrong, then
 * one throw in detail, then the model that judged it — and the numbers make
 * that order explicit instead of leaving it to be inferred from position.
 *
 * The foot of the rail states what is serving. A prediction whose provenance
 * is not on screen is one nobody should act on, so it is never more than a
 * glance away, on every page.
 */
const ITEMS = [
  { to: '/', end: true, label: 'Territory', ko: '선로도' },
  { to: '/fleet', label: 'Fleet', ko: '전체 기기' },
  { to: '/alerts', label: 'Alerts', ko: '경보' },
  { to: '/diagnostics', label: 'Diagnostics', ko: '파형 분석' },
  { to: '/model', label: 'Model', ko: '모델' },
]

export function Sidebar() {
  const { openAlerts, stats, model } = useConsole()

  return (
    <aside
      className="hidden h-full grid-rows-[auto_1fr_auto] overflow-hidden border-r lg:grid"
      style={{ borderColor: 'var(--color-edge)', background: 'var(--color-rail)' }}
    >
      <div className="border-b px-5 pb-5 pt-[22px]" style={{ borderColor: 'var(--color-edge)' }}>
        <div className="flex items-baseline gap-[7px]">
          <span aria-hidden className="inline-block h-4 w-[3px] translate-y-px" style={{ background: 'var(--color-accent)' }} />
          <span className="text-[17px] font-bold leading-none tracking-[-0.02em]" style={{ color: 'var(--color-ink-hi)' }}>
            RailPoint
          </span>
          <span className="mono text-[17px] font-medium leading-none" style={{ color: 'var(--color-accent)' }}>AI</span>
        </div>
        <div className="mt-[7px] pl-2.5 text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
          철도 선로전환기 감시
        </div>
        <div className="cap mt-3.5 pl-2.5" style={{ letterSpacing: '0.16em' }}>PMD FLEET · SEHWA</div>
      </div>

      <nav className="overflow-y-auto py-3.5" aria-label="Console sections">
        {ITEMS.map((it, i) => (
          <NavLink key={it.to} to={it.to} end={it.end}
            className="relative flex h-10 items-center gap-[9px] pl-5 pr-5 transition-colors">
            {({ isActive }) => (
              <>
                {/* Location is marked by more than colour: an active tick on the
                    leading edge survives a colour-blind read. */}
                <span aria-hidden className="absolute inset-y-0 left-0 w-0.5"
                  style={{ background: isActive ? 'var(--color-accent)' : 'transparent' }} />
                <span aria-hidden className="absolute inset-0 -z-10"
                  style={{ background: isActive ? 'var(--color-active)' : 'transparent' }} />
                <span className="mono w-4 flex-none text-[9px] font-medium leading-none"
                  style={{ letterSpacing: '0.1em', color: isActive ? 'var(--color-accent)' : 'var(--color-label)' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="text-[13px] font-medium leading-none tracking-[-0.005em]"
                  style={{ color: isActive ? 'var(--color-ink-hi)' : 'var(--color-dim)' }}>
                  {it.label}
                </span>
                <span className="whitespace-nowrap text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
                  {it.ko}
                </span>
                {it.to === '/alerts' && openAlerts.length > 0 && (
                  <span className="mono ml-auto inline-flex h-[17px] min-w-[20px] items-center justify-center px-[5px]
                                   text-[10px] font-semibold leading-none"
                    style={{
                      background: 'rgba(255,90,54,.14)',
                      border: '1px solid rgba(255,90,54,.3)',
                      color: 'var(--color-accent)',
                    }}>
                    {openAlerts.length}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t px-5 pb-[18px] pt-4"
        style={{ borderColor: 'var(--color-edge)', background: 'var(--color-rail-deep)' }}>
        <div className="cap" style={{ letterSpacing: '0.16em' }}>Serving</div>
        <div className="mt-[9px] flex items-center gap-[7px]">
          <span aria-hidden className="h-[5px] w-[5px] rounded-full pulse"
            style={{ background: stats?.model_source === 'trained' ? 'var(--color-green)' : 'var(--color-amber)' }} />
          <span className="mono text-[12px] font-medium leading-none" style={{ color: 'var(--color-ink-4)' }}>
            {stats?.model_version ?? '—'}
          </span>
        </div>
        <dl className="mono mt-2.5 grid grid-cols-[1fr_auto] gap-x-2 gap-y-1 text-[10px] leading-[1.4]"
          style={{ color: 'var(--color-label)' }}>
          <dt>encoder</dt>
          <dd style={{ color: stats?.model_source === 'trained' ? 'var(--color-green)' : 'var(--color-amber)' }}>
            {stats?.model_source === 'trained' ? 'trained' : 'probe fallback'}
          </dd>
          <dt>params</dt>
          <dd style={{ color: 'var(--color-dim)' }}>
            {model?.summary ? model.summary.params.toLocaleString() : '—'}
          </dd>
          <dt>window</dt>
          <dd style={{ color: 'var(--color-dim)' }}>
            {model?.summary ? `${model.summary.window} sa` : '—'}
          </dd>
        </dl>
      </div>
    </aside>
  )
}

/**
 * The rail, folded flat.
 *
 * The design specifies a desktop console and nothing below it, but hiding the
 * rail at narrow widths left the app with no reachable navigation at all — the
 * links were in the DOM inside a `display:none` aside. This is the same five
 * sections, same numbering, on one scrollable line.
 */
export function RailCompact() {
  const { openAlerts } = useConsole()

  return (
    <nav aria-label="Console sections"
      className="flex shrink-0 items-center gap-1 overflow-x-auto border-b px-3 py-2 lg:hidden"
      style={{ borderColor: 'var(--color-edge)', background: 'var(--color-rail)' }}>
      <span className="mr-2 flex flex-none items-baseline gap-1.5 pr-2">
        <span aria-hidden className="inline-block h-3.5 w-[3px]" style={{ background: 'var(--color-accent)' }} />
        <span className="text-[14px] font-bold leading-none tracking-[-0.02em]" style={{ color: 'var(--color-ink-hi)' }}>
          RailPoint
        </span>
        <span className="mono text-[14px] font-medium leading-none" style={{ color: 'var(--color-accent)' }}>AI</span>
      </span>
      {ITEMS.map((it, i) => (
        <NavLink key={it.to} to={it.to} end={it.end}
          className="press relative flex h-8 flex-none items-center gap-2 px-3 text-[12px] font-medium leading-none">
          {({ isActive }) => (
            <>
              <span aria-hidden className="absolute inset-x-0 bottom-0 h-0.5"
                style={{ background: isActive ? 'var(--color-accent)' : 'transparent' }} />
              <span className="mono text-[9px]" style={{ letterSpacing: '0.1em', color: isActive ? 'var(--color-accent)' : 'var(--color-label)' }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span style={{ color: isActive ? 'var(--color-ink-hi)' : 'var(--color-dim)' }}>{it.label}</span>
              {it.to === '/alerts' && openAlerts.length > 0 && (
                <span className="mono inline-flex h-4 min-w-[18px] items-center justify-center px-1 text-[10px] font-semibold"
                  style={{ background: 'rgba(255,90,54,.14)', border: '1px solid rgba(255,90,54,.3)', color: 'var(--color-accent)' }}>
                  {openAlerts.length}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
