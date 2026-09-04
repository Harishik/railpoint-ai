/**
 * Page primitives.
 *
 * Every workspace opens the same way — name, Korean name, then one sentence
 * saying what you are looking at and how to read it. Consistent placement is
 * what lets someone predict where things are before the page has painted.
 */
export function Page({ title, ko, lede, actions, children }: {
  title: string
  ko?: string
  lede?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-[18px] px-7 pb-9 pt-[26px]">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2.5">
            <h1 className="t-h1">{title}</h1>
            {ko && <span className="t-ko">{ko}</span>}
          </div>
          {lede && <p className="t-lede mt-[9px] max-w-[660px]">{lede}</p>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  )
}

/** A plate. Square-cornered, hairline-bordered, lit along its top edge. */
export function Panel({ title, aside, children, className = '', flush = false }: {
  title?: string
  aside?: React.ReactNode
  children?: React.ReactNode
  className?: string
  /** Content sits against the border — for tables and charts that own their
   *  own padding. */
  flush?: boolean
}) {
  return (
    <div className={`panel min-w-0 ${className}`}>
      {title && (
        <div className="panel-head">
          <span className="sec">{title}</span>
          {aside}
        </div>
      )}
      {children != null && (flush ? children : <div className="px-[18px] py-4">{children}</div>)}
    </div>
  )
}

/** Caption on a panel header. Never a second title — always metadata. */
export function Note({ children, tone = 'faint' }: { children: React.ReactNode; tone?: 'faint' | 'accent' }) {
  return (
    <span
      className="mono text-[10px] leading-none"
      style={{ color: tone === 'accent' ? 'var(--color-accent)' : 'var(--color-label)', letterSpacing: tone === 'accent' ? '0.08em' : undefined }}
    >
      {children}
    </span>
  )
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="py-14 text-center text-[13px] leading-none" style={{ color: 'var(--color-label)' }}>
      {children}
    </p>
  )
}

/** A run of prose called out against a coloured edge. Used for the two places
 *  the console has to say something unflattering about itself. */
export function Callout({ tone, children }: { tone: 'warn' | 'defect'; children: React.ReactNode }) {
  const colour = tone === 'defect' ? 'var(--color-accent)' : 'var(--color-amber)'
  return (
    <div
      className="px-[18px] py-3.5 text-[12px] leading-[1.6]"
      style={{
        background: tone === 'defect' ? '#160F0C' : 'var(--color-deep)',
        borderLeft: `2px solid ${colour}`,
        color: 'var(--color-dim)',
        textWrap: 'pretty',
      }}
    >
      {children}
    </div>
  )
}

/** Segmented control: filters, sorts. One row of the design's square chips. */
export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string; count?: number }[]
  label: string
}) {
  return (
    <div className="flex border" style={{ borderColor: 'var(--color-line)', background: 'var(--color-deep)' }}
      role="tablist" aria-label={label}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.value)}
            className="press mono inline-flex h-7 items-center px-3.5 text-[10px] font-medium leading-none"
            style={{
              letterSpacing: '0.12em',
              borderRight: '1px solid var(--color-line)',
              color: on ? 'var(--color-bg)' : 'var(--color-dim)',
              background: on ? 'var(--color-accent)' : 'transparent',
              textTransform: 'uppercase',
            }}
          >
            {o.label}
            {o.count !== undefined && (
              <span className="ml-[7px] text-[10px]" style={{ color: on ? 'rgba(11,15,20,.6)' : 'var(--color-label)' }}>
                {o.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** Bordered button in the design's control style. */
export function Ctl({ children, onClick, tone = 'quiet', title, pressed }: {
  children: React.ReactNode
  onClick: () => void
  tone?: 'quiet' | 'primary' | 'go'
  title?: string
  pressed?: boolean
}) {
  const base = 'press inline-flex h-[30px] items-center justify-center px-3.5 text-[12px] leading-none'
  if (tone === 'primary') {
    return (
      <button type="button" onClick={onClick} title={title} aria-pressed={pressed}
        className={`${base} font-semibold hover:brightness-110`}
        style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}>
        {children}
      </button>
    )
  }
  if (tone === 'go') {
    return (
      <button type="button" onClick={onClick} title={title} aria-pressed={pressed}
        className={`${base} font-medium`}
        style={{ border: '1px solid #1D3A2C', background: 'rgba(63,214,140,.08)', color: 'var(--color-green)' }}>
        {children}
      </button>
    )
  }
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={pressed}
      className={`${base} font-medium hover:border-rule-hi hover:text-ink`}
      style={{
        border: `1px solid ${pressed ? 'var(--color-rule-hi)' : 'var(--color-rule)'}`,
        background: pressed ? 'var(--color-line)' : 'var(--color-raised)',
        color: pressed ? 'var(--color-ink)' : 'var(--color-ink-4)',
      }}>
      {children}
    </button>
  )
}
