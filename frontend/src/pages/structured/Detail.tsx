import { useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { fetchStructuredOpportunity, fetchStructuredSnapshots } from '../../api/structured'
import QueryState from '../../components/ui/QueryState'
import { DataTable, HeadRow, THead, Td, Th } from '../../components/ui/table'
import { exchangeColor } from '../../lib/exchanges'
import { fmtDateTimeSec, fmtUsd } from '../../lib/format'
import { payoffSeries, snapshotDeltas } from './payoff'

function fmtLifetime(sec: number): string {
  if (sec < 90) return `${Math.round(sec)}s`
  if (sec < 5400) return `${Math.round(sec / 60)} min`
  if (sec < 172800) return `${(sec / 3600).toFixed(1)} h`
  return `${(sec / 86400).toFixed(1)} j`
}

export default function StructuredDetail() {
  const { id } = useParams<{ id: string }>()
  const oppId = Number(id)

  const oppQ = useQuery({
    queryKey: ['structured', 'opp', oppId],
    queryFn: () => fetchStructuredOpportunity(oppId),
    refetchInterval: 10_000,
  })
  const snapQ = useQuery({
    queryKey: ['structured', 'snapshots', oppId],
    queryFn: () => fetchStructuredSnapshots(oppId),
    refetchInterval: 10_000,
  })

  const snaps = useMemo(() => snapQ.data ?? [], [snapQ.data])
  const [selIdx, setSelIdx] = useState<number | null>(null)
  const sel = selIdx == null ? snaps.length - 1 : Math.min(selIdx, snaps.length - 1)
  const selected = snaps[sel]

  const t0 = snaps.length ? new Date(snaps[0].ts).getTime() : 0
  const decayData = useMemo(
    () =>
      snaps.map((s, i) => ({
        i,
        min: (new Date(s.ts).getTime() - t0) / 60000,
        total: s.max_total_profit_usd,
        edge: s.min_profit,
      })),
    [snaps, t0],
  )

  const opp = oppQ.data
  const [k1, k2] = opp?.strikes ?? [0, 0]
  const payoff = useMemo(
    () => (opp && selected ? payoffSeries(selected, k1, k2) : null),
    [opp, selected, k1, k2],
  )
  const deltas = useMemo(() => snapshotDeltas(snaps), [snaps])

  if (oppQ.isLoading || snapQ.isLoading) return <QueryState isLoading isError={false} />
  if (oppQ.isError || !opp)
    return (
      <div className="text-sm text-red-400">
        Opportunité introuvable.{' '}
        <Link to="/structured/historique" className="underline">
          Retour
        </Link>
      </div>
    )

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto pb-6">
      <Link to="/structured/historique" className="text-xs text-zinc-500 hover:text-zinc-300">
        ← Historique
      </Link>

      {/* ── En-tête ── */}
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <h1 className="text-base font-semibold text-zinc-100">
          {opp.strategy_type} · {opp.underlying} · {k1.toLocaleString()} / {k2.toLocaleString()}
        </h1>
        <span className="text-xs text-zinc-500">
          expiry {new Date(opp.expiry).toISOString().slice(0, 10)}
        </span>
        <span className="text-xs text-zinc-400">
          lifetime <span className="text-zinc-200">{fmtLifetime(opp.lifetime_sec)}</span>
        </span>
        <span className="text-xs text-zinc-400">{opp.samples_count} snapshots</span>
        <span className="text-xs text-zinc-400">
          peak <span className="text-emerald-400">{fmtUsd(opp.peak_total_profit_usd)}</span> →
          dernier <span className="text-zinc-200">{fmtUsd(opp.max_total_profit_usd)}</span>{' '}
          <span className={opp.decay_pct > 50 ? 'text-red-400' : 'text-zinc-500'}>
            (−{opp.decay_pct.toFixed(0)}%)
          </span>
        </span>
        <span className="text-xs">
          <span
            className={
              opp.live_status === 'LIVE'
                ? 'text-amber-400'
                : opp.live_status === 'STALE'
                  ? 'text-zinc-400'
                  : 'text-zinc-500'
            }
          >
            {opp.live_status}
          </span>
          {opp.close_reason && <span className="text-zinc-600"> ({opp.close_reason})</span>}
        </span>
      </div>

      {snaps.length === 0 ? (
        <p className="text-xs text-zinc-600">Aucun snapshot enregistré.</p>
      ) : (
        <>
          {/* ── Courbe de decay ── */}
          <section>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Profit total dans le temps
            </h2>
            <div className="h-56 w-full rounded border border-zinc-800 bg-zinc-900 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={decayData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="min"
                    type="number"
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: number) => `${v.toFixed(0)}m`}
                  />
                  <YAxis
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                  />
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }}
                    labelFormatter={(v) => `+${Number(v).toFixed(1)} min`}
                    formatter={(v, name) => [
                      name === 'total' ? fmtUsd(Number(v)) : Number(v).toFixed(4),
                      name === 'total' ? 'profit total' : 'edge/unité',
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#34d399"
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  {selected && (
                    <ReferenceDot
                      x={decayData[sel]?.min}
                      y={decayData[sel]?.total}
                      r={4}
                      fill="#fbbf24"
                      stroke="none"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* ── Slider temporel ── */}
          <section className="rounded border border-zinc-800 bg-zinc-900 p-3">
            <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
              <span className="text-zinc-300">
                Snapshot {sel + 1} / {snaps.length}
              </span>
              <span className="text-zinc-500">{selected && fmtDateTimeSec(selected.ts)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(snaps.length - 1, 0)}
              value={sel}
              onChange={(e) => setSelIdx(Number(e.target.value))}
              className="w-full accent-amber-400"
              aria-label="snapshot"
            />
            {selected && (
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-400">
                <span>
                  entry <span className="text-zinc-200">{selected.entry_cost.toFixed(4)}</span>
                </span>
                <span>
                  fees <span className="text-zinc-200">{selected.max_fees.toFixed(4)}</span>
                </span>
                <span>
                  edge/u{' '}
                  <span className={selected.min_profit > 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {selected.min_profit.toFixed(4)}
                  </span>
                </span>
                <span>
                  taille <span className="text-zinc-200">{selected.max_size.toFixed(2)}</span>
                </span>
                <span>
                  capital{' '}
                  <span className="text-zinc-200">{fmtUsd(selected.capital_required_usd)}</span>
                </span>
                <span>
                  total{' '}
                  <span className="text-emerald-400">{fmtUsd(selected.max_total_profit_usd)}</span>
                </span>
              </div>
            )}
          </section>

          {/* ── Jambes du snapshot ── */}
          {selected && selected.legs.length > 0 && (
            <section>
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Jambes — snapshot {sel + 1}
              </h2>
              <div className="overflow-auto rounded border border-zinc-800">
                <DataTable>
                  <THead>
                    <HeadRow>
                      <Th>Sens</Th>
                      <Th>Instrument</Th>
                      <Th>Venue</Th>
                      <Th align="right">Prix</Th>
                      <Th align="right">Liq</Th>
                    </HeadRow>
                  </THead>
                  <tbody>
                    {selected.legs.map((leg, i) => {
                      const buy = leg.side === 'buy'
                      return (
                        <tr key={i}>
                          <Td
                            className={`font-semibold ${buy ? 'text-emerald-400' : 'text-red-400'}`}
                          >
                            {buy ? 'BUY' : 'SELL'}
                          </Td>
                          <Td className="font-mono text-[11px] text-zinc-300">{leg.instrument}</Td>
                          <Td className={exchangeColor(leg.exchange)}>{leg.exchange}</Td>
                          <Td align="right" className="tabular-nums text-zinc-300">
                            {buy ? 'ask' : 'bid'} {leg.price.toFixed(4)}
                          </Td>
                          <Td align="right" className="tabular-nums text-zinc-600">
                            {leg.qty.toFixed(2)}
                          </Td>
                        </tr>
                      )
                    })}
                  </tbody>
                </DataTable>
              </div>
            </section>
          )}

          {/* ── Payoff des 2 spreads ── */}
          <section>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Payoff à expiry (par unité) — snapshot {sel + 1}
            </h2>
            {payoff ? (
              <div className="h-64 w-full rounded border border-zinc-800 bg-zinc-900 p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={payoff} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                    <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="s"
                      type="number"
                      domain={['dataMin', 'dataMax']}
                      stroke="#71717a"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v: number) => v.toFixed(0)}
                    />
                    <YAxis
                      stroke="#71717a"
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v: number) => v.toFixed(1)}
                    />
                    <Tooltip
                      contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }}
                      labelFormatter={(v) => `S_T = ${Number(v).toFixed(0)}`}
                      formatter={(v, name) => [Number(v).toFixed(4), String(name)]}
                    />
                    <ReferenceLine x={k1} stroke="#52525b" strokeDasharray="2 2" />
                    <ReferenceLine x={k2} stroke="#52525b" strokeDasharray="2 2" />
                    {selected?.underlying_price != null && (
                      <ReferenceLine
                        x={selected.underlying_price}
                        stroke="#fbbf24"
                        strokeDasharray="4 2"
                        label={{ value: 'spot', fill: '#fbbf24', fontSize: 10, position: 'top' }}
                      />
                    )}
                    <Line
                      name="bull call"
                      type="monotone"
                      dataKey="bull"
                      stroke="#38bdf8"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      name="bear put"
                      type="monotone"
                      dataKey="bear"
                      stroke="#a78bfa"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      name="box (verrouillé)"
                      type="monotone"
                      dataKey="box"
                      stroke="#34d399"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-xs text-zinc-600">
                Snapshot sans les 4 jambes — payoff indisponible.
              </p>
            )}
            <p className="mt-1 text-[11px] text-zinc-600">
              La ligne verte (box) est plate : c'est le P&amp;L verrouillé si on entre à cet instant
              et qu'on tient jusqu'à expiry. Les 2 autres sont les spreads composant.
            </p>
          </section>

          {/* ── Deltas snapshot-à-snapshot ── */}
          {deltas.length > 0 && (
            <section className="min-h-0">
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Évolution
              </h2>
              <div className="overflow-auto rounded border border-zinc-800">
                <DataTable>
                  <THead>
                    <HeadRow>
                      <Th>Vers</Th>
                      <Th align="right">Δt</Th>
                      <Th align="right">Δ entry</Th>
                      <Th align="right">Δ profit total</Th>
                      <Th>Venue</Th>
                    </HeadRow>
                  </THead>
                  <tbody>
                    {deltas.map((d, i) => (
                      <tr key={i}>
                        <Td className="whitespace-nowrap text-zinc-500">{fmtDateTimeSec(d.to)}</Td>
                        <Td align="right" className="text-zinc-400">
                          {d.dtSec.toFixed(0)}s
                        </Td>
                        <Td
                          align="right"
                          className={d.dEntryCost > 0 ? 'text-red-400' : 'text-emerald-400'}
                        >
                          {d.dEntryCost >= 0 ? '+' : ''}
                          {d.dEntryCost.toFixed(4)}
                        </Td>
                        <Td
                          align="right"
                          className={d.dTotalProfit >= 0 ? 'text-emerald-400' : 'text-red-400'}
                        >
                          {d.dTotalProfit >= 0 ? '+' : ''}
                          {fmtUsd(d.dTotalProfit)}
                        </Td>
                        <Td className="text-[11px] text-zinc-500">
                          {d.venueChanged ? 'mix changé' : '—'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
