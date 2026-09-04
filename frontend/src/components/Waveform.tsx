import { useEffect, useMemo, useState } from 'react'
import type { EventDetail } from '../lib/types'
import { CHANNEL_COLOR, CHANNEL_LABEL, CHANNEL_ORDER, PHASE_KO, PHASE_LABEL, num } from '../lib/format'

/* Fixed drawing grid. The SVG scales to its container, so one viewBox unit is
   not one pixel — which is what lets the whole plate keep its proportions from
   a laptop to a wall display without a resize observer in the loop. */
const VB_W = 1200
const VB_H = 420
const L = 76
const R = 1140
const PLOT_W = R - L
const TOP = 34
const BOT = 386
/** Zero for both axes. Current is non-negative so it lives in the upper half;
 *  the indication lines are bipolar and use the full height. Sharing one zero
 *  is what lets the two be read against each other at all. */
const MID = 210
const HALF = MID - TOP

const CURRENT = 'ac_curr'
const SUPPLY = 'ac_volt'

interface Props {
  event: EventDetail
  hoveredFeature?: string | null
}

export function Waveform({ event, hoveredFeature }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(new Set(['output_r_volt']))
  const [cursor, setCursor] = useState<number | null>(null)

  // The cursor is an index into *this* event's samples, so it must not survive
  // a change of event: sample 520 of a 600-sample capture is out of range on a
  // 259-sample one, and the readout would describe a sample that is not there.
  // Channel visibility deliberately does persist — that is an operator
  // preference, not a property of the event.
  useEffect(() => { setCursor(null) }, [event.id])

  const n = event.n_samples

  // The supply rail sits at 219–230 V while the indication lines swing ±23 V.
  // Sharing one axis flattens the indication into a line at zero and hides the
  // sag, which is the part that carries the information. So the supply is
  // plotted as deviation from its own idle level and shares the bipolar axis.
  const supplyRef = useMemo(() => {
    const ch = event.channels.find((c) => c.name === SUPPLY)
    const high = (ch?.values ?? []).filter((v): v is number => v != null && v > 50)
    if (!high.length) return 0
    return [...high].sort((a, b) => b - a)[Math.floor(high.length * 0.1)] ?? high[0]
  }, [event])

  const adjust = (name: string, v: number) => (name === SUPPLY ? v - supplyRef : v)

  const { currentMax, voltMax } = useMemo(() => {
    const cur = event.channels.find((c) => c.name === CURRENT)
    const curMax = Math.max(1, ...(cur?.values ?? []).map((v) => v ?? 0))
    let vMax = 1
    for (const ch of event.channels) {
      if (ch.name === CURRENT || hidden.has(ch.name)) continue
      for (const v of ch.values) if (v != null) vMax = Math.max(vMax, Math.abs(adjust(ch.name, v)))
    }
    return { currentMax: curMax * 1.08, voltMax: vMax * 1.08 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event, hidden, supplyRef])

  const x = (i: number) => L + (i / Math.max(1, n - 1)) * PLOT_W
  // Current travels MID→TOP, the same span the positive half of the voltage
  // axis uses. Doubling it here put the peak 142 units above the plot and
  // made the left-hand axis label describe a scale the trace did not use.
  const yA = (v: number) => MID - (v / currentMax) * HALF
  const yV = (v: number) => MID - (v / voltMax) * HALF

  const traces = useMemo(
    () => CHANNEL_ORDER
      .map((name) => event.channels.find((c) => c.name === name))
      .filter((c): c is NonNullable<typeof c> => !!c && !hidden.has(c.name))
      .map((ch) => {
        const y = ch.name === CURRENT ? yA : yV
        const pts: string[] = []
        let pen = false
        ch.values.forEach((v, i) => {
          // A null is a channel that is not wired — PMD014 has no output_r at
          // all. The line breaks rather than interpolating across the gap,
          // because drawing through missing data invents readings.
          if (v == null) { pen = false; return }
          pts.push(`${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(adjust(ch.name, v)).toFixed(1)}`)
          pen = true
        })
        return {
          name: ch.name,
          d: pts.join(''),
          w: ch.name === CURRENT ? 2.2 : ch.name === 'output_n_volt' ? 1.8 : ch.name === 'as_volt' ? 1.6 : 1.4,
          op: ch.name === CURRENT || ch.name === 'output_n_volt' ? 1 : ch.name === 'as_volt' ? 0.9 : 0.8,
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [event, hidden, currentMax, voltMax, supplyRef],
  )

  // A channel with no readings anywhere is not instrumented on this machine. A
  // channel that has readings but is null *here* is a dropout in the recording
  // chain. Reporting the second as "not wired" would tell the operator the
  // machine lacks a sensor it actually has.
  const wired = useMemo(
    () => new Map(event.channels.map((c) => [c.name, c.values.some((v) => v != null)])),
    [event],
  )

  // The readout never blanks. With no cursor it reads the middle of the throw,
  // which is the part an engineer looks at first — and the last cell always
  // names the sample, so a held value can never be mistaken for a live one.
  const throwPhase = event.phases.find((p) => p.name === 'throw')
  const fallback = throwPhase
    ? Math.min(n - 1, Math.round((throwPhase.start + throwPhase.end) / 2))
    : Math.round(n / 2)
  const ci = cursor ?? fallback

  const readCell = (name: string) => {
    const ch = event.channels.find((c) => c.name === name)
    const raw = ch?.values[ci] ?? null
    if (raw == null) return wired.get(name) ? 'no data' : 'not wired'
    const v = adjust(name, raw)
    return name === CURRENT ? `${num(v, 2)} A` : `${v >= 0 ? '' : '−'}${num(Math.abs(v), 1)} V`
  }

  const readout = [
    { k: 'MOTOR CURRENT', v: readCell('ac_curr'), c: CHANNEL_COLOR.ac_curr },
    { k: 'SUPPLY Δ', v: readCell('ac_volt'), c: CHANNEL_COLOR.ac_volt },
    { k: 'DRIVE CMD', v: readCell('as_volt'), c: CHANNEL_COLOR.as_volt },
    { k: 'POSITION N', v: readCell('output_n_volt'), c: CHANNEL_COLOR.output_n_volt },
    { k: 'SAMPLE', v: `#${ci}${cursor == null ? ' · held' : ''}`, c: 'var(--color-label)' },
  ]

  // Hovering a contribution in the evidence list lights the phase it came from,
  // so an attribution can be located on the trace rather than just read.
  const litPhase = !hoveredFeature ? null
    : hoveredFeature.includes('inrush') ? 'inrush'
    : hoveredFeature.includes('throw') || hoveredFeature.includes('plateau') || hoveredFeature.includes('curr_active') ? 'throw'
    : hoveredFeature.includes('lock') ? 'lock'
    : null

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * VB_W
    const i = Math.round(((px - L) / PLOT_W) * (n - 1))
    setCursor(i >= 0 && i < n ? i : null)
  }

  const curX = x(ci)

  return (
    <div className="flex flex-col gap-[18px]">
      <div className="flex flex-wrap items-center gap-2">
        {CHANNEL_ORDER.map((name) => {
          const ch = event.channels.find((c) => c.name === name)
          if (!ch) return null
          const on = !hidden.has(name)
          return (
            <button key={name} type="button" aria-pressed={on}
              onClick={() => setHidden((s) => {
                const next = new Set(s)
                if (next.has(name)) next.delete(name); else next.add(name)
                return next
              })}
              className="press inline-flex h-[30px] items-center gap-2 px-3"
              style={{
                border: `1px solid ${on ? 'var(--color-rule)' : 'var(--color-edge)'}`,
                background: on ? 'var(--color-raised)' : 'var(--color-deep)',
                color: on ? 'var(--color-ink-2)' : 'var(--color-label)',
              }}>
              <span aria-hidden className="inline-block h-0.5 w-3.5"
                style={{ background: on ? CHANNEL_COLOR[name] : 'var(--color-tick)' }} />
              <span className="text-[12px] font-medium leading-none">{CHANNEL_LABEL[name] ?? name}</span>
              <span className="mono text-[10px] leading-none" style={{ color: 'var(--color-label)' }}>{ch.unit}</span>
            </button>
          )
        })}
        <div className="flex-1" />
        <span className="mono text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
          {cursor == null ? 'MOVE ACROSS THE TRACE TO READ PER-SAMPLE VALUES' : `SAMPLE #${ci} OF ${n}`}
        </span>
      </div>

      <div className="panel-deep">
        <div className="grid grid-cols-5 border-b" style={{ borderColor: 'var(--color-edge)', background: 'var(--color-panel)' }}>
          {readout.map((r) => (
            <div key={r.k} className="flex flex-col gap-[5px] border-r px-[15px] py-[11px]" style={{ borderColor: 'var(--color-edge)' }}>
              <span className="mono text-[9px] font-medium leading-none" style={{ letterSpacing: '0.13em', color: r.c }}>{r.k}</span>
              <span className="mono text-[14px] font-medium leading-none" style={{ color: 'var(--color-ink)' }}>{r.v}</span>
            </div>
          ))}
        </div>

        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="block h-auto w-full cursor-crosshair"
          onMouseMove={onMove} onMouseLeave={() => setCursor(null)}
          role="img"
          aria-label={`Waveform for event ${event.id} on ${event.machine_id}: ${n} samples across ${event.channels.length} channels, predicted ${event.prediction.fault_en}.`}>
          {/* Phase bands: the same decomposition the feature model uses, so the
              operator is shown the model's own reasoning frame rather than a
              chart drawn beside it. */}
          {event.phases.map((p) => {
            const px = x(p.start)
            const lit = litPhase === p.name
            const tint = p.name === 'inrush' ? 'rgba(79,184,232,.05)' : p.name === 'lock' ? 'rgba(63,214,140,.05)' : 'transparent'
            return (
              <g key={p.name}>
                <rect x={px} y={TOP} width={Math.max(0, x(p.end) - px)} height={BOT - TOP}
                  fill={lit ? 'rgba(255,90,54,.09)' : tint}
                  style={{ transition: 'fill 180ms var(--ease-out-quint)' }} />
                <line x1={px} y1={TOP} x2={px} y2={BOT} stroke="var(--color-axis)" strokeWidth="1" strokeDasharray="3 3" />
                <text x={px + 6} y="26" fill={lit ? 'var(--color-accent)' : 'var(--color-label)'}
                  fontFamily="Geist Mono, monospace" fontSize="9.5" letterSpacing="1.6">
                  {PHASE_LABEL[p.name]}{PHASE_KO[p.name] ? ` ${PHASE_KO[p.name]}` : ''}
                </text>
                <text x={px + 6} y="404" fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9">
                  {p.start}–{p.end}
                </text>
              </g>
            )
          })}

          <g stroke="var(--color-grid)" strokeWidth="1">
            {[TOP, 122, MID, 298, BOT].map((y) => <line key={y} x1={L} y1={y} x2={R} y2={y} />)}
          </g>

          <g fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9.5" textAnchor="end">
            <text x="68" y="38">{num(currentMax, 1)}</text>
            <text x="68" y="214">0</text>
          </g>
          <g fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9.5">
            <text x="1150" y="38">+{num(voltMax, 0)}</text>
            <text x="1150" y="214">0</text>
            <text x="1150" y="390">−{num(voltMax, 0)}</text>
          </g>
          <text x={L} y="418" fill="var(--color-label)" fontFamily="Geist Mono, monospace" fontSize="9">
            A ← motor current · supply shown as deviation from {num(supplyRef, 0)} V idle · volts →
          </text>

          {traces.map((t) => (
            <path key={t.name} d={t.d} fill="none" stroke={CHANNEL_COLOR[t.name]} strokeWidth={t.w}
              strokeLinejoin="round" strokeLinecap="round" opacity={t.op} className="trace-in"
              style={{ ['--len' as string]: 6000, ['--dur' as string]: `${Math.min(620, n * 1.6)}ms` }} />
          ))}

          <g>
            <line x1={curX} y1={TOP} x2={curX} y2={BOT}
              stroke={cursor == null ? 'var(--color-rule-hi)' : 'var(--color-accent)'} strokeWidth="1"
              strokeDasharray={cursor == null ? '2 4' : undefined} />
            {cursor != null && (
              <>
                <rect x={Math.min(R - 52, curX - 26)} y={TOP} width="52" height="17" fill="var(--color-accent)" />
                <text x={Math.min(R - 44, curX - 18)} y={TOP + 12} fill="var(--color-bg)"
                  fontFamily="Geist Mono, monospace" fontSize="10" fontWeight="600">#{ci}</text>
              </>
            )}
          </g>
        </svg>
      </div>
    </div>
  )
}
