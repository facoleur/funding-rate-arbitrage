import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { fetchBacktest } from '../../api/analytics'
import { fmtUsd } from '../../lib/format'
import { exchangeColor } from '../../lib/exchanges'
import { NumberField, Select } from '../../components/ui/Field'
import QueryState from '../../components/ui/QueryState'
import { DataTable, HeadRow, THead, Td, Th } from '../../components/ui/table'

const DAY_OPTIONS = [7, 30, 90, 365] as const
const LIFETIME_OPTIONS = [
  { v: 0, label: 'toutes durées' },
  { v: 60, label: '≥ 1 min de vie' },
  { v: 300, label: '≥ 5 min de vie' },
  { v: 900, label: '≥ 15 min de vie' },
] as const

function Stat({
  label,
  value,
  sub,
  color = 'text-zinc-200',
}: {
  label: string
  value: string
  sub?: string
  color?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-zinc-600 uppercase tracking-wider">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${color}`}>{value}</span>
      {sub && <span className="text-[10px] text-zinc-600">{sub}</span>}
    </div>
  )
}

function pct(v: number, dec = 1) {
  return `${v.toFixed(dec)}%`
}

const fmtDay = (ms: number) =>
  new Date(ms).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })

export default function Backtest() {
  const [days, setDays] = useState(30)
  const [symbol, setSymbol] = useState('')
  const [network, setNetwork] = useState<'mainnet' | 'testnet' | ''>('mainnet')
  const [minApr, setMinApr] = useState('')
  const [minProfit, setMinProfit] = useState('')
  const [minLifetime, setMinLifetime] = useState(0)
  const [budget, setBudget] = useState('')
  const [dedup, setDedup] = useState(true)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['backtest', days, symbol, network, minApr, minProfit, minLifetime, budget, dedup],
    queryFn: () =>
      fetchBacktest({
        days,
        symbol: symbol || undefined,
        network: network || undefined,
        min_apr: minApr ? Number(minApr) : undefined,
        min_profit: minProfit ? Number(minProfit) : undefined,
        min_lifetime_sec: minLifetime || undefined,
        one_position_per_instrument: dedup,
        capital_budget_usd: budget ? Number(budget) : undefined,
      }),
    refetchInterval: 60_000,
  })

  const s = data?.summary
  const series = useMemo(
    () =>
      (data?.series ?? []).map((p) => ({
        t: new Date(p.ts).getTime(),
        capital: p.capital_in_use_usd,
        profit: p.cumulative_profit_usd,
      })),
    [data],
  )

  return (
    <div className="space-y-5">
      {/* ── Header + filtres ── */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-1 text-base font-semibold text-zinc-100">Backtest opportunités</h1>

        <Select value={days} onChange={(v) => setDays(Number(v))}>
          {DAY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d} jours
            </option>
          ))}
        </Select>

        <Select value={symbol} onChange={setSymbol}>
          <option value="">BTC + ETH</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>

        <Select value={network} onChange={(v) => setNetwork(v as 'mainnet' | 'testnet' | '')}>
          <option value="mainnet">mainnet</option>
          <option value="testnet">testnet</option>
          <option value="">tous réseaux</option>
        </Select>

        <NumberField value={minApr} placeholder="APR min %" onChange={setMinApr} className="w-24" />
        <NumberField
          value={minProfit}
          placeholder="Profit min $"
          onChange={setMinProfit}
          className="w-24"
        />

        <Select value={minLifetime} onChange={(v) => setMinLifetime(Number(v))}>
          {LIFETIME_OPTIONS.map((o) => (
            <option key={o.v} value={o.v}>
              {o.label}
            </option>
          ))}
        </Select>

        <NumberField
          value={budget}
          placeholder="Budget $ (illimité)"
          onChange={setBudget}
          className="w-36"
        />

        <label className="flex items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={dedup}
            onChange={(e) => setDedup(e.target.checked)}
            className="accent-emerald-500"
          />
          1 position / instrument
        </label>
      </div>

      {dataUpdatedAt > 0 && (
        <p className="text-[10px] text-zinc-700">
          Simulation : chaque détection du screener prise à sa détection (statut executor ignoré —
          un REJECTED = executor coupé ou capital plafonné, pas une opp fausse ; filtre{' '}
          <code>status</code> pour restreindre). Capital immobilisé jusqu'à l'expiration de
          l'option, profit réalisé à l'expiration. Économie top-of-book du screener — pas de
          slippage d'exécution au-delà du walk, pas de coût de funding du hedge au-delà des fees.
        </p>
      )}

      <QueryState isLoading={isLoading} isError={isError} />

      {s && (
        <>
          {/* ── Stats principales ── */}
          <div className="grid grid-cols-2 gap-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 sm:grid-cols-4 lg:grid-cols-6">
            <Stat
              label={
                s.capital_budget_usd ? 'Capital requis (pic / budget)' : 'Capital requis (pic)'
              }
              value={fmtUsd(s.peak_capital_usd)}
              sub={
                s.capital_budget_usd
                  ? `budget ${fmtUsd(s.capital_budget_usd)}`
                  : `moy. ${fmtUsd(s.avg_capital_usd)}`
              }
              color="text-zinc-100"
            />
            <Stat
              label="Profit net réalisé"
              value={fmtUsd(s.total_net_profit_usd)}
              sub={`fees ${fmtUsd(s.total_fees_usd)}`}
              color={s.total_net_profit_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}
            />
            <Stat
              label="Profit non réalisé"
              value={fmtUsd(s.unrealized_net_profit_usd)}
              sub={`${s.n_open} position(s) ouvertes`}
              color={s.unrealized_net_profit_usd > 0 ? 'text-emerald-500/80' : 'text-zinc-500'}
            />
            <Stat
              label={s.return_on_budget_pct != null ? 'Rendement / budget' : 'Rendement / capital'}
              value={pct(s.return_on_budget_pct ?? s.return_on_peak_pct, 2)}
              color="text-zinc-200"
            />
            <Stat
              label="Rendement annualisé"
              value={pct(s.annualized_pct, 1)}
              sub={`sur ${s.period_days.toFixed(0)} j`}
              color={s.annualized_pct >= 20 ? 'text-emerald-400' : 'text-zinc-300'}
            />
            <Stat
              label="Efficience capital"
              value={pct(s.capital_efficiency_pct, 0)}
              sub="capital moyen / pic"
              color="text-zinc-300"
            />
            <Stat
              label="Positions prises"
              value={`${s.n_taken} / ${s.n_candidates}`}
              sub={`hold moy. ${s.avg_hold_days.toFixed(1)} j`}
              color="text-zinc-300"
            />
            <Stat
              label="Skips"
              value={`${s.n_skipped_dedup} dédup · ${s.n_skipped_budget} budget`}
              color="text-zinc-500"
            />
            <Stat
              label="Win rate"
              value={pct(s.win_rate_pct, 0)}
              color={s.win_rate_pct >= 80 ? 'text-emerald-500' : 'text-amber-400'}
            />
          </div>

          {/* ── Chart capital + profit cumulé ── */}
          <div className="rounded border border-zinc-800 bg-zinc-900/20 p-3">
            <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-600">
              Capital immobilisé (aire) · profit cumulé réalisé (ligne)
            </p>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    scale="time"
                    domain={['dataMin', 'dataMax']}
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={fmtDay}
                  />
                  <YAxis
                    yAxisId="cap"
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => fmtUsd(Number(v))}
                  />
                  <YAxis
                    yAxisId="pnl"
                    orientation="right"
                    stroke="#71717a"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => fmtUsd(Number(v))}
                  />
                  <Tooltip
                    contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }}
                    labelFormatter={(v) => new Date(Number(v)).toLocaleString('fr-FR')}
                    formatter={(v, name) => [fmtUsd(Number(v)), String(name)]}
                  />
                  <Area
                    yAxisId="cap"
                    name="capital immobilisé"
                    type="stepAfter"
                    dataKey="capital"
                    stroke="#60a5fa"
                    fill="#60a5fa"
                    fillOpacity={0.12}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="pnl"
                    name="profit cumulé"
                    type="stepAfter"
                    dataKey="profit"
                    stroke="#34d399"
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── Ventilation par paire ── */}
          {data.by_pair.length > 0 && (
            <div className="overflow-auto">
              <DataTable>
                <THead>
                  <HeadRow>
                    <Th>Paire</Th>
                    <Th align="right">Positions</Th>
                    <Th align="right">Profit net</Th>
                    <Th align="right">Pic capital</Th>
                  </HeadRow>
                </THead>
                <tbody>
                  {data.by_pair.map((p) => (
                    <tr key={p.pair}>
                      <Td className="whitespace-nowrap font-medium">
                        <span className={exchangeColor(p.buy_from)}>{p.buy_from}</span>
                        <span className="mx-1.5 text-zinc-400">→</span>
                        <span className={exchangeColor(p.sell_to)}>{p.sell_to}</span>
                      </Td>
                      <Td align="right" className="text-zinc-400">
                        {p.n_taken}
                      </Td>
                      <Td align="right" className="font-medium text-emerald-400">
                        {fmtUsd(p.net_profit_usd)}
                      </Td>
                      <Td align="right" className="text-zinc-300">
                        {fmtUsd(p.peak_capital_usd)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </div>
          )}

          {s.n_taken === 0 && (
            <p className="text-xs text-zinc-600">
              Aucune opportunité ne passe les filtres sur cette période.
            </p>
          )}
        </>
      )}
    </div>
  )
}
