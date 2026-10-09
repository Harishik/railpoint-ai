import { useEffect, useRef, useState } from 'react'
import { api, HttpError } from '../lib/api'
import type { CopilotModels, CopilotReply } from '../lib/types'
import { faultLabel } from '../lib/format'

type Props = {
  eventId: string | null
  verdict?: string
  machineId?: string
  /** The model's top class and its 90% prediction set, as class codes. */
  fault?: string
  predictionSet?: string[]
}

/**
 * Maintenance copilot. Turns a prediction into a work order a crew can act on.
 *
 * Two things this deliberately does not do. It does not stream a chat
 * transcript — a technician on shift wants the answer, not a conversation — and
 * it does not hide where the text came from. The source badge names the model
 * that wrote it, or says the deterministic drafter did and why, because a work
 * order whose provenance is unclear is one nobody should sign.
 *
 * Drafts come from a local model through Ollama by default, and the panel lets
 * the reader pick any model installed there: they cost nothing per token. When
 * the operator configures Claude instead, there is nothing to pick.
 *
 * The prototype also showed a maintenance history ("Replaced line relay on
 * PMD007 · 3d"). Nothing records that, so it is not here: a fabricated
 * maintenance record is the one thing on this page that could get someone hurt.
 */
export function Copilot({ eventId, verdict, machineId, fault, predictionSet }: Props) {
  const [reply, setReply] = useState<CopilotReply | null>(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [menu, setMenu] = useState<CopilotModels | null>(null)
  const [model, setModel] = useState<string | null>(null)
  // Guards against a slow reply for event A landing after the user moved to B.
  const inFlight = useRef(0)

  useEffect(() => {
    api.copilotModels().then((m) => {
      setMenu(m)
      const kept = readChoice()
      setModel(kept && m.models.some((x) => x.name === kept) ? kept : m.default)
    }, () => setMenu(null))
  }, [])

  // A work order belongs to one event. Clear it when the event changes rather
  // than leaving the previous machine's instructions on screen — and retire any
  // draft still in flight, which with a local model can be a minute away.
  useEffect(() => {
    inFlight.current++
    setReply(null); setError(null); setQuestion(''); setBusy(false)
  }, [eventId])

  const local = menu?.provider === 'ollama' && model !== null

  async function ask(q?: string) {
    if (!eventId) return
    const ticket = ++inFlight.current
    setBusy(true); setError(null)
    try {
      const r = await api.copilot(eventId, q, local ? model : undefined)
      if (ticket === inFlight.current) setReply(r)
    } catch (e) {
      if (ticket === inFlight.current) {
        // A refusal (say, a model removed from Ollama since the menu loaded)
        // has a reason worth showing; anything else is an outage.
        setError(e instanceof HttpError && e.status < 500 ? e.message : 'Could not reach the copilot service.')
      }
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
            <div className="flex h-[54px] animate-pulse items-center px-3 text-[11px]"
              style={{ background: 'var(--color-panel)', color: 'var(--color-label)' }}>
              {local ? `${model} is writing on this machine. Local drafts take a minute or two.` : null}
            </div>
          ) : (
            <>
              <div className="text-[13px] font-medium leading-[1.45]" style={{ color: 'var(--color-ink-2)' }}>
                {suggestion(machineId ?? 'this machine', verdict, fault, predictionSet)}
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
        {menu?.provider === 'ollama' && menu.models.length > 0 && (
          <label className="inline-flex h-8 items-center" title="Local models installed in Ollama">
            <span className="sr-only">Copilot model</span>
            <select value={model ?? ''} disabled={busy}
              onChange={(e) => { setModel(e.target.value); keepChoice(e.target.value) }}
              className="mono h-8 max-w-[190px] px-2 text-[11px] leading-none outline-none disabled:opacity-50"
              style={{ border: '1px solid var(--color-rule)', background: 'var(--color-deep)', color: 'var(--color-ink-2)' }}>
              {menu.models.map((m) => (
                <option key={m.name} value={m.name}>{m.name} · {m.size_gb} GB</option>
              ))}
            </select>
          </label>
        )}
        {reply && (
          <span className="mono inline-flex h-8 items-center px-2.5 text-[10px] uppercase leading-none"
            style={{ border: '1px solid var(--color-rule)', letterSpacing: '0.1em', color: 'var(--color-label)' }}
            title={badgeTitle(reply)}>
            {reply.source === 'deterministic' ? 'deterministic' : `${reply.source} · ${reply.model ?? ''}`}
          </span>
        )}
      </div>
      {menu?.unavailable && !reply && (
        <p className="-mt-1.5 text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
          No language model available ({menu.unavailable}). Drafts will come from the deterministic writer.
        </p>
      )}

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
        {reply?.fallback_reason && (
          <p className="text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
            Written without a language model: {reply.fallback_reason}.
          </p>
        )}
        {reply && (
          <p className="text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>{reply.disclaimer}</p>
        )}
      </div>
    </div>
  )
}

function badgeTitle(r: CopilotReply): string {
  if (r.source === 'ollama') return `Written on this machine by ${r.model} (Ollama), grounded in this event's evidence`
  if (r.source === 'claude') return `Written by ${r.model}, grounded in this event's evidence`
  return 'Generated without a language model, from the same grounded evidence' +
    (r.fallback_reason ? ` (${r.fallback_reason})` : '')
}

// The model choice is a per-reader convenience, so it lives in this browser.
// Storage can be unavailable (private windows, blocked site data); that only
// means the choice is forgotten.
const CHOICE_KEY = 'railpoint.copilot.model'
function readChoice(): string | null {
  try { return localStorage.getItem(CHOICE_KEY) } catch { return null }
}
function keepChoice(name: string) {
  try { localStorage.setItem(CHOICE_KEY, name) } catch { /* forgotten, not broken */ }
}

/**
 * The one-line action shown before a work order is drafted.
 *
 * It used to read only the top-1 verdict, so a throw whose prediction set was
 * {Normal, supply undervoltage} — the evidence panel beside it saying the model
 * cannot rule the fault out — was summarised here as "No fault indicated".
 * That is the sentence that sends a crew away from a faulty machine. When the
 * set holds more than one label, the action says so and names what is open.
 */
function suggestion(machine: string, verdict?: string, fault?: string, set?: string[]): string {
  const others = (set ?? []).filter((c) => c !== fault).map(faultLabel)
  if (others.length > 0) {
    const leaning = verdict && verdict !== 'Normal' ? verdict.toLowerCase() : 'no fault'
    return `Not conclusive on ${machine}: the model leans towards ${leaning} but cannot rule out ` +
      `${others.join(', ')} at 90% coverage. Check before the next scheduled throw.`
  }
  return verdict && verdict !== 'Normal'
    ? `Inspect the ${verdict.toLowerCase()} circuit on ${machine} before the next scheduled throw.`
    : `No fault indicated on ${machine} for this throw.`
}
