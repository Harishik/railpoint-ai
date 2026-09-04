import { useState } from 'react'
import { Page, Panel, Segmented } from '../shell/Page'
import { Sparkline } from '../components/Sparkline'
import { useConsole } from '../state/console'
import { POSITION_COLOR, POSITION_KO, POSITION_LABEL, SEVERITY_COLOR, ago, num } from '../lib/format'

type Sort = 'health' | 'rul' | 'id'

/**
 * Fleet — every machine, ranked by how close it is to needing work.
 *
 * Sorted by health ascending by default rather than by id: a maintenance
 * planner opens this to decide what to do next, and the answer should be the
 * first row rather than something to be found.
 */
export function Fleet({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const { machines } = useConsole()
  const [sort, setSort] = useState<Sort>('health')

  const rows = [...machines].sort((a, b) =>
    sort === 'rul' ? (a.health.rul_cycles ?? Infinity) - (b.health.rul_cycles ?? Infinity)
      : sort === 'id' ? a.id.localeCompare(b.id)
      : a.health.health - b.health.health,
  )

  // A fixed ruler, so the interval bars are comparable between rows rather than
  // each scaled to itself.
  const pct = (v: number | null | undefined) => `${(Math.min(Math.max(v ?? 0, 0), 700) / 700 * 100).toFixed(1)}%`

  return (
    <Page
      title="Fleet"
      ko="전체 기기"
      lede="Remaining life is a 90% conformal interval in throws, not a point estimate. The bar shows the interval; the notch is the median."
      actions={
        <Segmented value={sort} onChange={setSort} label="Sort fleet"
          options={[{ value: 'health', label: 'Health' }, { value: 'rul', label: 'Life' }, { value: 'id', label: 'ID' }]} />
      }
    >
      <Panel flush>
        <div className="overflow-x-auto">
          <div className="min-w-[1000px]">
            <div className="grid grid-cols-[34px_96px_128px_74px_118px_132px_minmax(172px,1fr)_66px] items-center gap-3.5 border-b px-[18px] py-0"
              style={{ height: 38, borderColor: 'var(--color-line)', background: 'var(--color-deep)' }}>
              <span className="cap">#</span>
              <span className="cap">Machine</span>
              <span className="cap">Position</span>
              <span className="cap">Type</span>
              <span className="cap">Health</span>
              <span className="cap">{machines[0]?.health.trend.length ?? 30}-throw trend</span>
              <span className="cap">Remaining life</span>
              <span className="cap text-right">Last</span>
            </div>

            {rows.map((m, i) => {
              const colour = SEVERITY_COLOR[m.severity]
              const detected = m.position === 'N' || m.position === 'R'
              const active = selected === m.id
              return (
                <div key={m.id} role="button" tabIndex={0}
                  onClick={() => onSelect(m.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.id) } }}
                  aria-pressed={active}
                  className="grid cursor-pointer grid-cols-[34px_96px_128px_74px_118px_132px_minmax(172px,1fr)_66px] items-center gap-3.5 border-b px-[18px] transition-colors hover:bg-raised"
                  style={{ height: 52, borderColor: 'var(--color-hair)', background: active ? 'var(--color-raised)' : undefined }}>
                  <span className="flex items-center gap-2">
                    <span aria-hidden className="h-[5px] w-[5px] flex-none rounded-full" style={{ background: colour }} />
                    <span className="mono text-[10px] leading-none" style={{ color: 'var(--color-label)' }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                  </span>
                  <span className="mono text-[13px] font-medium leading-none tracking-[-0.01em]" style={{ color: 'var(--color-ink)' }}>
                    {m.id}
                  </span>
                  <span className="flex items-center gap-[7px]">
                    <span className="mono inline-flex h-[17px] w-[17px] items-center justify-center text-[10px] font-bold leading-none"
                      style={{
                        background: detected ? `color-mix(in srgb, ${POSITION_COLOR[m.position]} 16%, transparent)` : 'var(--color-idle)',
                        color: POSITION_COLOR[m.position],
                      }}>
                      {detected ? m.position : '·'}
                    </span>
                    <span className="text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>
                      {POSITION_LABEL[m.position]} <span style={{ color: 'var(--color-label)' }}>{POSITION_KO[m.position]}</span>
                    </span>
                  </span>
                  <span className="mono text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{m.spec}</span>
                  <span className="flex items-center gap-[9px]">
                    <span className="relative h-1 w-14 flex-none" style={{ background: 'var(--color-line)' }}>
                      <span className="absolute inset-y-0 left-0" style={{ width: `${m.health.health * 100}%`, background: colour }} />
                    </span>
                    <span className="mono text-[12px] font-medium leading-none" style={{ color: colour }}>
                      {(m.health.health * 100).toFixed(0)}%
                    </span>
                  </span>
                  <Sparkline values={m.health.trend} colour={colour} />
                  <span className="flex items-center gap-2.5">
                    {m.health.rul_cycles == null ? (
                      <span className="text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
                        no failure in horizon
                      </span>
                    ) : (
                      <>
                        <span className="relative h-3.5 w-24 flex-none">
                          <span className="absolute inset-x-0 top-1.5 h-0.5" style={{ background: 'var(--color-line)' }} />
                          {/* No calibrated interval means no band — drawing a
                              zero-width one under a header that promises a 90%
                              interval would state a bound we do not have. */}
                          {m.health.rul_low != null && m.health.rul_high != null && (
                            <span className="absolute top-[5px] h-1" style={{
                              left: pct(m.health.rul_low),
                              width: `calc(${pct(m.health.rul_high)} - ${pct(m.health.rul_low)})`,
                              background: colour, opacity: 0.32,
                            }} />
                          )}
                          <span className="absolute top-px h-3 w-0.5" style={{ left: pct(m.health.rul_cycles), background: colour }} />
                        </span>
                        <span className="mono text-[12px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                          {num(m.health.rul_cycles, 0)}
                          {m.health.rul_low == null && (
                            <span className="ml-1 text-[10px]" style={{ color: 'var(--color-label)' }}
                              title="Point estimate only — no calibrated interval is being served">
                              ±?
                            </span>
                          )}
                        </span>
                      </>
                    )}
                  </span>
                  <span className="mono text-right text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
                    {ago(m.last_event_at)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </Panel>
    </Page>
  )
}
