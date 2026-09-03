import type { Machine } from '../lib/types'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago } from '../lib/format'

interface Props {
  machines: Machine[]
  selected: string | null
  onSelect: (id: string) => void
  recent: Set<string>
}

const VB_W = 200
const VB_H = 86
/** Length of the diverging stub. Long enough to read as a route, short enough
 *  not to collide with the next turnout at 34 units of spacing. */
const FORK = 13
const FORK_RISE = 6.5

/**
 * Interlocking schematic.
 *
 * Drawn to the signalling convention rather than invented: a turnout is a fork
 * in the running line, and the route the points are *set* for is drawn solid
 * while the unset route stays dim. That is how an NX panel or a train-describer
 * display shows it, so a signaller reads it without translating.
 *
 * Position is therefore carried by geometry — which leg is live — before colour
 * is involved at all. Colour reinforces it; it is never the only channel.
 */
export function Schematic({ machines, selected, onSelect, recent }: Props) {
  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="w-full"
      role="group"
      data-schematic=""
      aria-label="Interlocking schematic. Each turnout is a point machine; the solid leg is the route the points are set for."
    >
      {/* ── Running lines ────────────────────────────────────────────────── */}
      {[30, 62].map((y) => (
        <line
          key={y}
          x1={2} x2={VB_W - 2} y1={y} y2={y}
          stroke="var(--color-line-strong)"
          strokeWidth="1"
          strokeLinecap="round"
          opacity="0.65"
        />
      ))}

      {machines.map((m) => {
        const lane = m.y < 50 ? 0 : 1
        const railY = lane === 0 ? 30 : 62
        // Lane 0 forks downward into the middle, lane 1 upward — the two routes
        // face each other the way a real crossover does.
        const dir = lane === 0 ? 1 : -1
        const labelY = lane === 0 ? railY - 10 : railY + 14
        const active = selected === m.id
        const colour = POSITION_COLOR[m.position]
        const alarm = m.severity === 'critical' || m.severity === 'warning'
        const inTransit = m.position === 'transit'
        const setNormal = m.position === 'N'
        const setReverse = m.position === 'R'

        const x0 = m.x - 4
        const divergeEnd = { x: m.x + FORK, y: railY + dir * FORK_RISE }

        return (
          <g
            key={m.id}
            onPointerDown={() => onSelect(m.id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.id) } }}
            tabIndex={0}
            data-machine-node={m.id}
            role="button"
            aria-label={`${m.id}, ${POSITION_LABEL[m.position]}, ${m.severity}, health ${(m.health.health * 100).toFixed(0)} percent, last event ${ago(m.last_event_at)} ago`}
            aria-pressed={active}
            className="cursor-pointer outline-none"
          >
            {/* Hit area — a 5px target is not clickable, let alone tappable. */}
            <rect
              x={m.x - 11} y={Math.min(railY, divergeEnd.y) - 12}
              width={26} height={30} fill="transparent"
            />

            {active && (
              <rect
                x={m.x - 10} y={Math.min(railY, divergeEnd.y) - 11}
                width={24} height={28} rx="4"
                fill="var(--color-surface-2)" opacity="0.55"
              />
            )}

            {/* Diverging leg. Solid when the points are set to Reverse. */}
            <path
              d={`M${x0},${railY} L${m.x + 3},${railY + dir * 1.2} L${divergeEnd.x},${divergeEnd.y}`}
              fill="none"
              stroke={setReverse ? colour : 'var(--color-line)'}
              strokeWidth={setReverse ? 1.7 : 0.8}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={setReverse ? 1 : 0.55}
              style={{ transition: 'stroke 240ms var(--ease-out-quint), stroke-width 240ms var(--ease-out-quint), opacity 240ms var(--ease-out-quint)' }}
            />

            {/* Through leg. Solid when the points are set to Normal. */}
            <line
              x1={x0} y1={railY} x2={m.x + FORK} y2={railY}
              stroke={setNormal ? colour : 'var(--color-line)'}
              strokeWidth={setNormal ? 1.7 : 0.8}
              strokeLinecap="round"
              opacity={setNormal ? 1 : 0.55}
              style={{ transition: 'stroke 240ms var(--ease-out-quint), stroke-width 240ms var(--ease-out-quint), opacity 240ms var(--ease-out-quint)' }}
            />

            {/* In transit: neither route is proven, so neither is drawn live.
                A hollow marker at the fork says "detection lost", which is
                exactly what a 0 V indication means. */}
            {inTransit && (
              <circle
                cx={m.x + 2} cy={railY + dir * 2} r="2.3"
                fill="none" stroke={colour} strokeWidth="0.9"
              />
            )}

            {/* Machine marker, sitting at the toe of the switch. */}
            {alarm && (
              <circle
                cx={x0} cy={railY} r="4.6"
                fill="none" strokeWidth="0.9"
                stroke={SEVERITY_COLOR[m.severity]} opacity="0.6"
                className={recent.has(m.id) ? 'attention' : ''}
              />
            )}
            <circle
              cx={x0} cy={railY} r="2.6"
              fill="var(--color-bg)"
              stroke={active ? 'var(--color-ink)' : colour}
              strokeWidth={active ? 1.3 : 1}
              style={{ transition: 'stroke 240ms var(--ease-out-quint)' }}
            />

            <text
              x={x0} y={labelY}
              textAnchor="middle" fontSize="3.6"
              fill={active ? 'var(--color-ink)' : 'var(--color-ink-faint)'}
              className="num" style={{ letterSpacing: '0.03em' }}
            >
              {m.id.replace('PMD', '')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
