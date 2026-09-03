/** Every workspace opens the same way: what this page is, then what it holds.
 *  Consistent placement is what lets someone predict where things are. */
export function Page({ title, ko, lede, actions, children }: {
  title: string
  ko?: string
  lede?: string
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-full flex-col gap-4 p-4 lg:p-5">
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div>
          <div className="flex items-baseline gap-2.5">
            <h1 className="text-[20px] font-semibold leading-tight tracking-[-0.014em]">{title}</h1>
            {ko && <span className="t-label text-ink-faint">{ko}</span>}
          </div>
          {lede && <p className="t-label mt-1 max-w-[70ch] text-ink-dim">{lede}</p>}
        </div>
        {actions}
      </header>
      {children}
    </div>
  )
}

export function Section({ title, aside, children, className = '' }: {
  title?: string
  aside?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-xl border border-line/70 bg-surface-1 ${className}`}
      style={{ boxShadow: 'var(--shadow-hero)' }}>
      {title && (
        <header className="flex items-center justify-between gap-3 px-4 pb-2.5 pt-3">
          <h2 className="t-micro text-ink-faint">{title}</h2>
          {aside}
        </header>
      )}
      <div className={title ? 'px-4 pb-4' : 'p-4'}>{children}</div>
    </section>
  )
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="t-label py-10 text-center text-ink-faint">{children}</p>
}
