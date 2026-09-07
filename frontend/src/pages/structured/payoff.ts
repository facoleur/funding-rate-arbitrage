import type { StructuredLeg, StructuredSnapshot } from '../../api/structured'

/** Option type parsed from a normalized instrument name `…-{STRIKE}-{C|P}`. */
function legType(leg: StructuredLeg): 'C' | 'P' {
  return leg.instrument.trim().endsWith('P') ? 'P' : 'C'
}

function find(
  legs: StructuredLeg[],
  type: 'C' | 'P',
  side: 'buy' | 'sell',
): StructuredLeg | undefined {
  return legs.find((l) => legType(l) === type && l.side === side)
}

export interface SpreadDebits {
  /** Net debit of the bull call spread: ask(C K1) − bid(C K2). */
  callDebit: number
  /** Net debit of the bear put spread: ask(P K2) − bid(P K1). */
  putDebit: number
}

export function spreadDebits(legs: StructuredLeg[]): SpreadDebits | null {
  const c1 = find(legs, 'C', 'buy')
  const c2 = find(legs, 'C', 'sell')
  const p1 = find(legs, 'P', 'sell')
  const p2 = find(legs, 'P', 'buy')
  if (!c1 || !c2 || !p1 || !p2) return null
  return { callDebit: c1.price - c2.price, putDebit: p2.price - p1.price }
}

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x))

export interface PayoffPoint {
  s: number
  bull: number // bull call spread P&L per unit
  bear: number // bear put spread P&L per unit
  box: number // combined box — flat, locked P&L per unit
}

/**
 * Per-unit P&L at expiry across a range of underlying prices, for the two
 * spreads composing the box plus their (flat) sum. `null` when the snapshot's
 * legs don't form a complete box.
 */
export function payoffSeries(
  snapshot: Pick<StructuredSnapshot, 'legs' | 'entry_cost' | 'max_fees'>,
  k1: number,
  k2: number,
  points = 61,
): PayoffPoint[] | null {
  const debits = spreadDebits(snapshot.legs)
  if (!debits || k2 <= k1) return null
  const width = k2 - k1
  const box = width - snapshot.entry_cost - snapshot.max_fees
  const lo = k1 - width * 0.6
  const hi = k2 + width * 0.6
  const step = (hi - lo) / (points - 1)
  const out: PayoffPoint[] = []
  for (let i = 0; i < points; i++) {
    const s = lo + step * i
    out.push({
      s,
      bull: clamp(s - k1, 0, width) - debits.callDebit,
      bear: clamp(k2 - s, 0, width) - debits.putDebit,
      box,
    })
  }
  return out
}

export interface SnapshotDelta {
  from: string
  to: string
  dtSec: number
  dEntryCost: number
  dTotalProfit: number
  venueChanged: boolean
}

function venueKey(legs: StructuredLeg[]): string {
  return legs.map((l) => `${l.instrument}:${l.exchange}`).join('|')
}

export function snapshotDeltas(snaps: StructuredSnapshot[]): SnapshotDelta[] {
  const out: SnapshotDelta[] = []
  for (let i = 1; i < snaps.length; i++) {
    const a = snaps[i - 1]
    const b = snaps[i]
    out.push({
      from: a.ts,
      to: b.ts,
      dtSec: (new Date(b.ts).getTime() - new Date(a.ts).getTime()) / 1000,
      dEntryCost: b.entry_cost - a.entry_cost,
      dTotalProfit: b.max_total_profit_usd - a.max_total_profit_usd,
      venueChanged: venueKey(a.legs) !== venueKey(b.legs),
    })
  }
  return out
}
