import { describe, expect, it } from 'vitest'

import type { StructuredLeg, StructuredSnapshot } from '../../api/structured'
import { payoffSeries, snapshotDeltas, spreadDebits } from './payoff'

const K1 = 100
const K2 = 120

function legs(overrides: Partial<Record<string, number>> = {}): StructuredLeg[] {
  const p = { c1: 21, c2: 9, p1: 9, p2: 16, ...overrides }
  const mk = (
    instrument: string,
    side: 'buy' | 'sell',
    price: number,
    exchange = 'derive',
  ): StructuredLeg => ({ exchange, instrument, side, price, qty: 5, taker_fee_rate: 0 })
  return [
    mk('BTC-20260327-100-C', 'buy', p.c1),
    mk('BTC-20260327-100-P', 'sell', p.p1),
    mk('BTC-20260327-120-C', 'sell', p.c2),
    mk('BTC-20260327-120-P', 'buy', p.p2),
  ]
}

function snap(over: Partial<StructuredSnapshot> = {}): StructuredSnapshot {
  return {
    ts: '2026-09-06T12:00:00Z',
    entry_cost: 19,
    max_fees: 0,
    min_profit: 1,
    max_size: 5,
    capital_required_usd: 95,
    max_total_profit_usd: 5,
    legs: legs(),
    underlying_price: 110,
    ...over,
  }
}

describe('spreadDebits', () => {
  it('splits the box into bull-call and bear-put debits', () => {
    expect(spreadDebits(legs())).toEqual({ callDebit: 12, putDebit: 7 })
  })

  it('returns null when a leg is missing', () => {
    expect(spreadDebits(legs().slice(0, 3))).toBeNull()
  })
})

describe('payoffSeries', () => {
  it('box line is flat = width - entry_cost - fees, and the two spreads sum to it', () => {
    const s = payoffSeries(snap({ entry_cost: 19, max_fees: 0 }), K1, K2)
    expect(s).not.toBeNull()
    for (const pt of s!) {
      expect(pt.box).toBeCloseTo(1) // 120 - 100 - 19
      expect(pt.bull + pt.bear).toBeCloseTo(pt.box)
    }
  })

  it('bull call is capped by the width net of its debit above K2', () => {
    const s = payoffSeries(snap(), K1, K2)!
    const last = s[s.length - 1] // S well above K2
    expect(last.bull).toBeCloseTo(20 - 12)
    expect(last.bear).toBeCloseTo(0 - 7)
  })

  it('returns null for a degenerate strike pair', () => {
    expect(payoffSeries(snap(), 120, 120)).toBeNull()
  })
})

describe('snapshotDeltas', () => {
  it('diffs consecutive snapshots and flags venue changes', () => {
    const a = snap({ ts: '2026-09-06T12:00:00Z', entry_cost: 19, max_total_profit_usd: 5 })
    const b = snap({
      ts: '2026-09-06T12:00:30Z',
      entry_cost: 18,
      max_total_profit_usd: 10,
      legs: legs({ c1: 21 }).map((l) =>
        l.instrument.endsWith('100-C') ? { ...l, exchange: 'aevo' } : l,
      ),
    })
    const [d] = snapshotDeltas([a, b])
    expect(d.dtSec).toBe(30)
    expect(d.dEntryCost).toBe(-1)
    expect(d.dTotalProfit).toBe(5)
    expect(d.venueChanged).toBe(true)
  })

  it('is empty for a single snapshot', () => {
    expect(snapshotDeltas([snap()])).toEqual([])
  })
})
