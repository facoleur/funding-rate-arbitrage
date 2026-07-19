import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchOpportunities, type Opportunity, type OpportunityStatus } from '../api/opportunities'
import StatusBadge from '../components/StatusBadge'

function fmtAge(iso: string) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

function fmtExpiry(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: '2-digit' })
}

const STATUSES: OpportunityStatus[] = ['PENDING', 'APPROVED', 'EXECUTED', 'REJECTED', 'EXPIRED']

export default function Opportunities() {
  const [minApr, setMinApr] = useState('')
  const [underlying, setUnderlying] = useState('')
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | ''>('')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['opportunities'],
    queryFn: () => fetchOpportunities({ limit: 200 }),
    refetchInterval: 5000,
  })

  const rows: Opportunity[] = (data ?? []).filter((o) => {
    if (minApr && o.apr_pct < parseFloat(minApr)) return false
    if (underlying && !o.symbol.startsWith(underlying)) return false
    if (statusFilter && o.status !== statusFilter) return false
    return true
  })

  return (
    <div>
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-base font-semibold text-zinc-100">Opportunités</h1>
        <span className="text-xs text-zinc-500">{rows.length} lignes</span>
      </div>

      <div className="mb-4 flex gap-3 flex-wrap">
        <input
          type="number"
          placeholder="APR min %"
          value={minApr}
          onChange={(e) => setMinApr(e.target.value)}
          className="w-28 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none"
        />
        <select
          value={underlying}
          onChange={(e) => setUnderlying(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
        >
          <option value="">Tous</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as OpportunityStatus | '')}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
        >
          <option value="">Tous statuts</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-xs text-zinc-500">Chargement...</p>}
      {isError && <p className="text-xs text-red-400">Erreur de chargement</p>}

      {!isLoading && (
        <div className="overflow-auto max-h-[calc(100vh-11rem)]">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-zinc-950">
              <tr className="border-b border-zinc-800 text-left text-zinc-500">
                <th className="pb-2 pr-4">Instrument</th>
                <th className="pb-2 pr-4">Expiry</th>
                <th className="pb-2 pr-4">Route</th>
                <th className="pb-2 pr-4 text-right">Buy ask</th>
                <th className="pb-2 pr-4 text-right">Sell bid</th>
                <th className="pb-2 pr-4 text-right">Spread%</th>
                <th className="pb-2 pr-4 text-right">APR%</th>
                <th className="pb-2 pr-4 text-right">Notional</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Age</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={10} className="pt-4 text-center text-zinc-600">
                    Aucune opportunité
                  </td>
                </tr>
              )}
              {rows.map((o) => (
                <tr
                  key={o.id}
                  className={`border-b border-zinc-800/50 ${
                    o.apr_pct >= 10 ? 'bg-emerald-950/30' : ''
                  }`}
                >
                  <td className="py-1.5 pr-4 font-medium text-zinc-200">{o.instrument}</td>
                  <td className="py-1.5 pr-4 text-zinc-400">{fmtExpiry(o.expiry)}</td>
                  <td className="py-1.5 pr-4 text-zinc-400">
                    {o.buy_from} → {o.sell_to}
                  </td>
                  <td className="py-1.5 pr-4 text-right text-zinc-300">{o.top_ask.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 text-right text-zinc-300">{o.top_bid.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 text-right text-zinc-300">
                    {o.spread_pct.toFixed(2)}%
                  </td>
                  <td
                    className={`py-1.5 pr-4 text-right font-medium ${
                      o.apr_pct >= 10 ? 'text-emerald-400' : 'text-zinc-300'
                    }`}
                  >
                    {o.apr_pct.toFixed(1)}%
                  </td>
                  <td className="py-1.5 pr-4 text-right text-zinc-400">
                    ${o.max_notional_usd.toFixed(0)}
                  </td>
                  <td className="py-1.5 pr-4">
                    <StatusBadge value={o.status} />
                  </td>
                  <td className="py-1.5 text-zinc-500">{fmtAge(o.detected_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
