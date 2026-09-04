import type { Position, Severity } from './types'

/** Severity maps onto the console's three states: fault, watch, clear. */
export const SEVERITY_COLOR: Record<Severity, string> = {
  normal: 'var(--color-green)',
  info: 'var(--color-cyan)',
  warning: 'var(--color-amber)',
  critical: 'var(--color-accent)',
}

/** Three states, named the way the wall board names them. */
export function stateOf(sev: Severity): 'fault' | 'watch' | 'clear' {
  return sev === 'critical' ? 'fault' : sev === 'warning' || sev === 'info' ? 'watch' : 'clear'
}

/** Position colours are the machine's own indication states, not a theme:
 *  +23 V proves Normal, −23 V proves Reverse, 0 V proves nothing. */
export const POSITION_COLOR: Record<Position, string> = {
  N: 'var(--color-green)',
  R: 'var(--color-cyan)',
  transit: 'var(--color-amber)',
  unknown: 'var(--color-label)',
}

export const POSITION_LABEL: Record<Position, string> = {
  N: 'Normal',
  R: 'Reverse',
  transit: 'In transit',
  unknown: 'No telemetry',
}

export const POSITION_KO: Record<Position, string> = {
  N: '정위',
  R: '반위',
  transit: '전환 중',
  unknown: '표시 없음',
}

export const CHANNEL_COLOR: Record<string, string> = {
  ac_curr: 'var(--color-cyan)',
  ac_volt: 'var(--color-amber)',
  as_volt: 'var(--color-violet)',
  output_n_volt: 'var(--color-green)',
  output_r_volt: 'var(--color-label)',
}

export const CHANNEL_LABEL: Record<string, string> = {
  ac_curr: 'Motor current',
  ac_volt: 'Supply',
  as_volt: 'Drive command',
  output_n_volt: 'Position (N)',
  output_r_volt: 'Position (R)',
}

/** Drawing order, back to front: the current trace is the subject and is drawn
 *  last so nothing crosses over it. */
export const CHANNEL_ORDER = ['output_r_volt', 'output_n_volt', 'as_volt', 'ac_volt', 'ac_curr']

export const PHASE_LABEL: Record<string, string> = {
  idle_pre: 'IDLE',
  inrush: 'UNLOCK',
  throw: 'THROW',
  lock: 'LOCK',
  idle_post: 'IDLE',
}

export const PHASE_KO: Record<string, string> = {
  idle_pre: '',
  inrush: '해정',
  throw: '전환',
  lock: '쇄정',
  idle_post: '',
}

export function faultLabel(fault: string): string {
  return fault === 'NORMAL' ? 'Normal' : fault.replace(/^E\d\d_/, '').replaceAll('_', ' ').toLowerCase()
}

export function num(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(digits)
}

export function ago(iso: string | null): string {
  if (!iso) return '—'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}
