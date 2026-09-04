import { Callout, Empty, Note, Page, Panel } from '../shell/Page'
import { useConsole } from '../state/console'
import { faultLabel } from '../lib/format'

/**
 * Model — what is serving, how well it does, and where it does not.
 *
 * Read from the experiment artefacts rather than restated here, so the page
 * cannot drift from the run that produced it. It deliberately leads with the
 * result that does *not* flatter: a console that only shows its best number is
 * how the 2024 version came to report ">90% accuracy" for a system that
 * contained no model at all.
 */
export function Model() {
  const { model: card } = useConsole()

  if (!card) {
    return (
      <Page title="Model" ko="모델">
        <div className="h-64 animate-pulse" style={{ background: 'var(--color-panel)' }} />
      </Page>
    )
  }

  const s = card.summary
  const acc = s?.acceptance
  const weakest = [...card.per_class].sort((a, b) => Number(a.f1) - Number(b.f1)).slice(0, 5)
  const metro = card.metropt
  const degraded = card.serving.degraded

  return (
    <Page
      title="Model"
      ko="모델"
      lede="PointMachineNet — a 1D-CNN stem into a Transformer encoder, with fault, RUL and anomaly heads. Every figure here is read from the training run's own artefacts."
      actions={
        <div className="flex h-[30px] items-center gap-2 px-3"
          style={{
            border: `1px solid ${degraded ? 'rgba(255,90,54,.3)' : '#1D3A2C'}`,
            background: degraded ? 'rgba(255,90,54,.06)' : 'rgba(63,214,140,.07)',
          }}>
          <span aria-hidden className="h-[5px] w-[5px] rounded-full"
            style={{ background: degraded ? 'var(--color-accent)' : 'var(--color-green)' }} />
          <span className="mono text-[11px] leading-none" style={{ color: degraded ? 'var(--color-accent)' : 'var(--color-green)' }}>
            {degraded ? 'degraded' : card.serving.source} · {card.serving.version}
          </span>
        </div>
      }
    >
      {acc && (
        <Panel title="Real-data acceptance test" flush aside={<Note tone="accent">THE NUMBER THAT MATTERS</Note>}>
          <div className="grid border-b sm:grid-cols-3" style={{ borderColor: 'var(--color-edge)' }}>
            {[
              { n: acc.diagnostic_correct, d: acc.diagnostic_total, l: 'scoreable real faults identified', c: acc.passed ? 'var(--color-green)' : 'var(--color-amber)' },
              { n: acc.all_correct, d: 7, l: 'all real events labelled correctly', c: 'var(--color-ink-hi)' },
              { n: acc.expected_in_conformal_set, d: 7, l: 'true label inside the 90% set', c: 'var(--color-ink-hi)' },
            ].map((a) => (
              <div key={a.l} className="flex flex-col gap-[9px] border-r px-[22px] py-5" style={{ borderColor: 'var(--color-edge)' }}>
                <div className="flex items-baseline gap-[3px]">
                  <span className="mono text-[34px] font-semibold leading-none tracking-[-0.02em]" style={{ color: a.c }}>{a.n}</span>
                  <span className="mono text-[22px] leading-none" style={{ color: 'var(--color-label)' }}>/</span>
                  <span className="mono text-[22px] leading-none" style={{ color: 'var(--color-dim)' }}>{a.d}</span>
                </div>
                <span className="max-w-[220px] text-[12px] leading-[1.45]" style={{ color: 'var(--color-body)' }}>{a.l}</span>
              </div>
            ))}
          </div>

          <Callout tone="warn">
            These are the seven genuine Sehwa captures, never trained on.{' '}
            <strong className="font-semibold" style={{ color: 'var(--color-amber)' }}>The test is not fully independent</strong>:
            the E01 fault parameters were tuned to match the two PMD055 events it scores, and the simulator's
            healthy reference is the four PMD014 events it expects to read Normal. Read it as “the simulator
            reproduces these traces well enough for the model to recognise them”, not as field validation.
          </Callout>

          {card.acceptance.length > 0 && (
            <div className="overflow-x-auto">
              <div className="min-w-[720px]">
                <div className="grid grid-cols-[150px_1fr_1fr_86px_66px] items-center gap-3.5 border-b px-[18px]"
                  style={{ height: 36, borderColor: 'var(--color-hair)', background: 'var(--color-deep)' }}>
                  <span className="cap">Event</span>
                  <span className="cap">Expected</span>
                  <span className="cap">Predicted</span>
                  <span className="cap text-right">Set size</span>
                  <span className="cap text-right">Correct</span>
                </div>
                {card.acceptance.map((r) => {
                  const ok = String(r.correct).toLowerCase() === 'true'
                  const c = ok ? 'var(--color-green)' : 'var(--color-accent)'
                  return (
                    <div key={r.event} className="grid grid-cols-[150px_1fr_1fr_86px_66px] items-center gap-3.5 border-b px-[18px]"
                      style={{ height: 42, borderColor: 'var(--color-hair)' }}>
                      <span className="mono text-[12px] font-medium leading-none" style={{ color: 'var(--color-ink-4)' }}>{r.event}</span>
                      <span className="text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>{faultLabel(r.expected)}</span>
                      <span className="text-[12px] font-medium leading-none" style={{ color: c }}>{faultLabel(r.predicted)}</span>
                      <span className="mono text-right text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>{r.set_size}</span>
                      <span className="mono text-right text-[11px] leading-none" style={{ letterSpacing: '0.08em', color: c }}>
                        {ok ? 'yes' : 'no'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </Panel>
      )}

      {s && (
        <div className="grid gap-[18px] sm:grid-cols-2 xl:grid-cols-4">
          <Metric k="ACCURACY" ko="정확도" v={`${(s.test.accuracy * 100).toFixed(1)}%`} bar={s.test.accuracy}
            sub={`balanced ${(s.test.balanced_acc * 100).toFixed(1)}%`} />
          <Metric k="MACRO F1" ko="거시 F1" v={s.test.macro_f1.toFixed(3)} bar={s.test.macro_f1}
            sub={`${card.per_class.length} classes, held-out machines`} />
          <Metric k="ANOMALY ROC-AUC" ko="이상 탐지" v={s.anomaly.roc_auc.toFixed(3)} bar={s.anomaly.roc_auc}
            sub={`positive rate ${(s.anomaly.positive_rate * 100).toFixed(0)}%`} />
          <Metric k="RUL ERROR" ko="잔여수명 오차" v={s.rul.rmse.toFixed(0)} bar={0.38} warn
            sub={`throws RMSE · ${(s.rul.coverage * 100).toFixed(0)}% interval coverage`} />
        </div>
      )}

      {s && (
        <Panel title="Conformal calibration" flush aside={<Note>등각 예측</Note>}>
          <div className="grid lg:grid-cols-[1.1fr_1fr]">
            <div className="grid grid-cols-2 border-r" style={{ borderColor: 'var(--color-edge)' }}>
              {[
                { k: 'TARGET COVERAGE', v: `${((1 - s.conformal.alpha) * 100).toFixed(0)}%`, c: 'var(--color-ink-2)' },
                { k: 'EMPIRICAL COVERAGE', v: `${(s.conformal.coverage * 100).toFixed(1)}%`, c: 'var(--color-amber)' },
                { k: 'MEAN SET SIZE', v: s.conformal.mean_set_size.toFixed(3), c: s.conformal.mean_set_size < 1 ? 'var(--color-accent)' : 'var(--color-ink-2)' },
                // Which split the quantile was fitted on is part of whether the
                // number above means anything, so it sits beside it rather than
                // in a footnote.
                {
                  k: 'CALIBRATED ON',
                  v: s.conformal.calib_events
                    ? `${s.conformal.calib_events.toLocaleString()} held out`
                    : '—',
                  c: 'var(--color-ink-2)',
                },
              ].map((c) => (
                <div key={c.k} className="flex flex-col gap-[7px] border-b border-r px-[18px] py-4" style={{ borderColor: 'var(--color-edge)' }}>
                  <span className="cap">{c.k}</span>
                  <span className="mono text-[20px] font-semibold leading-none" style={{ color: c.c }}>{c.v}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-col justify-center gap-[11px] p-[18px]">
              <div className="flex items-baseline justify-between">
                <span className="cap">Coverage vs target</span>
                <span className="mono text-[11px] font-medium leading-none"
                  style={{ color: s.conformal.coverage < 1 - s.conformal.alpha ? 'var(--color-accent)' : 'var(--color-amber)' }}>
                  {s.conformal.coverage >= 1 - s.conformal.alpha ? '+' : '−'}
                  {Math.abs((s.conformal.coverage - (1 - s.conformal.alpha)) * 100).toFixed(1)} pt
                </span>
              </div>
              <div className="relative h-[22px]" style={{ background: 'var(--color-deep)', border: '1px solid var(--color-line)' }}>
                <div className="absolute inset-y-0 left-0"
                  style={{
                    width: `${(s.conformal.coverage * 100).toFixed(1)}%`,
                    background: 'linear-gradient(90deg, rgba(79,184,232,.28), rgba(79,184,232,.14))',
                  }} />
                <div className="absolute -top-1 -bottom-1 w-0.5"
                  style={{ left: `${((1 - s.conformal.alpha) * 100).toFixed(0)}%`, background: 'var(--color-amber)' }} />
                <div className="mono absolute inset-0 flex items-center px-[9px] text-[10px] font-medium leading-none"
                  style={{ color: 'var(--color-ink-4)' }}>
                  {(s.conformal.coverage * 100).toFixed(1)}% EMPIRICAL
                </div>
              </div>
              <span className="text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
                Target {((1 - s.conformal.alpha) * 100).toFixed(0)}% marked in amber.{' '}
                {s.conformal.coverage < 1 - s.conformal.alpha
                  ? 'Under-coverage means the set is narrower than advertised.'
                  : 'Over-coverage is safe but means the sets are wider than the target requires.'}
                {s.conformal.calib_machines != null && (
                  <>
                    {' '}Fitted on <span className="mono" style={{ color: 'var(--color-dim)' }}>{s.conformal.calib_split ?? 'calib'}</span>{' '}
                    ({s.conformal.calib_machines} machines the model was neither trained on nor selected on),
                    measured on <span className="mono" style={{ color: 'var(--color-dim)' }}>test</span>.
                  </>
                )}
              </span>
            </div>
          </div>
          {s.conformal.mean_set_size <= 1.0001 && (
            <Callout tone="defect">
              <strong className="font-semibold" style={{ color: 'var(--color-accent)' }}>Not earning its keep.</strong>{' '}
              Every set is exactly one label, so coverage ({(s.conformal.coverage * 100).toFixed(2)}%) equals
              top-1 accuracy ({(s.test.accuracy * 100).toFixed(2)}%) — the conformal layer is contributing
              nothing over plain argmax. No set ever widens, so set size cannot be the off-distribution signal;
              the anomaly head is. The fix is an adaptive score function (APS/RAPS) that sizes sets by
              difficulty rather than by a fixed threshold.
            </Callout>
          )}
          {(s.conformal.threshold_empty_sets ?? (s.conformal.mean_set_size < 1 ? 1 : 0)) > 0 && (
            <Callout tone="defect">
              <strong className="font-semibold" style={{ color: 'var(--color-amber)' }}>Worth knowing.</strong>{' '}
              On <span className="mono">{s.conformal.threshold_empty_sets}</span> held-out events the bare
              threshold <span className="mono">p ≥ 1 − q̂</span> names no label at all. Both the serving path
              and the conformal wrapper force the argmax in, so nothing renders empty in the console — but
              that many events sit close enough to the threshold to be worth watching.
            </Callout>
          )}
        </Panel>
      )}

      <div className="grid items-start gap-[18px] xl:grid-cols-[1.25fr_1fr]">
        <Panel title="Where it is weakest" flush aside={<Note>LOWEST F1 FIRST</Note>}>
          {weakest.length === 0 ? <Empty>No per-class results available.</Empty> : (
            <div className="overflow-x-auto">
              <div className="min-w-[560px]">
                <div className="grid grid-cols-[minmax(0,1fr)_66px_66px_132px_60px] items-center gap-3 border-b px-[18px]"
                  style={{ height: 36, borderColor: 'var(--color-hair)', background: 'var(--color-deep)' }}>
                  <span className="cap">Class</span>
                  <span className="cap text-right">Prec</span>
                  <span className="cap text-right">Recall</span>
                  <span className="cap">F1</span>
                  <span className="cap text-right">Support</span>
                </div>
                {weakest.map((c) => {
                  const f1 = Number(c.f1)
                  const colour = f1 < 0.6 ? 'var(--color-accent)' : f1 < 0.85 ? 'var(--color-amber)' : 'var(--color-green)'
                  return (
                    <div key={c.class} className="grid grid-cols-[minmax(0,1fr)_66px_66px_132px_60px] items-center gap-3 border-b px-[18px]"
                      style={{ height: 44, borderColor: 'var(--color-hair)' }}>
                      <span className="truncate text-[12px] leading-none" style={{ color: 'var(--color-ink-3)' }}>{faultLabel(c.class)}</span>
                      <span className="mono text-right text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>{Number(c.precision).toFixed(3)}</span>
                      <span className="mono text-right text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>{Number(c.recall).toFixed(3)}</span>
                      <span className="flex items-center gap-[9px]">
                        <span className="relative h-1 w-[70px] flex-none" style={{ background: 'var(--color-line)' }}>
                          <span className="absolute inset-y-0 left-0" style={{ width: `${(f1 * 100).toFixed(1)}%`, background: colour }} />
                        </span>
                        <span className="mono text-[12px] font-medium leading-none" style={{ color: colour }}>{f1.toFixed(3)}</span>
                      </span>
                      <span className="mono text-right text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{c.support}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </Panel>

        {metro && (
          <Panel title="Real field data — MetroPT-3" flush aside={<Note>UCI 791 · CC BY 4.0</Note>}>
            <div className="grid grid-cols-2">
              {[
                { k: 'ROC-AUC', v: String(metro.roc_auc), c: 'var(--color-green)' },
                { k: 'PRECISION@100', v: String(metro.precision_at_100), c: 'var(--color-accent)' },
                { k: 'WINDOWS', v: Number(metro.windows).toLocaleString(), c: 'var(--color-ink-2)' },
                { k: 'DOCUMENTED FAILURES', v: String(metro.documented_failures), c: 'var(--color-ink-2)' },
              ].map((m) => (
                <div key={m.k} className="flex flex-col gap-[7px] border-b border-r px-[18px] py-4" style={{ borderColor: 'var(--color-edge)' }}>
                  <span className="cap">{m.k}</span>
                  <span className="mono text-[20px] font-semibold leading-none" style={{ color: m.c }}>{m.v}</span>
                </div>
              ))}
            </div>
            <p className="px-[18px] py-3.5 text-[12px] leading-[1.6]" style={{ color: 'var(--color-dim)', textWrap: 'pretty' }}>
              The only data here nobody generated for this project. Read the two numbers together: the AUC is
              real, but <strong className="font-semibold" style={{ color: 'var(--color-accent)' }}>precision@100 is zero</strong> —{' '}
              {String(metro.normal_windows_above_failure_max)} normal windows outscore the highest failure
              window. A team told to investigate the top 100 alarms would find none of the four documented
              failures. AUC flatters a detector that could not be used as an alarm list.
            </p>
          </Panel>
        )}
      </div>
    </Page>
  )
}

function Metric({ k, ko, v, sub, bar, warn }: { k: string; ko: string; v: string; sub: string; bar: number; warn?: boolean }) {
  return (
    <div className="panel flex flex-col gap-3 px-[18px] py-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="cap" style={{ color: 'var(--color-dim)' }}>{k}</span>
        <span className="text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{ko}</span>
      </div>
      <span className="mono text-[30px] font-semibold leading-none tracking-[-0.02em]" style={{ color: 'var(--color-ink-hi)' }}>{v}</span>
      <span className="relative block h-[3px]" style={{ background: 'var(--color-line)' }}>
        <span className="absolute inset-y-0 left-0"
          style={{ width: `${(Math.min(1, Math.max(0, bar)) * 100).toFixed(1)}%`, background: warn ? 'var(--color-amber)' : 'var(--color-green)' }} />
      </span>
      <span className="text-[11px] leading-[1.4]" style={{ color: 'var(--color-dim)' }}>{sub}</span>
    </div>
  )
}
