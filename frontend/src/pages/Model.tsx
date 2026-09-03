import { useEffect, useState } from 'react'
import { Empty, Page, Section } from '../shell/Page'
import { api } from '../lib/api'
import type { ModelCard } from '../lib/types'
import { faultLabel } from '../lib/format'

/**
 * Model — what is serving, how well it does, and where it does not.
 *
 * Read from the experiment artefacts rather than restated here, so the page
 * cannot drift from the run that produced it. It deliberately leads with the
 * result that does *not* flatter: a console that only shows its best number is
 * how the 2024 version came to report ">90% accuracy" for a system with no
 * model in it.
 */
export function Model() {
  const [card, setCard] = useState<ModelCard | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    void api.model().then(setCard).catch(() => setError(true))
  }, [])

  if (error) return <Page title="Model"><Section><Empty>Could not load the model card.</Empty></Section></Page>
  if (!card) {
    return (
      <Page title="Model" ko="모델">
        <div className="h-40 animate-pulse rounded-xl bg-surface-2" />
      </Page>
    )
  }

  const s = card.summary
  const acc = s?.acceptance
  const weakest = [...card.per_class]
    .sort((a, b) => Number(a.f1) - Number(b.f1))
    .slice(0, 5)

  return (
    <Page
      title="Model"
      ko="모델"
      lede="PointMachineNet — a 1D-CNN stem into a Transformer encoder, with fault, RUL and anomaly heads. Every figure here is read from the training run's own artefacts."
      actions={
        <span
          className="t-label rounded-full px-2.5 py-1 font-semibold"
          style={{
            background: `color-mix(in oklch, ${card.serving.degraded ? 'var(--color-fault)' : 'var(--color-normal)'} 16%, transparent)`,
            color: card.serving.degraded ? 'var(--color-fault)' : 'var(--color-normal)',
          }}
        >
          {card.serving.degraded ? 'degraded' : card.serving.source} · {card.serving.version}
        </span>
      }
    >
      {/* The honest headline first. */}
      {acc && (
        <Section title="Real-data acceptance test" aside={<span className="t-label text-ink-faint">the number that matters</span>}>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              <div className="t-display" style={{ color: acc.passed ? 'var(--color-normal)' : 'var(--color-degraded)' }}>
                {acc.diagnostic_correct}<span className="text-ink-faint">/{acc.diagnostic_total}</span>
              </div>
              <div className="t-label mt-1 text-ink-faint">scoreable real faults identified</div>
            </div>
            <div>
              <div className="t-metric">{acc.all_correct}<span className="text-ink-faint">/7</span></div>
              <div className="t-label mt-1 text-ink-faint">all real events labelled correctly</div>
            </div>
            <div>
              <div className="t-metric">{acc.expected_in_conformal_set}<span className="text-ink-faint">/7</span></div>
              <div className="t-label mt-1 text-ink-faint">true label inside the 90% set</div>
            </div>
          </div>

          <p className="t-label mt-4 rounded-lg bg-surface-2 px-3 py-2.5 leading-relaxed text-ink-dim">
            These are the seven genuine Sehwa captures, never trained on. <span className="text-ink">The test is
            not fully independent</span>: the E01 fault parameters were tuned to match the two PMD055 events it
            scores, and the simulator's healthy reference is the four PMD014 events it expects to read Normal.
            Read it as “the simulator reproduces these traces well enough for the model to recognise them”, not
            as field validation.
          </p>

          {card.acceptance.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse">
                <thead>
                  <tr className="t-micro text-left text-ink-faint">
                    <th className="pb-2 font-semibold">Event</th>
                    <th className="pb-2 font-semibold">Expected</th>
                    <th className="pb-2 font-semibold">Predicted</th>
                    <th className="pb-2 text-right font-semibold">Set size</th>
                    <th className="pb-2 text-right font-semibold">Correct</th>
                  </tr>
                </thead>
                <tbody>
                  {card.acceptance.map((r) => {
                    const ok = String(r.correct).toLowerCase() === 'true'
                    return (
                      <tr key={r.event} className="border-t border-line/60">
                        <td className="num t-label py-1.5">{r.event}</td>
                        <td className="t-label py-1.5 text-ink-dim">{faultLabel(r.expected)}</td>
                        <td className="t-label py-1.5" style={{ color: ok ? 'var(--color-normal)' : 'var(--color-degraded)' }}>
                          {faultLabel(r.predicted)}
                        </td>
                        <td className="num t-label py-1.5 text-right text-ink-dim">{r.set_size}</td>
                        <td className="t-label py-1.5 text-right" style={{ color: ok ? 'var(--color-normal)' : 'var(--color-degraded)' }}>
                          {ok ? 'yes' : 'no'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {s && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Accuracy" ko="정확도" value={`${(s.test.accuracy * 100).toFixed(1)}%`}
            note={`balanced ${(s.test.balanced_acc * 100).toFixed(1)}%`} />
          <Metric label="Macro F1" ko="거시 F1" value={s.test.macro_f1.toFixed(3)}
            note={`${card.per_class.length} classes, held-out machines`} />
          <Metric label="Anomaly ROC-AUC" ko="이상 탐지" value={s.anomaly.roc_auc.toFixed(3)}
            note={`positive rate ${(s.anomaly.positive_rate * 100).toFixed(0)}%`} />
          <Metric label="RUL error" ko="잔여수명 오차" value={`${s.rul.rmse.toFixed(0)}`}
            note={`throws RMSE · ${(s.rul.coverage * 100).toFixed(0)}% interval coverage`} />
        </div>
      )}

      {s && (
        <Section title="Conformal calibration" aside={<span className="t-label text-ink-faint">등각 예측</span>}>
          <div className="flex flex-wrap gap-x-10 gap-y-3">
            <Stat label="Target coverage" value={`${((1 - s.conformal.alpha) * 100).toFixed(0)}%`} />
            <Stat label="Empirical coverage" value={`${(s.conformal.coverage * 100).toFixed(1)}%`} />
            <Stat label="Mean set size" value={s.conformal.mean_set_size.toFixed(3)} />
            <Stat label="Parameters" value={s.params.toLocaleString()} />
          </div>
          {s.conformal.mean_set_size < 1 && (
            <p className="t-label mt-3 rounded-lg px-3 py-2 leading-relaxed"
              style={{ background: 'color-mix(in oklch, var(--color-degraded) 12%, transparent)', color: 'var(--color-ink-dim)' }}>
              <span className="font-semibold" style={{ color: 'var(--color-degraded)' }}>Known defect. </span>
              A mean set size below 1 means some events receive an <span className="text-ink">empty</span>{' '}
              prediction set — the conformal threshold has collapsed. Calibration currently shares the
              validation split used for early stopping, which breaks the exchangeability the guarantee rests on.
            </p>
          )}
        </Section>
      )}

      <Section title="Where it is weakest" aside={<span className="t-label text-ink-faint">lowest F1 first</span>}>
        {weakest.length === 0 ? <Empty>No per-class results available.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse">
              <thead>
                <tr className="t-micro text-left text-ink-faint">
                  <th className="pb-2 font-semibold">Class</th>
                  <th className="pb-2 text-right font-semibold">Precision</th>
                  <th className="pb-2 text-right font-semibold">Recall</th>
                  <th className="pb-2 text-right font-semibold">F1</th>
                  <th className="pb-2 text-right font-semibold">Support</th>
                </tr>
              </thead>
              <tbody>
                {weakest.map((c) => (
                  <tr key={c.class} className="border-t border-line/60">
                    <td className="t-label py-1.5">{faultLabel(c.class)}</td>
                    <td className="num t-label py-1.5 text-right">{Number(c.precision).toFixed(3)}</td>
                    <td className="num t-label py-1.5 text-right">{Number(c.recall).toFixed(3)}</td>
                    <td className="num t-label py-1.5 text-right"
                      style={{ color: Number(c.f1) < 0.6 ? 'var(--color-degraded)' : undefined }}>
                      {Number(c.f1).toFixed(3)}
                    </td>
                    <td className="num t-label py-1.5 text-right text-ink-faint">{c.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {card.metropt && (
        <Section title="Real field data — MetroPT-3" aside={<span className="t-label text-ink-faint">UCI 791, CC BY 4.0</span>}>
          <div className="flex flex-wrap gap-x-10 gap-y-3">
            <Stat label="ROC-AUC" value={String(card.metropt.roc_auc)} />
            <Stat label="Precision@100" value={String(card.metropt.precision_at_100)} />
            <Stat label="Windows" value={Number(card.metropt.windows).toLocaleString()} />
            <Stat label="Documented failures" value={String(card.metropt.documented_failures)} />
          </div>
          <p className="t-label mt-3 rounded-lg bg-surface-2 px-3 py-2.5 leading-relaxed text-ink-dim">
            The only data here nobody generated for this project. Read the two numbers together: the AUC is
            real, but <span className="text-ink">precision@100 is zero</span> —{' '}
            {String(card.metropt.normal_windows_above_failure_max)} normal windows outscore the highest failure
            window. A team told to investigate the top 100 alarms would find none of the four documented
            failures. AUC flatters a detector that could not be used as an alarm list.
          </p>
        </Section>
      )}
    </Page>
  )
}

function Metric({ label, ko, value, note }: { label: string; ko: string; value: string; note: string }) {
  return (
    <Section title={label} aside={<span className="t-label text-ink-faint">{ko}</span>}>
      <div className="t-display">{value}</div>
      <div className="t-label mt-1 text-ink-faint">{note}</div>
    </Section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="t-micro text-ink-faint">{label}</div>
      <div className="t-metric mt-1">{value}</div>
    </div>
  )
}
