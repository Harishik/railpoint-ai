import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { EventDetail } from '../lib/types'
import { CHANNEL_COLOR, CHANNEL_LABEL, PHASE_LABEL, num } from '../lib/format'

const H = 360
const MIN_W = 480
const PAD = { top: 16, right: 56, bottom: 26, left: 52 }

/** Current sits on its own axis; the four voltage channels share the other. */
const CURRENT = 'ac_curr'
const SUPPLY = 'ac_volt'

interface Props {
  event: EventDetail
  hoveredFeature?: string | null
}

type Scale = (v: number) => number

export function Waveform({ event, hoveredFeature }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(new Set(['output_r_volt']))
  const [cursor, setCursor] = useState<number | null>(null)

  // The cursor is an index into *this* event's samples, so it must not survive a
  // change of event: sample 520 of a 600-sample capture is out of range on a
  // 259-sample one, and the readout would describe a sample that is not there.
  // Channel visibility deliberately does persist - that is an operator
  // preference, not a property of the event.
  useEffect(() => { setCursor(null) }, [event.id])
  const svgRef = useRef<SVGSVGElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  // The viewBox width tracks the measured container width so one SVG unit is
  // one CSS pixel. Deriving height from width via aspect-ratio instead sets up a
  // feedback loop inside an overflow-auto parent - a scrollbar changes the
  // width, which changes the height, which toggles the scrollbar - and that
  // wedges the renderer. Height is fixed; only width is measured.
  const [W, setW] = useState(1000)
  useLayoutEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const next = Math.max(MIN_W, Math.round(entry.contentRect.width))
      setW((cur) => (Math.abs(cur - next) > 2 ? next : cur))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const n = event.n_samples
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom

  // The supply rail sits at 219-230 V while the indication lines swing +-23 V.
  // Sharing one axis flattens the indication into a line at zero and hides the
  // sag, which is the part that actually carries information. So the supply is
  // plotted as *deviation from its own idle level* and shares the bipolar axis.
  const supplyRef = useMemo(() => {
    const ch = event.channels.find((c) => c.name === SUPPLY)
    const high = (ch?.values ?? []).filter((v): v is number => v != null && v > 50)
    if (!high.length) return 0
    return [...high].sort((a, b) => b - a)[Math.floor(high.length * 0.1)] ?? high[0]
  }, [event])

  const adjust = (name: string, v: number) => (name === SUPPLY ? v - supplyRef : v)

  const { currentMax, voltAbsMax } = useMemo(() => {
    const cur = event.channels.find((c) => c.name === CURRENT)
    const curMax = Math.max(1, ...(cur?.values ?? []).map((v) => (v == null ? 0 : v)))
    let vMax = 1
    for (const ch of event.channels) {
      if (ch.name === CURRENT || hidden.has(ch.name)) continue
      for (const v of ch.values) if (v != null) vMax = Math.max(vMax, Math.abs(adjust(ch.name, v)))
    }
    return { currentMax: curMax * 1.12, voltAbsMax: vMax * 1.12 }
  }, [event, hidden, supplyRef])

  const x: Scale = (i) => PAD.left + (i / Math.max(1, n - 1)) * plotW
  const yCurrent: Scale = (v) => PAD.top + plotH - (v / currentMax) * plotH
  // Voltage is bipolar and its sign is the machine's state, so zero must sit in
  // the middle of the axis rather than at the bottom.
  const yVolt: Scale = (v) => PAD.top + plotH / 2 - (v / voltAbsMax) * (plotH / 2)

  const paths = useMemo(
    () =>
      event.channels
        .filter((c) => !hidden.has(c.name))
        .map((ch) => {
          const y = ch.name === CURRENT ? yCurrent : yVolt
          let d = ''
          let pen = false
          ch.values.forEach((v, i) => {
            // A null is a channel that is not wired (PMD014 has no output_r at
            // all). The line breaks rather than interpolating across the gap,
            // because drawing through missing data invents readings.
            if (v == null) { pen = false; return }
            d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(adjust(ch.name, v)).toFixed(1)}`
            pen = true
          })
          return { name: ch.name, unit: ch.unit, d }
        }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [event, hidden, currentMax, voltAbsMax, supplyRef, W],
  )

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = ((e.clientX - rect.left) / rect.width) * W
    const i = Math.round(((px - PAD.left) / plotW) * (n - 1))
    setCursor(i >= 0 && i < n ? i : null)
  }

  // A channel with no readings anywhere is not instrumented on this machine
  // (PMD014 has no output_r wiring at all). A channel that has readings but is
  // null *here* is a dropout in the recording chain. Reporting the second as
  // "not wired" tells the operator the machine lacks a sensor it actually has.
  const wired = useMemo(
    () => new Map(event.channels.map((c) => [c.name, c.values.some((v) => v != null)])),
    [event],
  )

  const readout = cursor == null ? null : event.channels.map((c) => ({
    name: c.name,
    unit: c.unit,
    value: c.values[cursor] ?? null,
    wired: wired.get(c.name) ?? false,
    delta: c.name === SUPPLY && c.values[cursor] != null ? c.values[cursor]! - supplyRef : null,
  }))

  // Evidence highlighting: hovering a contribution lights the phase it came from.
  const phaseForFeature = (f?: string | null) =>
    !f ? null
      : f.includes('inrush') ? 'inrush'
      : f.includes('throw') || f.includes('plateau') ? 'throw'
      : f.includes('lock') ? 'lock'
      : f.includes('in_transit') || f.includes('drive') || f.includes('ind') ? null
      : null
  const litPhase = phaseForFeature(hoveredFeature)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {event.channels.map((ch) => {
          const off = hidden.has(ch.name)
          return (
            <button
              key={ch.name}
              onClick={() =>
                setHidden((s) => {
                  const next = new Set(s)
                  next.has(ch.name) ? next.delete(ch.name) : next.add(ch.name)
                  return next
                })
              }
              aria-pressed={!off}
              className="group flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px] transition-colors duration-150"
              style={{
                borderColor: off ? 'var(--color-line)' : CHANNEL_COLOR[ch.name],
                color: off ? 'var(--color-ink-faint)' : 'var(--color-ink)',
                background: off ? 'transparent' : 'color-mix(in oklch, ' + CHANNEL_COLOR[ch.name] + ' 12%, transparent)',
              }}
            >
              <span className="h-0.5 w-3 rounded-full" style={{ background: off ? 'var(--color-line-strong)' : CHANNEL_COLOR[ch.name] }} />
              {CHANNEL_LABEL[ch.name] ?? ch.name}
              <span className="num text-[11px] opacity-60">{ch.unit}</span>
            </button>
          )
        })}
      </div>

      <div ref={boxRef} className="w-full overflow-hidden">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        // shrink-0 matters: as a flex child the SVG was otherwise compressed to
        // a third of its height, which made the trace unreadable.
        className="shrink-0 touch-none select-none"
        width={W}
        height={H}
        style={{ display: 'block' }}
        onMouseMove={onMove}
        onMouseLeave={() => setCursor(null)}
        role="img"
        aria-label={`Waveform for event ${event.id} on ${event.machine_id}: ${event.n_samples} samples across ${event.channels.length} channels, predicted ${event.prediction.fault_en}.`}
      >
        {/* Phase bands: the same decomposition the feature model uses, so the
            operator sees the model's own reasoning frame. */}
        {event.phases.map((p) => {
          const lit = litPhase === p.name
          return (
            <g key={p.name}>
              <rect
                x={x(p.start)} y={PAD.top} width={Math.max(0, x(p.end) - x(p.start))} height={plotH}
                fill={lit ? 'color-mix(in oklch, var(--color-transit) 16%, transparent)' : 'var(--color-surface-2)'}
                opacity={p.name.startsWith('idle') ? 0.35 : 0.6}
                style={{ transition: 'fill 180ms var(--ease-out-quint)' }}
              />
              {!p.name.startsWith('idle') && (
                <text
                  x={(x(p.start) + x(p.end)) / 2} y={PAD.top + 12}
                  textAnchor="middle" fontSize="10"
                  fill={lit ? 'var(--color-transit)' : 'var(--color-ink-faint)'}
                  className="font-medium"
                >
                  {PHASE_LABEL[p.name]}
                </text>
              )}
            </g>
          )
        })}

        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={PAD.left} x2={W - PAD.right}
            y1={PAD.top + plotH * f} y2={PAD.top + plotH * f}
            stroke="var(--grid)" strokeWidth="1" />
        ))}
        {/* Zero line for the bipolar voltage axis — the indication's 0 V state. */}
        <line x1={PAD.left} x2={W - PAD.right} y1={yVolt(0)} y2={yVolt(0)}
          stroke="var(--color-line-strong)" strokeWidth="1" strokeDasharray="3 3" />

        {paths.map((p) => (
          <path
            key={p.name} d={p.d} fill="none"
            stroke={CHANNEL_COLOR[p.name]}
            strokeWidth={p.name === CURRENT ? 1.9 : 1.2}
            strokeLinejoin="round" strokeLinecap="round"
            opacity={p.name === CURRENT ? 1 : 0.85}
            className="trace-in"
            style={{ ['--len' as string]: 4000, ['--dur' as string]: `${Math.min(600, n * 1.1)}ms` }}
          />
        ))}

        {cursor != null && (
          <line x1={x(cursor)} x2={x(cursor)} y1={PAD.top} y2={PAD.top + plotH}
            stroke="var(--color-ink-dim)" strokeWidth="1" />
        )}

        <text x={PAD.left - 8} y={PAD.top + 9} textAnchor="end" fontSize="10" fill="var(--color-ink-faint)" className="num">
          {num(currentMax, 1)}A
        </text>
        <text x={PAD.left - 8} y={PAD.top + plotH} textAnchor="end" fontSize="10" fill="var(--color-ink-faint)" className="num">0</text>
        <text x={W - PAD.right + 8} y={PAD.top + 9} fontSize="10" fill="var(--color-ink-faint)" className="num">
          +{num(voltAbsMax, 0)}V
        </text>
        <text x={W - PAD.right + 8} y={yVolt(0) + 3} fontSize="10" fill="var(--color-ink-faint)" className="num">0</text>
        <text x={W - PAD.right + 8} y={PAD.top + plotH} fontSize="10" fill="var(--color-ink-faint)" className="num">
          -{num(voltAbsMax, 0)}V
        </text>
        <text x={PAD.left} y={H - 8} fontSize="10" fill="var(--color-ink-faint)">
          supply shown as deviation from {num(supplyRef, 0)} V idle
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize="10" fill="var(--color-ink-faint)" className="num">
          {n} samples
        </text>
      </svg>
      </div>

      <div className="flex min-h-[26px] flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
        {readout ? (
          <>
            <span className="num text-ink-dim">sample {cursor}</span>
            {readout.map((r) => (
              <span key={r.name} className="flex items-center gap-1.5">
                <span className="h-0.5 w-2.5 rounded-full" style={{ background: CHANNEL_COLOR[r.name] }} />
                <span className="text-ink-faint">{CHANNEL_LABEL[r.name]}</span>
                <span className="num">
                  {r.value == null ? (r.wired ? 'no data' : 'not wired') : `${num(r.value)} ${r.unit}`}
                  {r.delta != null && <span className="text-ink-faint"> ({r.delta >= 0 ? '+' : ''}{num(r.delta, 1)})</span>}
                </span>
              </span>
            ))}
          </>
        ) : (
          <span className="text-ink-faint">Move across the trace to read per-sample values.</span>
        )}
      </div>
    </div>
  )
}
