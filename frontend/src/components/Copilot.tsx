import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { CopilotReply } from '../lib/types'

type Props = { eventId: string | null }

/**
 * Maintenance copilot. Turns a prediction into a work order a crew can act on.
 *
 * Two things this deliberately does NOT do. It does not stream a chat
 * transcript — a technician on shift wants the answer, not a conversation — and
 * it does not hide where the text came from. The `source` badge says whether a
 * language model wrote it or the deterministic drafter did, because a work order
 * whose provenance is unclear is one nobody should sign.
 */
export function Copilot({ eventId }: Props) {
  const [reply, setReply] = useState<CopilotReply | null>(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Guards against a slow reply for event A landing after the user has moved to B.
  const inFlight = useRef(0)

  // A work order belongs to one event. Clear it when the event changes rather
  // than leaving the previous machine's instructions on screen.
  useEffect(() => {
    setReply(null)
    setError(null)
    setQuestion('')
  }, [eventId])

  async function ask(q?: string) {
    if (!eventId) return
    const ticket = ++inFlight.current
    setBusy(true)
    setError(null)
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
    return <p className="text-[12px] text-ink-faint">Select an event to draft a work order.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void ask()}
          disabled={busy}
          className="rounded border border-line px-2.5 py-1 text-[12px] font-medium
                     text-ink transition-colors hover:bg-surface-3
                     focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent
                     disabled:opacity-50"
        >
          {busy ? 'Drafting…' : 'Draft work order'}
        </button>
        {reply && (
          <span
            className="rounded-sm border border-line px-1.5 py-0.5 text-[10px] uppercase
                       tracking-wide text-ink-faint"
            title={
              reply.source === 'claude'
                ? `Written by ${reply.model}, grounded in this event's evidence`
                : 'Generated without a language model, from the same grounded evidence'
            }
          >
            {reply.source === 'claude' ? reply.model : 'deterministic'}
          </span>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (question.trim()) void ask(question.trim())
        }}
        className="flex gap-2"
      >
        <label className="sr-only" htmlFor="copilot-q">
          Ask the maintenance copilot about this event
        </label>
        <input
          id="copilot-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="무엇을 점검해야 합니까? / What should I check?"
          className="min-w-0 flex-1 rounded border border-line bg-surface-1 px-2 py-1
                     text-[12px] text-ink placeholder:text-ink-faint
                     focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="rounded border border-line px-2.5 py-1 text-[12px] text-ink
                     transition-colors hover:bg-surface-3
                     focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent
                     disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      <div aria-live="polite" aria-busy={busy}>
        {error && <p className="text-[12px] text-state-fault">{error}</p>}
        {busy && !reply && (
          // Reserve height so the panel does not jump when the answer lands.
          <div className="min-h-[120px] animate-pulse rounded bg-surface-2" />
        )}
        {reply && (
          <div className="flex flex-col gap-2">
            <div className="max-h-[280px] overflow-y-auto whitespace-pre-wrap rounded
                            bg-surface-1 p-2.5 text-[12px] leading-relaxed text-ink">
              {reply.answer}
            </div>
            {reply.citations.length > 0 && (
              <p className="text-[11px] text-ink-faint">
                Cited maintenance codes: {reply.citations.join(', ')}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
