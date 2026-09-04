import type { Machine } from '../lib/types'
import { POSITION_KO, POSITION_LABEL, SEVERITY_COLOR, ago, stateOf } from '../lib/format'

interface Props {
  machines: Machine[]
  selected: string | null
  onSelect: (id: string) => void
  recent: Set<string>
}

const VB_W = 1200
const VB_H = 340
/** The two running lines. */
const LANE_Y = [124, 262]
/** Turnouts span this range; column pitch is derived so any fleet size fills
 *  the width rather than bunching at the left. */
const X0 = 140
const X1 = 990
/** Geometry of one turnout, in viewBox units. */
const THROUGH = 136
const KNEE = 40
const RISE = 58

/**
 * Interlocking plan.
 *
 * Drawn to the signalling convention rather than invented: a turnout is a fork
 * in the running line, and the route the points are *set* for is drawn lit
 * while the unset leg stays dark. That is how an NX panel shows it, so a
 * signaller reads it without translating.
 *
 * Position is therefore carried by geometry — which leg is live — before colour
 * is involved at all. Colour then says condition, not position, so the two
 * never compete for the same channel.
 */
export function Schematic({ machines, selected, onSelect, recent }: Props) {
  // Lane and column come from the layout coordinates the API assigns, not from
  // the machine number: renumbering the fleet must not scramble the diagram.
  const lanes = LANE_Y.map((_, i) => machines.filter((m) => (m.y < 50 ? 0 : 1) === i).sort((a, b) => a.x - b.x))
  const cols = Math.max(1, ...lanes.map((l) => l.length))
  const pitch = cols > 1 ? (X1 - X0) / (cols - 1) : 0

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="block h-auto w-full"
      role="group" data-schematic=""
      aria-label="Interlocking plan. Each turnout is a point machine; the lit leg is the route the points are set for.">
      {/* Chainage rule along the top — an orientation aid, not data. */}
      <g stroke="var(--color-axis)" strokeWidth="1">
        <line x1="60" y1="46" x2="1160" y2="46" />
        <line x1="60" y1="40" x2="60" y2="52" />
        <line x1="610" y1="40" x2="610" y2="52" />
        <line x1="1160" y1="40" x2="1160" y2="52" />
      </g>
      <g fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9" letterSpacing="1.4">
        <text x="60" y="36">W YARD</text>
        <text x="560" y="36">PLATFORM 2</text>
        <text x="1075" y="36">E JUNCTION</text>
      </g>

      <g fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9" letterSpacing="1.4">
        <text x="0" y="128">UP MAIN</text>
        <text x="0" y="141">상선</text>
        <text x="0" y="266">DOWN MAIN</text>
        <text x="0" y="279">하선</text>
      </g>

      <g stroke="var(--color-idle)" strokeWidth="5" strokeLinecap="square">
        {LANE_Y.map((y) => <line key={y} x1="60" y1={y} x2="1160" y2={y} />)}
      </g>

      {lanes.flatMap((lane, li) =>
        lane.map((m, i) => {
          const y = LANE_Y[li]
          // Lane 0 forks downward into the middle, lane 1 upward — the two
          // routes face each other the way a real crossover does.
          const d = li === 0 ? 1 : -1
          const x = X0 + i * pitch
          const st = stateOf(m.severity)
          const colour = SEVERITY_COLOR[m.severity]
          const setN = m.position === 'N'
          const setR = m.position === 'R'
          // Neither leg is proven while the points are moving, so neither is
          // drawn lit. A 0 V indication means "detection lost", not "Normal".
          const detected = setN || setR
          const active = selected === m.id
          const alarm = st !== 'clear'

          const labelY = d > 0 ? y - 44 : y + 26
          const textY = d > 0 ? y - 31 : y + 39

          return (
            <g key={m.id}
              onPointerDown={() => onSelect(m.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.id) } }}
              tabIndex={0}
              role="button"
              data-machine-node={m.id}
              aria-pressed={active}
              aria-label={`${m.id}, ${POSITION_LABEL[m.position]}, ${st}, health ${(m.health.health * 100).toFixed(0)} percent, last throw ${ago(m.last_event_at)} ago`}
              className="cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-[var(--color-accent)]">
              {/* Hit area. A 5px stroke is not a click target, let alone a tap
                  target, so the whole turnout cell takes the press. */}
              <rect x={x - 10} y={Math.min(y, y + d * RISE) - 34} width={THROUGH + 20} height={RISE + 68}
                fill={active ? 'rgba(255,255,255,.028)' : 'transparent'} strokeWidth="1" stroke="transparent" />

              {/* Diverging leg — lit when the points are set to Reverse. */}
              <path d={`M ${x},${y} L ${x + KNEE},${y} L ${x + THROUGH},${y + d * RISE}`}
                stroke={setR ? colour : 'var(--color-idle)'} strokeWidth={setR ? 5 : 4}
                fill="none" strokeLinecap="round"
                style={{ transition: 'stroke 260ms var(--ease-out-quint), stroke-width 260ms var(--ease-out-quint)' }} />

              {/* Through leg — lit when the points are set to Normal. */}
              <path d={`M ${x},${y} L ${x + THROUGH},${y}`}
                stroke={setN ? colour : 'var(--color-idle)'} strokeWidth={setN ? 5 : 4}
                fill="none" strokeLinecap="round"
                style={{ transition: 'stroke 260ms var(--ease-out-quint), stroke-width 260ms var(--ease-out-quint)' }} />

              {alarm && (
                <circle cx={x} cy={y} r="12" fill="none" stroke={colour} strokeWidth="1" opacity="0.5"
                  className={recent.has(m.id) ? 'attention' : ''} style={{ color: colour }} />
              )}
              <circle cx={x} cy={y} r="7" fill="var(--color-bg)"
                stroke={active ? 'var(--color-ink-hi)' : colour} strokeWidth="2.5" />

              <rect x={x - 4} y={labelY} width="66" height="18" fill="var(--color-deep)"
                stroke={st === 'clear' ? 'var(--color-rule)' : colour} strokeWidth="1" />
              <text x={x + 3} y={textY} fill={st === 'clear' ? 'var(--color-ink-4)' : colour}
                fontFamily="Geist Mono, monospace" fontSize="10" fontWeight="500" letterSpacing=".5">
                {m.id}
              </text>

              {/* Position chip. Filled with the condition colour and reversed
                  out, so it reads at a glance from across a room. */}
              <rect x={x + 62} y={labelY} width="18" height="18" fill={detected ? colour : 'var(--color-idle)'} />
              <text x={x + 67} y={textY} fill={detected ? 'var(--color-bg)' : 'var(--color-label)'}
                fontFamily="Geist Mono, monospace" fontSize="10" fontWeight="700">
                {detected ? m.position : '·'}
              </text>

              <title>{`${m.id} · ${POSITION_LABEL[m.position]} ${POSITION_KO[m.position]}`}</title>
            </g>
          )
        }),
      )}
    </svg>
  )
}
