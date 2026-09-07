import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { fetchOpportunity, fetchOpportunitySnapshots } from '../../api/opportunities'
import QueryState from '../../components/ui/QueryState'
import { DataTable, HeadRow, THead, Td, Th } from '../../components/ui/table'
import { exchangeColor } from '../../lib/exchanges'
import { fmtDateTimeSec, fmtUsd } from '../../lib/format'

function fmtLifetime(sec: number): string {
  if (sec < 90) return `${Math.round(sec)}s`
  if (sec < 5400) return `${Math.round(sec / 60)} min`
  if (sec < 172800) return `${(sec / 3600).toFixed(1)} h`
  return `${(sec / 86400).toFixed(1)} j`
}

const LIVE_COLOR: Record<string, string> = {
  LIVE: 'text-amber-400',
  STALE: 'text-zinc-400',
  EXPIRED: 'text-zinc-500',
}

export default function OpportunityDetail() {
  const { id } = useParams<{ id: string }>()
  const oppId = Number(id)

  const oppQ = useQuery({
    queryKey: ['opp', 'detail', oppId],
    queryFn: () => fetchOpportunity(oppId),
    refetchInterval: 10_000,
  })
  const snapQ = useQuery({
    queryKey: ['opp', 'snapshots', oppId],
    queryFn: () => fetchOpportunitySnapshots(oppId),
    refetchInterval: 10_000,
  })

  const snaps = useMemo(() => snapQ.data ?? [], [snapQ.data])
  const [selIdx, setSelIdx] = useState<number | null>(null)
  const sel = selIdx == null ? snaps.length - 1 : Math.min(selIdx, snaps.length - 1)
  const selected = snaps[sel]

  const t0 = snaps.length ? new Date(snaps[0].ts).getTime() : 0
  const series = useMemo(
    () =>
      snaps.map((s) => ({
        min: (new Date(s.ts).getTime() - t0) / 60000,
        net: s.net_profit_usd,
        apr: s.apr_pct,
        ask: s.top_ask,
        bid: s.top_bid,
        spread: s.top_bid - s.top_ask,
      })),
    [snaps, t0],
  )

  const deltas = useMemo(
    () =>
      snaps.slice(1).map((s, i) => {
        const a = snaps[i]
        return {
          ts: s.ts,
          dtSec: (new Date(s.ts).getTime() - new Date(a.ts).getTime()) / 1000,
          dNet: s.net_profit_usd - a.net_profit_usd,
          dSpread: s.top_bid - s.top_ask - (a.top_bid - a.top_ask),
        }
      }),
    [snaps],
  )

  if (oppQ.isLoading || snapQ.isLoading) return <QueryState isLoading isError={false} />
  const opp = oppQ.data
  if (oppQ.isError || !opp)
    return (
      <div className="text-sm text-red-400">
        Opportunité introuvable.{' '}
        <Link to="/opportunites/historique" className="underline">
          Retour
        </Link>
      </div>
    )

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto pb-6">
      <Link to="/opportunites/historique" className="text-xs text-zinc-500 hover:text-zinc-300">
        ← Historique
      </Link>

      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <h1 className="font-mono text-sm font-semibold text-zinc-100">{opp.instrument}</h1>
        <span className="text-xs">
          <span className={exchangeColor(opp.buy_from)}>{opp.buy_from}</span>
          <span className="mx-1 text-zinc-500">→</span>
          <span className={exchangeColor(opp.sell_to)}>{opp.sell_to}</span>
        </span>
        <span className="text-xs text-zinc-400">
          lifetime <span className="text-zinc-200">{fmtLifetime(opp.lifetime_sec)}</span>
        </span>
        <span className="text-xs text-zinc-400">{opp.samples_count} snapshots</span>
        <span className="text-xs text-zinc-400">
          peak <span className="text-emerald-400">{fmtUsd(opp.peak_net_profit_usd)}</span> → dernier{' '}
          <span className="text-zinc-200">{fmtUsd(opp.net_profit_usd)}</span>{' '}
          <span className={opp.decay_pct > 50 ? 'text-red-400' : 'text-zinc-500'}>
            (−{opp.decay_pct.toFixed(0)}%)
          </span>
        </span>
        <span className="text-xs">
          <span className={LIVE_COLOR[opp.live_status] ?? 'text-zinc-400'}>{opp.live_status}</span>
          {opp.close_reason && <span className="text-zinc-600"> ({opp.close_reason})</span>}
          <span className="ml-2 text-zinc-500">exec: {opp.status}</span>
        </span>
      </div>

      {opp.status === 'EXECUTED' && (
        <Link to="/trades" className="text-xs text-sky-400 hover:underline">
          → voir le trade
        </Link>
      )}

      {snaps.length === 0 ? (
        <p className="text-xs text-zinc-600">Aucun snapshot enregistré.</p>
      ) : (
        <>
          <section>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Profit net dans le temps
            </h2>
            <div className="h-56 w-full rounded border border-zinc-800 bg-zinc-900 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="min"
                    type="number"
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `${Number(v).toFixed(0)}m`}
                  />
                  <YAxis
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                  />
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }}
                    labelFormatter={(v) => `+${Number(v).toFixed(1)} min`}
                    formatter={(v, name) => [
                      name === 'net' ? fmtUsd(Number(v)) : `${Number(v).toFixed(1)}%`,
                      name === 'net' ? 'profit net' : 'APR',
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="net"
                    stroke="#34d399"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  {selected && (
                    <ReferenceDot
                      x={series[sel]?.min}
                      y={series[sel]?.net}
                      r={4}
                      fill="#fbbf24"
                      stroke="none"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

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
                  achat @{opp.buy_from}{' '}
                  <span className="text-zinc-200">{selected.top_ask.toFixed(4)}</span>
                </span>
                <span>
                  vente @{opp.sell_to}{' '}
                  <span className="text-zinc-200">{selected.top_bid.toFixed(4)}</span>
                </span>
                <span>
                  fees <span className="text-zinc-200">{fmtUsd(selected.fees_usd)}</span>
                </span>
                <span>
                  net{' '}
                  <span
                    className={selected.net_profit_usd > 0 ? 'text-emerald-400' : 'text-red-400'}
                  >
                    {fmtUsd(selected.net_profit_usd)}
                  </span>
                </span>
                <span>
                  APR <span className="text-zinc-200">{selected.apr_pct.toFixed(1)}%</span>
                </span>
                <span>
                  capital{' '}
                  <span className="text-zinc-200">{fmtUsd(selected.capital_required_usd)}</span>
                </span>
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Convergence des 2 quotes
            </h2>
            <div className="h-56 w-full rounded border border-zinc-800 bg-zinc-900 p-2">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={series} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="min"
                    type="number"
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `${Number(v).toFixed(0)}m`}
                  />
                  <YAxis stroke="#71717a" tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }}
                    labelFormatter={(v) => `+${Number(v).toFixed(1)} min`}
                    formatter={(v, name) => [Number(v).toFixed(4), String(name)]}
                  />
                  <Area
                    name="edge"
                    type="monotone"
                    dataKey="spread"
                    stroke="none"
                    fill="#34d399"
                    fillOpacity={0.12}
                  />
                  <Line
                    name={`bid @${opp.sell_to}`}
                    type="monotone"
                    dataKey="bid"
                    stroke="#34d399"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    name={`ask @${opp.buy_from}`}
                    type="monotone"
                    dataKey="ask"
                    stroke="#f87171"
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-1 text-[11px] text-zinc-600">
              L'arbitrage se referme quand le bid (vente) rejoint l'ask (achat). L'aire verte = edge
              brut par unité.
            </p>
          </section>

          {deltas.length > 0 && (
            <section>
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Évolution
              </h2>
              <div className="overflow-auto rounded border border-zinc-800">
                <DataTable>
                  <THead>
                    <HeadRow>
                      <Th>Vers</Th>
                      <Th align="right">Δt</Th>
                      <Th align="right">Δ profit net</Th>
                      <Th align="right">Δ spread</Th>
                    </HeadRow>
                  </THead>
                  <tbody>
                    {deltas.map((d, i) => (
                      <tr key={i}>
                        <Td className="whitespace-nowrap text-zinc-500">{fmtDateTimeSec(d.ts)}</Td>
                        <Td align="right" className="text-zinc-400">
                          {d.dtSec.toFixed(0)}s
                        </Td>
                        <Td
                          align="right"
                          className={d.dNet >= 0 ? 'text-emerald-400' : 'text-red-400'}
                        >
                          {d.dNet >= 0 ? '+' : ''}
                          {fmtUsd(d.dNet)}
                        </Td>
                        <Td
                          align="right"
                          className={d.dSpread >= 0 ? 'text-emerald-400' : 'text-red-400'}
                        >
                          {d.dSpread >= 0 ? '+' : ''}
                          {d.dSpread.toFixed(4)}
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
