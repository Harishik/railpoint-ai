import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { CopilotReply } from '../lib/types'

type Props = { eventId: string | null; verdict?: string; machineId?: string }

/**
 * Maintenance copilot. Turns a prediction into a work order a crew can act on.
 *
 * Two things this deliberately does not do. It does not stream a chat
 * transcript — a technician on shift wants the answer, not a conversation — and
 * it does not hide where the text came from. The source badge says whether a
 * language model wrote it or the deterministic drafter did, because a work
 * order whose provenance is unclear is one nobody should sign.
 *
 * The prototype also showed a maintenance history ("Replaced line relay on
 * PMD007 · 3d"). Nothing records that, so it is not here: a fabricated
 * maintenance record is the one thing on this page that could get someone hurt.
 */
export function Copilot({ eventId, verdict, machineId }: Props) {
  const [reply, setReply] = useState<CopilotReply | null>(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Guards against a slow reply for event A landing after the user moved to B.
  const inFlight = useRef(0)

  // A work order belongs to one event. Clear it when the event changes rather
  // than leaving the previous machine's instructions on screen.
  useEffect(() => {
    setReply(null); setError(null); setQuestion('')
  }, [eventId])

  async function ask(q?: string) {
    if (!eventId) return
    const ticket = ++inFlight.current
    setBusy(true); setError(null)
    try {
      const r = await api.copilot(eventId, q)
      if (ticket === inFlight.current) setReply(r)
    } catch {
      if (ticket === inFlight.current) setError('Could not reach the copilot service.')
    } finally {
      if (ticket === inFlight.current) setBusy(false)
    }
  }

  if (!eventId) {
    return <p className="text-[12px]" style={{ color: 'var(--color-label)' }}>Select an event to draft a work order.</p>
  }

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-col gap-[9px]">
        <span className="cap" style={{ letterSpacing: '0.13em' }}>Suggested action</span>
        <div className="px-3.5 py-3" style={{ borderLeft: '2px solid var(--color-accent)', background: 'var(--color-raised)' }}>
          {reply ? (
            <div className="max-h-[240px] overflow-y-auto whitespace-pre-wrap text-[12px] leading-[1.55]"
              style={{ color: 'var(--color-ink-2)' }}>
              {reply.answer}
            </div>
          ) : busy ? (
            <div className="h-[54px] animate-pulse" style={{ background: 'var(--color-panel)' }} />
          ) : (
            <>
              <div className="text-[13px] font-medium leading-[1.45]" style={{ color: 'var(--color-ink-2)' }}>
                {verdict && verdict !== 'Normal'
                  ? `Inspect the ${verdict.toLowerCase()} circuit on ${machineId ?? 'this machine'} before the next scheduled throw.`
                  : `No fault indicated on ${machineId ?? 'this machine'} for this throw.`}
              </div>
              <div className="mt-2 text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
                Draft a work order to have the evidence, the cited maintenance codes and the recommended
                checks written out in full.
              </div>
            </>
          )}
          {reply && reply.citations.length > 0 && (
            <p className="mt-2.5 text-[11px]" style={{ color: 'var(--color-label)' }}>
              Cited maintenance codes: {reply.citations.join(', ')}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => void ask()} disabled={busy}
          className="press inline-flex h-8 items-center px-3.5 text-[12px] font-semibold leading-none disabled:opacity-50"
          style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}>
          {busy ? 'Drafting…' : reply ? 'Redraft' : 'Draft work order'}
        </button>
        {reply && (
          <span className="mono inline-flex h-8 items-center px-2.5 text-[10px] uppercase leading-none"
            style={{ border: '1px solid var(--color-rule)', letterSpacing: '0.1em', color: 'var(--color-label)' }}
            title={reply.source === 'claude'
              ? `Written by ${reply.model}, grounded in this event's evidence`
              : 'Generated without a language model, from the same grounded evidence'}>
            {reply.source === 'claude' ? (reply.model ?? 'claude') : 'deterministic'}
          </span>
        )}
      </div>

      <div className="h-px" style={{ background: 'var(--color-edge)' }} />

      <form onSubmit={(e) => { e.preventDefault(); if (question.trim()) void ask(question.trim()) }}
        className="flex flex-col gap-[9px]">
        <label className="cap" htmlFor="copilot-q" style={{ letterSpacing: '0.13em' }}>Ask</label>
        <div className="flex" style={{ border: '1px solid var(--color-rule)', background: 'var(--color-deep)' }}>
          <input id="copilot-q" value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="무엇을 점검해야 합니까? / What should I check?"
            className="h-[34px] min-w-0 flex-1 bg-transparent px-3 text-[12px] leading-none outline-none"
            style={{ color: 'var(--color-ink-2)' }} />
          <button type="submit" disabled={busy || !question.trim()}
            className="press inline-flex h-[34px] items-center px-3.5 text-[12px] font-medium leading-none disabled:opacity-40"
            style={{ borderLeft: '1px solid var(--color-rule)', color: 'var(--color-dim)' }}>
            Ask
          </button>
        </div>
      </form>

      <div aria-live="polite" aria-busy={busy}>
        {error && <p className="text-[12px]" style={{ color: 'var(--color-accent)' }}>{error}</p>}
        {reply && (
          <p className="text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>{reply.disclaimer}</p>
        )}
      </div>
    </div>
  )
}
