import { useNavigate } from 'react-router-dom'
import { Page, Section } from '../shell/Page'
import { Sparkline } from '../components/Sparkline'
import { useConsole } from '../state/console'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago, num } from '../lib/format'

/**
 * Fleet — every machine, ranked by how close it is to needing work.
 *
 * Sorted by health ascending rather than by id: a maintenance planner opens
 * this to decide what to do next, and the answer should be the first row.
 */
export function Fleet() {
  const { machines } = useConsole()
  const navigate = useNavigate()
  const sorted = [...machines].sort((a, b) => a.health.health - b.health.health)

  return (
    <Page
      title="Fleet"
      ko="전체 기기"
      lede="Ranked by health, worst first. Remaining life is a 90% conformal interval, not a point estimate."
    >
      <Section>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="t-micro text-left text-ink-faint">
                <th className="pb-2 font-semibold">Machine</th>
                <th className="pb-2 font-semibold">Position</th>
                <th className="pb-2 font-semibold">State</th>
                <th className="pb-2 pr-3 text-right font-semibold">Health</th>
                <th className="pb-2 font-semibold">Trend</th>
                <th className="pb-2 text-right font-semibold">Remaining life</th>
                <th className="pb-2 text-right font-semibold">Last throw</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((m) => (
                <tr
                  key={m.id}
                  onClick={() => navigate(`/machines/${m.id}`)}
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/machines/${m.id}`) }}
                  className="cursor-pointer border-t border-line/60 transition-colors hover:bg-surface-2"
                >
                  <td className="py-2">
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[m.severity] }} />
                      <span className="num t-label font-semibold">{m.id}</span>
                    </span>
                  </td>
                  <td className="t-label py-2" style={{ color: POSITION_COLOR[m.position] }}>
                    {POSITION_LABEL[m.position]}
                  </td>
                  <td className="t-label py-2 text-ink-dim">{m.spec}</td>
                  <td className="num t-label py-2 pr-3 text-right">{(m.health.health * 100).toFixed(0)}%</td>
                  <td className="w-24 py-2"><Sparkline values={m.health.trend} /></td>
                  <td className="num t-label py-2 text-right">
                    {m.health.rul_cycles == null ? (
                      <span className="text-ink-faint">—</span>
                    ) : (
                      <>
                        {num(m.health.rul_cycles, 0)}
                        {m.health.rul_low != null && (
                          <span className="text-ink-faint">
                            {' '}({num(m.health.rul_low, 0)}–{num(m.health.rul_high, 0)})
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td className="num t-label py-2 text-right text-ink-faint">{ago(m.last_event_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </Page>
  )
}
