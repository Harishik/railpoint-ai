import type { Position, Severity } from './types'

export const SEVERITY_COLOR: Record<Severity, string> = {
  normal: 'var(--color-normal)',
  info: 'var(--color-transit)',
  warning: 'var(--color-degraded)',
  critical: 'var(--color-fault)',
}

/** Position colours are the machine's own indication states, not a theme. */
export const POSITION_COLOR: Record<Position, string> = {
  N: 'var(--color-normal)',
  R: 'var(--color-reverse)',
  transit: 'var(--color-transit)',
  unknown: 'var(--color-unknown)',
}

export const POSITION_LABEL: Record<Position, string> = {
  N: 'Normal 정위',
  R: 'Reverse 반위',
  transit: 'In transit',
  unknown: 'No telemetry',
}

export const CHANNEL_COLOR: Record<string, string> = {
  ac_curr: 'var(--color-transit)',
  ac_volt: 'var(--color-degraded)',
  as_volt: 'var(--color-reverse)',
  output_n_volt: 'var(--color-normal)',
  output_r_volt: 'var(--color-unknown)',
}

export const CHANNEL_LABEL: Record<string, string> = {
  ac_curr: 'Motor current',
  ac_volt: 'Supply',
  as_volt: 'Drive command',
  output_n_volt: 'Position (N)',
  output_r_volt: 'Position (R)',
}

export const PHASE_LABEL: Record<string, string> = {
  idle_pre: 'Idle',
  inrush: 'Unlock 해정',
  throw: 'Throw 전환',
  lock: 'Lock 쇄정',
  idle_post: 'Idle',
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
  return `${Math.floor(s / 3600)}h`
}
