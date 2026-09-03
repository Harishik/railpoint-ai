import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Empty, Page, Section } from '../shell/Page'
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
 * else on the page explains it: what the model concluded, which measurements
 * drove that, and what a crew should do about it.
 */
export function Diagnostics() {
  const { eventId } = useParams()
  const { events } = useConsole()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<EventDetail | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  // Following the live feed is opt-in. This is a reading surface: an operator
  // opens it to study one throw, and a page that swaps the waveform out every
  // three seconds cannot be read at all.
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

  return (
    <Page
      title="Diagnostics"
      ko="파형 분석"
      lede={detail ? `Event ${detail.id} on ${detail.machine_id}, commanded to ${detail.direction}.` : undefined}
      actions={
        <div className="flex flex-wrap items-center gap-2.5">
          {!eventId && (
            <button
              onClick={() => { setFollow((f) => !f); if (!follow) setPinned(null) }}
              aria-pressed={follow}
              className="press t-label flex items-center gap-1.5 rounded-md border px-2 py-1"
              style={{
                borderColor: follow ? 'color-mix(in oklch, var(--color-normal) 45%, transparent)' : 'var(--color-line)',
                color: follow ? 'var(--color-normal)' : 'var(--color-ink-dim)',
              }}
              title={follow ? 'Following the live feed' : 'Holding on one throw'}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: follow ? 'var(--color-normal)' : 'var(--color-line-strong)' }}
              />
              {follow ? 'Following live' : 'Hold'}
            </button>
          )}
          {newer > 0 && (
            <button
              onClick={() => setPinned(latestId ?? null)}
              className="press t-label rounded-md px-2 py-1"
              style={{
                background: 'color-mix(in oklch, var(--color-transit) 16%, transparent)',
                color: 'var(--color-transit)',
              }}
            >
              {newer} newer {newer === 1 ? 'throw' : 'throws'} · show latest
            </button>
          )}
          {pred && (
          <div className="flex items-center gap-2.5">
            <span
              className="t-label rounded-full px-2.5 py-1 font-semibold"
              style={{
                background: `color-mix(in oklch, ${SEVERITY_COLOR[pred.severity]} 16%, transparent)`,
                color: SEVERITY_COLOR[pred.severity],
                boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${SEVERITY_COLOR[pred.severity]} 35%, transparent)`,
              }}
            >
              {pred.fault_en}
            </span>
            <span className="t-label text-ink-faint">{pred.fault_ko}</span>
            <span className="t-metric">{(pred.confidence * 100).toFixed(0)}<span className="t-label text-ink-faint">%</span></span>
          </div>
          )}
        </div>
      }
    >
      <Section>
        {detail ? (
          <Waveform event={detail} hoveredFeature={hovered} />
        ) : (
          <div className="h-[360px] animate-pulse rounded-lg bg-surface-2" />
        )}
      </Section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Section
          title="Evidence"
          aside={pred && (
            <span className="t-label text-ink-faint">
              {pred.set_size === 1 ? 'confident' : `${pred.set_size} candidates at 90%`}
            </span>
          )}
        >
          {detail ? (
            <>
              {pred && pred.set_size > 1 && (
                <p className="t-label mb-3 rounded-lg bg-surface-2 px-3 py-2 leading-snug text-ink-dim">
                  The model cannot separate{' '}
                  <span className="text-ink">{pred.prediction_set.map(faultLabel).join(', ')}</span>{' '}
                  at 90% coverage. Treat this as a shortlist, not a diagnosis.
                </p>
              )}
              <Evidence attributions={detail.attributions} onHover={setHovered} />
            </>
          ) : (
            <div className="h-32 animate-pulse rounded-lg bg-surface-2" />
          )}
        </Section>

        <Section title="Maintenance copilot" aside={<span className="t-label text-ink-faint">정비 보조</span>}>
          <Copilot eventId={detail?.id ?? null} />
        </Section>
      </div>

      <Section title="Recent throws" aside={<span className="t-label text-ink-faint">click to inspect</span>}>
        {events.length === 0 ? (
          <Empty>No throws recorded yet.</Empty>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {events.slice(0, 30).map((e) => (
              <li key={e.id}>
                <button
                  onClick={() => { setFollow(false); setPinned(e.id); navigate(`/events/${e.id}`) }}
                  aria-current={e.id === id}
                  className={`press t-label flex items-center gap-1.5 rounded-md border px-2 py-1 ${
                    e.id === id ? 'border-line-strong bg-surface-3 text-ink' : 'border-line text-ink-dim hover:text-ink'
                  }`}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[e.prediction.severity] }} />
                  <span className="num">{e.machine_id}</span>
                  <span className="text-ink-faint">{ago(e.ts)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  )
}
