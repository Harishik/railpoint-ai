import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Empty, Note, Page, Panel } from '../shell/Page'
import { Waveform } from '../components/Waveform'
import { Evidence } from '../components/Evidence'
import { Copilot } from '../components/Copilot'
import { useConsole } from '../state/console'
import { api } from '../lib/api'
import type { EventDetail } from '../lib/types'
import { SEVERITY_COLOR, ago, faultLabel } from '../lib/format'

/**
 * Diagnostics — one throw, in full.
 *
 * The waveform is the reason this page exists, so it gets the width. Everything
 * else explains it: what the model concluded, which measurements drove that,
 * and what a crew should do about it.
 *
 * Following the live feed is opt-in. This is a reading surface — an operator
 * opens it to study one throw — and a page that swaps the trace out every three
 * seconds cannot be read at all. New throws are offered, never forced.
 */
export function Diagnostics() {
  const { eventId } = useParams()
  const { events, model } = useConsole()
  const sets = model?.summary?.conformal
  const navigate = useNavigate()
  const [detail, setDetail] = useState<EventDetail | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [follow, setFollow] = useState(false)
  const [pinned, setPinned] = useState<string | null>(null)

  const latestId = events[0]?.id

  // With no event in the URL, land on whatever was latest when the page opened
  // and then hold still, rather than tracking the head of the stream.
  useEffect(() => {
    if (!eventId && !pinned && latestId) setPinned(latestId)
  }, [eventId, pinned, latestId])

  const id = eventId ?? (follow ? latestId : (pinned ?? latestId))

  // How many throws have arrived since the one on screen — offered, not forced.
  const newer = (() => {
    if (eventId || follow || !pinned) return 0
    const at = events.findIndex((e) => e.id === pinned)
    return at > 0 ? at : 0
  })()

  useEffect(() => {
    if (!id) return
    let live = true
    // Deliberately not clearing `detail` first. Blanking to a skeleton on every
    // refetch is what made this page appear to reload rather than update; the
    // previous trace stays up until the new one is ready to replace it.
    void api.event(id).then((d) => { if (live) setDetail(d) }).catch(() => {})
    return () => { live = false }
  }, [id])

  const pred = detail?.prediction
  const colour = pred ? SEVERITY_COLOR[pred.severity] : 'var(--color-label)'
  const clear = pred?.severity === 'normal'

  return (
    <Page
      title="Diagnostics"
      ko="파형 분석"
      lede={detail ? (
        <>
          Event <span className="mono" style={{ color: 'var(--color-ink-4)' }}>{detail.id}</span> on{' '}
          <span className="mono" style={{ color: 'var(--color-ink-4)' }}>{detail.machine_id}</span>, commanded to{' '}
          {detail.direction}.
        </>
      ) : 'Waiting for a throw to inspect.'}
      actions={
        <div className="flex flex-wrap items-center gap-2.5">
          {!eventId && (
            <button type="button" aria-pressed={follow}
              onClick={() => { setFollow((f) => !f); if (!follow) setPinned(null) }}
              title={follow ? 'Following the live feed' : 'Holding on one throw'}
              className="press inline-flex h-[30px] items-center gap-2 px-3 text-[12px] font-medium leading-none"
              style={{
                border: `1px solid ${follow ? '#1D3A2C' : 'var(--color-rule)'}`,
                background: follow ? 'rgba(63,214,140,.07)' : 'var(--color-raised)',
                color: follow ? 'var(--color-green)' : 'var(--color-ink-4)',
              }}>
              <span aria-hidden className={`h-[5px] w-[5px] rounded-full ${follow ? 'pulse-live' : ''}`}
                style={{ background: follow ? 'var(--color-green)' : 'var(--color-rule-hi)' }} />
              {follow ? 'Following live' : 'Hold'}
            </button>
          )}
          {newer > 0 && (
            <button type="button" onClick={() => setPinned(latestId ?? null)}
              className="press inline-flex h-[30px] items-center px-3 text-[12px] font-medium leading-none"
              style={{ background: 'rgba(79,184,232,.14)', color: 'var(--color-cyan)' }}>
              {newer} newer {newer === 1 ? 'throw' : 'throws'} · show latest
            </button>
          )}
          {pred && (
            <div className="flex items-stretch"
              style={{
                border: `1px solid ${clear ? '#1D3A2C' : 'rgba(255,90,54,.3)'}`,
                background: clear ? 'rgba(63,214,140,.06)' : 'rgba(255,90,54,.05)',
              }}>
              <div className="flex flex-col gap-[5px] border-r px-[15px] py-2.5" style={{ borderColor: 'inherit' }}>
                <span className="cap" style={{ color: 'var(--color-label)' }}>Verdict</span>
                <span className="text-[14px] font-semibold leading-none" style={{ color: colour }}>{pred.fault_en}</span>
              </div>
              <div className="flex flex-col gap-[5px] border-r px-[15px] py-2.5" style={{ borderColor: 'inherit' }}>
                <span className="cap">90% set</span>
                <span className="mono text-[14px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                  {pred.set_size} {pred.set_size === 1 ? 'label' : 'labels'}
                </span>
              </div>
              <div className="flex flex-col gap-[5px] px-[15px] py-2.5">
                <span className="cap">Samples</span>
                <span className="mono text-[14px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                  {detail?.n_samples ?? '—'}
                </span>
              </div>
            </div>
          )}
        </div>
      }
    >
      {detail ? (
        <Waveform event={detail} hoveredFeature={hovered} />
      ) : (
        <div className="h-[420px] animate-pulse" style={{ background: 'var(--color-panel)' }} />
      )}

      <div className="grid items-start gap-[18px] xl:grid-cols-[1.35fr_1fr]">
        <Panel title="Evidence" flush aside={<Note>CONTRIBUTION TO VERDICT</Note>}>
          {detail ? (
            <>
              {/* A set cannot come back empty under any rule, so the only case
                  left to explain is a genuine shortlist. Under the old threshold
                  rule this never rendered — every set was one label. */}
              {pred && pred.set_size > 1 && (
                <div className="border-b px-[18px] py-3 text-[12px] leading-[1.55]"
                  style={{ borderColor: 'var(--color-hair)', borderLeft: '2px solid var(--color-amber)', color: 'var(--color-dim)' }}>
                  The model cannot separate{' '}
                  <span style={{ color: 'var(--color-ink-2)' }}>{pred.prediction_set.map(faultLabel).join(', ')}</span>{' '}
                  at 90% coverage. Treat this as a shortlist, not a diagnosis.
                  {/* The reason to take a shortlist seriously, measured rather
                      than asserted. Omitted when the artefact predates it. */}
                  {sets?.widened_lift != null && sets.error_rate_widened != null && (
                    <>
                      {' '}On held-out simulated machines, throws with a shortlist were wrong{' '}
                      <span className="mono" style={{ color: 'var(--color-amber)' }}>
                        {(sets.error_rate_widened * 100).toFixed(1)}%
                      </span>{' '}
                      of the time — {sets.widened_lift.toFixed(1)}× the average.
                    </>
                  )}
                </div>
              )}
              <Evidence attributions={detail.attributions} onHover={setHovered} />
            </>
          ) : (
            <div className="m-[18px] h-40 animate-pulse" style={{ background: 'var(--color-raised)' }} />
          )}
        </Panel>

        <Panel title="Maintenance copilot" aside={<Note>정비 보조</Note>}>
          <Copilot eventId={detail?.id ?? null} verdict={pred?.fault_en} machineId={detail?.machine_id}
            fault={pred?.fault} predictionSet={pred?.prediction_set} />
        </Panel>
      </div>

      <Panel title="Recent throws" flush aside={<Note>CLICK TO INSPECT</Note>}>
        {events.length === 0 ? (
          <Empty>No throws recorded yet.</Empty>
        ) : (
          <div className="flex flex-wrap gap-2 px-[18px] py-4">
            {events.slice(0, 30).map((e) => {
              const on = e.id === id
              return (
                <button key={e.id} type="button" aria-current={on}
                  onClick={() => { setFollow(false); setPinned(e.id); navigate(`/events/${e.id}`) }}
                  className="press inline-flex h-[30px] items-center gap-2 px-3 text-[12px] leading-none"
                  style={{
                    border: `1px solid ${on ? 'var(--color-rule-hi)' : 'var(--color-edge)'}`,
                    background: on ? 'var(--color-raised)' : 'var(--color-deep)',
                    color: on ? 'var(--color-ink)' : 'var(--color-dim)',
                  }}>
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[e.prediction.severity] }} />
                  <span className="mono">{e.machine_id}</span>
                  <span className="mono text-[11px]" style={{ color: 'var(--color-label)' }}>{ago(e.ts)}</span>
                </button>
              )
            })}
          </div>
        )}
      </Panel>
    </Page>
  )
}
