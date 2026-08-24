import type { Machine } from '../lib/types'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago } from '../lib/format'

interface Props {
  machines: Machine[]
  selected: string | null
  onSelect: (id: string) => void
  recent: Set<string>
}

const VB_W = 200
const VB_H = 100

/**
 * Interlocking schematic.
 *
 * Signalling staff read their territory as a track diagram, not a table, so the
 * primary surface is one — machines sit on the layout and are coloured by their
 * indication state. It is navigation and status in a single object.
 */
export function Schematic({ machines, selected, onSelect, recent }: Props) {
  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="w-full"
      style={{ maxHeight: 260 }}
      role="group"
      aria-label="Interlocking schematic. Each node is a point machine, coloured by detected position."
    >
      {[30, 70].map((y) => (
        <line key={y} x1={4} x2={VB_W - 4} y1={y} y2={y}
          stroke="var(--color-line)" strokeWidth="1.4" strokeLinecap="round" />
      ))}
      {machines.map((m, i) => {
        if (i % 2 !== 0) return null
        const next = machines[i + 1]
        if (!next) return null
        return (
          <path key={`x${i}`} d={`M${m.x},${m.y} C${m.x + 6},${m.y} ${next.x - 6},${next.y} ${next.x},${next.y}`}
            fill="none" stroke="var(--color-line)" strokeWidth="0.9" opacity="0.55" />
        )
      })}

      {machines.map((m) => {
        const active = selected === m.id
        const colour = POSITION_COLOR[m.position]
        const alarm = m.severity === 'critical' || m.severity === 'warning'
        return (
          <g
            key={m.id}
            transform={`translate(${m.x} ${m.y})`}
            onClick={() => onSelect(m.id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.id) } }}
            tabIndex={0}
            role="button"
            aria-label={`${m.id}, ${POSITION_LABEL[m.position]}, ${m.severity}, health ${(m.health.health * 100).toFixed(0)} percent, last event ${ago(m.last_event_at)} ago`}
            className="cursor-pointer outline-none"
          >
            {active && <circle r="7.5" fill="none" stroke="var(--color-ink-dim)" strokeWidth="0.7" strokeDasharray="2 2" />}
            {alarm && (
              <circle r="5.6" fill="none" strokeWidth="0.9"
                stroke={SEVERITY_COLOR[m.severity]} opacity="0.55"
                className={recent.has(m.id) ? 'attention' : ''} />
            )}
            <circle r="4.2" fill="var(--color-surface-1)" stroke={colour} strokeWidth="1.5"
              style={{ transition: 'stroke 220ms var(--ease-out-quint)' }} />
            <circle r="1.9" fill={colour} style={{ transition: 'fill 220ms var(--ease-out-quint)' }} />
            <text y="11.5" textAnchor="middle" fontSize="3.6" fill="var(--color-ink-dim)" className="num">
              {m.id.replace('PMD', '')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
