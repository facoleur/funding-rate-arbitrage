import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTrades, type Trade, type TradeStatus, type Mode } from '../api/trades'
import StatusBadge from '../components/StatusBadge'
import { fmtDateTimeSec } from '../lib/format'
import { Select } from '../components/ui/Field'
import Pagination from '../components/ui/Pagination'
import QueryState from '../components/ui/QueryState'

function PnL({ value }: { value: number | null }) {
  if (value == null) return <span className="text-zinc-500">—</span>
  const cls = value >= 0 ? 'text-emerald-400' : 'text-red-400'
  return (
    <span className={cls}>
      {value >= 0 ? '+' : ''}
      {value.toFixed(2)}
    </span>
  )
}

const STATUSES: TradeStatus[] = ['PLACING', 'FILLED', 'HEDGED', 'STUCK', 'FAILED']
const MODES: Mode[] = ['live', 'paper', 'backtest']
const PAGE_SIZE = 50

export default function Trades() {
  const [modeFilter, setModeFilter] = useState<Mode | ''>('')
  const [statusFilter, setStatusFilter] = useState<TradeStatus | ''>('')
  const [offset, setOffset] = useState(0)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['trades', modeFilter, statusFilter, offset],
    queryFn: () =>
      fetchTrades({
        mode: modeFilter || undefined,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    refetchInterval: 10000,
  })

  const rows: Trade[] = data ?? []

  return (
    <div>
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-base font-semibold text-zinc-100">Trades</h1>
        <span className="text-xs text-zinc-500">{rows.length} résultats</span>
      </div>

      <div className="mb-4 flex gap-3">
        <Select
          value={modeFilter}
          onChange={(v) => {
            setModeFilter(v as Mode | '')
            setOffset(0)
          }}
        >
          <option value="">Tous modes</option>
          {MODES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
        <Select
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v as TradeStatus | '')
            setOffset(0)
          }}
        >
          <option value="">Tous statuts</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </div>

      <QueryState isLoading={isLoading} isError={isError} />

      {!isLoading && (
        <>
          <div className="overflow-auto max-h-[calc(100vh-11rem)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-zinc-950">
                <tr className="border-b border-zinc-800 text-left text-zinc-500">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Instrument</th>
                  <th className="pb-2 pr-4">Route</th>
                  <th className="pb-2 pr-4 text-right">Size</th>
                  <th className="pb-2 pr-4 text-right">Buy fill</th>
                  <th className="pb-2 pr-4 text-right">Sell fill</th>
                  <th className="pb-2 pr-4 text-right">Slippage%</th>
                  <th className="pb-2 pr-4 text-right">PnL $</th>
                  <th className="pb-2 pr-4 text-right">Fees $</th>
                  <th className="pb-2 pr-4">Mode</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={11} className="pt-4 text-center text-zinc-500">
                      Aucun trade
                    </td>
                  </tr>
                )}
                {rows.map((t) => {
                  const instrument = t.error?.includes('-') ? t.error : `opp #${t.opportunity_id}`
                  return (
                    <tr key={t.id} className="border-b border-zinc-800/50">
                      <td className="py-1.5 pr-4 text-zinc-500 whitespace-nowrap">
                        {fmtDateTimeSec(t.opened_at)}
                      </td>
                      <td className="py-1.5 pr-4 font-medium text-zinc-200 whitespace-nowrap">
                        {instrument}
                      </td>
                      <td className="py-1.5 pr-4 text-zinc-400 whitespace-nowrap">
                        {t.buy_exchange} → {t.sell_exchange}
                      </td>
                      <td className="py-1.5 pr-4 text-right text-zinc-300">{t.requested_size}</td>
                      <td className="py-1.5 pr-4 text-right text-zinc-300">
                        {t.buy_fill_price != null ? t.buy_fill_price.toFixed(2) : '—'}
                      </td>
                      <td className="py-1.5 pr-4 text-right text-zinc-300">
                        {t.sell_fill_price != null ? t.sell_fill_price.toFixed(2) : '—'}
                      </td>
                      <td className="py-1.5 pr-4 text-right text-zinc-400">
                        {t.slippage_pct != null ? `${t.slippage_pct.toFixed(2)}%` : '—'}
                      </td>
                      <td className="py-1.5 pr-4 text-right">
                        <PnL value={t.net_pnl_usd} />
                      </td>
                      <td className="py-1.5 pr-4 text-right text-zinc-400">
                        {t.fees_usd != null ? `$${t.fees_usd.toFixed(2)}` : '—'}
                      </td>
                      <td className="py-1.5 pr-4">
                        <StatusBadge value={t.mode} />
                      </td>
                      <td className="py-1.5">
                        <StatusBadge value={t.status} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <Pagination
            offset={offset}
            pageSize={PAGE_SIZE}
            count={rows.length}
            onOffsetChange={setOffset}
          />
        </>
      )}
    </div>
  )
}
