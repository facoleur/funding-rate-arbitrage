import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchOpportunities,
  fetchOpportunityStats,
  type OpportunityStatus,
  type SortCol,
} from '../api/opportunities'

const PAGE_SIZES = [25, 50, 100, 200] as const

const EXCHANGE_COLORS: Record<string, string> = {
  derive: 'text-violet-400',
  deribit: 'text-sky-400',
  deribit_linear: 'text-cyan-400',
}

function ExBadge({ name }: { name: string }) {
  return <span className={`font-medium ${EXCHANGE_COLORS[name] ?? 'text-zinc-400'}`}>{name}</span>
}

function fmt$(v: number) {
  return v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(2)}`
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_COLORS: Record<OpportunityStatus, string> = {
  PENDING:  'text-amber-400',
  APPROVED: 'text-sky-400',
  EXECUTED: 'text-emerald-400',
  REJECTED: 'text-zinc-500',
  EXPIRED:  'text-zinc-500',
}

type SortDir = 'asc' | 'desc'

const COLS: { key: SortCol; label: string; right?: boolean }[] = [
  { key: 'detected_at',     label: 'Date' },
  { key: 'net_profit_usd',  label: 'Profit net',   right: true },
  { key: 'fees_usd',        label: 'Fees',          right: true },
  { key: 'max_notional_usd',label: 'Notionnel',     right: true },
  { key: 'spread_pct',      label: 'Spread net',    right: true },
  { key: 'apr_pct',         label: 'APR',           right: true },
]

function SortTh({
  col, label, right, active, dir, onSort,
}: {
  col: SortCol; label: string; right?: boolean
  active: boolean; dir: SortDir; onSort: (c: SortCol) => void
}) {
  return (
    <th
      className={`pb-2 pr-3 cursor-pointer select-none hover:text-zinc-300 ${right ? 'text-right' : ''}`}
      onClick={() => onSort(col)}
    >
      {label}
      <span className="ml-1 text-zinc-400">
        {active ? (dir === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </th>
  )
}

function Select({
  value, onChange, children, className = '',
}: {
  value: string | number; onChange: (v: string) => void
  children: React.ReactNode; className?: string
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none ${className}`}
    >
      {children}
    </select>
  )
}

export default function History() {
  const [days, setDays]           = useState(30)
  const [symbol, setSymbol]       = useState('')
  const [statusFilter, setStatus] = useState<OpportunityStatus | ''>('')
  const [minApr, setMinApr]       = useState('')
  const [minProfit, setMinProfit] = useState('')
  const [pairFilter, setPairFilter] = useState('')
  const [network, setNetwork]     = useState<'mainnet' | 'testnet' | ''>('mainnet')
  const [pageSize, setPageSize]   = useState<number>(100)
  const [offset, setOffset]       = useState(0)
  const [sortBy, setSortBy]       = useState<SortCol>('detected_at')
  const [sortDir, setSortDir]     = useState<SortDir>('desc')

  function handleSort(col: SortCol) {
    if (col === sortBy) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(col)
      setSortDir(col === 'detected_at' ? 'desc' : 'desc')
    }
    setOffset(0)
  }

  function resetFilters() {
    setSymbol(''); setStatus(''); setMinApr(''); setMinProfit('')
    setPairFilter(''); setNetwork('mainnet'); setOffset(0)
  }

  const hasActiveFilter = symbol || statusFilter || minApr || minProfit || pairFilter || network !== 'mainnet'

  const { data: stats } = useQuery({
    queryKey: ['opp-stats', days, symbol, network],
    queryFn: () => fetchOpportunityStats({ days, symbol: symbol || undefined, network: network || undefined }),
    refetchInterval: 30_000,
  })

  const { data: opps, isLoading, isFetching } = useQuery({
    queryKey: ['opp-history', days, symbol, statusFilter, minApr, minProfit, pairFilter, network, pageSize, offset, sortBy, sortDir],
    queryFn: () => {
      const [bf, st] = pairFilter ? pairFilter.split('→').map(s => s.trim()) : ['', '']
      return fetchOpportunities({
        days,
        symbol: symbol || undefined,
        status: statusFilter || undefined,
        min_apr: minApr ? Number(minApr) : undefined,
        min_profit: minProfit ? Number(minProfit) : undefined,
        buy_from: bf || undefined,
        sell_to: st || undefined,
        network: network || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: pageSize,
        offset,
      })
    },
    refetchInterval: 30_000,
  })

  const page = Math.floor(offset / pageSize) + 1

  return (
    <div className="space-y-5">
      {/* ── Filtres globaux ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-base font-semibold text-zinc-100 mr-1">Historique</h1>

        <Select value={days} onChange={v => { setDays(Number(v)); setOffset(0) }}>
          <option value={7}>7 jours</option>
          <option value={30}>30 jours</option>
          <option value={90}>90 jours</option>
          <option value={365}>1 an</option>
        </Select>

        <Select value={symbol} onChange={v => { setSymbol(v); setOffset(0) }}>
          <option value="">BTC + ETH</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>

        <Select value={statusFilter} onChange={v => { setStatus(v as OpportunityStatus | ''); setOffset(0) }}>
          <option value="">Tous statuts</option>
          <option value="EXECUTED">EXECUTED</option>
          <option value="PENDING">PENDING</option>
          <option value="REJECTED">REJECTED</option>
          <option value="EXPIRED">EXPIRED</option>
        </Select>

        <Select value={network} onChange={v => { setNetwork(v as 'mainnet' | 'testnet' | ''); setOffset(0) }}>
          <option value="mainnet">mainnet</option>
          <option value="testnet">testnet</option>
          <option value="">tous réseaux</option>
        </Select>

        <input
          type="number"
          placeholder="APR min %"
          value={minApr}
          onChange={e => { setMinApr(e.target.value); setOffset(0) }}
          className="w-24 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none"
        />

        <input
          type="number"
          placeholder="Profit min $"
          value={minProfit}
          onChange={e => { setMinProfit(e.target.value); setOffset(0) }}
          className="w-24 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none"
        />

        {hasActiveFilter && (
          <button onClick={resetFilters} className="text-xs text-zinc-400 hover:text-zinc-200">
            × reset filtres
          </button>
        )}
      </div>

      {/* ── Stats par paire ── */}
      {stats && stats.length > 0 && (
        <div>
          <p className="text-xs text-zinc-500 mb-1.5">
            Cliquer sur une paire pour filtrer · profit = potentiel brut (non dédupliqué)
          </p>
          <div className="overflow-auto">
            <table className="w-full text-xs border-separate border-spacing-0">
              <thead>
                <tr className="text-left text-zinc-500 border-b border-zinc-800">
                  <th className="pb-2 pr-4">Paire</th>
                  <th className="pb-2 pr-4 text-right">Opps</th>
                  <th className="pb-2 pr-4 text-right">Profit net total</th>
                  <th className="pb-2 pr-4 text-right">Fees totales</th>
                  <th className="pb-2 pr-4 text-right">Meilleure opp</th>
                  <th className="pb-2 text-right">APR moy.</th>
                </tr>
              </thead>
              <tbody>
                {stats.map(s => (
                  <tr
                    key={s.pair}
                    onClick={() => { setPairFilter(pairFilter === s.pair ? '' : s.pair); setOffset(0) }}
                    className={`border-b border-zinc-800/40 cursor-pointer hover:bg-zinc-800/30 transition-colors ${
                      pairFilter === s.pair ? 'bg-zinc-800/50' : ''
                    }`}
                  >
                    <td className="py-1.5 pr-4 font-medium">
                      <ExBadge name={s.buy_from} />
                      <span className="mx-1.5 text-zinc-400">→</span>
                      <ExBadge name={s.sell_to} />
                      {pairFilter === s.pair && <span className="ml-2 text-zinc-400 text-[10px]">✓ filtré</span>}
                    </td>
                    <td className="py-1.5 pr-4 text-right text-zinc-400">{s.count.toLocaleString()}</td>
                    <td className="py-1.5 pr-4 text-right text-emerald-400 font-medium">{fmt$(s.total_net_profit_usd)}</td>
                    <td className="py-1.5 pr-4 text-right text-zinc-500">{fmt$(s.total_fees_usd)}</td>
                    <td className="py-1.5 pr-4 text-right text-zinc-300">{fmt$(s.best_net_profit_usd)}</td>
                    <td className="py-1.5 text-right text-zinc-400">{s.avg_apr_pct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Table détaillée ── */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Détail {pairFilter ? `— ${pairFilter}` : ''}
          </h2>
          <span className="text-xs text-zinc-500">
            {isFetching && !isLoading ? '↻' : ''}
          </span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-zinc-500">Par page :</span>
            <Select value={pageSize} onChange={v => { setPageSize(Number(v)); setOffset(0) }} className="w-16">
              {PAGE_SIZES.map(n => <option key={n} value={n}>{n}</option>)}
            </Select>
          </div>
        </div>

        {isLoading && <p className="text-xs text-zinc-500">Chargement...</p>}

        {opps && opps.length === 0 && !isLoading && (
          <p className="text-xs text-zinc-500">Aucune opportunité sur cette période.</p>
        )}

        {opps && opps.length > 0 && (
          <>
            <div className="overflow-auto max-h-[calc(100vh-24rem)]">
              <table className="w-full text-xs border-separate border-spacing-0">
                <thead className="sticky top-0 z-10 bg-zinc-950">
                  <tr className="text-left text-zinc-500 border-b border-zinc-800">
                    {COLS.map(c => (
                      <SortTh
                        key={c.key}
                        col={c.key}
                        label={c.label}
                        right={c.right}
                        active={sortBy === c.key}
                        dir={sortDir}
                        onSort={handleSort}
                      />
                    ))}
                    <th className="pb-2 pr-3">Instrument</th>
                    <th className="pb-2 pr-3">Paire</th>
                    <th className="pb-2 pr-3">Réseau</th>
                    <th className="pb-2">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {opps.map(o => (
                    <tr key={o.id} className="border-b border-zinc-800/30 hover:bg-zinc-900/40">
                      <td className="py-1 pr-3 text-zinc-500 whitespace-nowrap">{fmtDate(o.detected_at)}</td>
                      <td className="py-1 pr-3 text-right font-medium text-emerald-400">{fmt$(o.net_profit_usd)}</td>
                      <td className="py-1 pr-3 text-right text-zinc-500">{fmt$(o.fees_usd)}</td>
                      <td className="py-1 pr-3 text-right text-zinc-400">{fmt$(o.max_notional_usd)}</td>
                      <td className="py-1 pr-3 text-right text-zinc-300">{o.spread_pct.toFixed(2)}%</td>
                      <td className="py-1 pr-3 text-right text-zinc-400">{o.apr_pct.toFixed(1)}%</td>
                      <td className="py-1 pr-3 text-zinc-300 font-mono text-[11px]">{o.instrument}</td>
                      <td className="py-1 pr-3 whitespace-nowrap">
                        <ExBadge name={o.buy_from} />
                        <span className="mx-1 text-zinc-400">→</span>
                        <ExBadge name={o.sell_to} />
                      </td>
                      <td className="py-1 pr-3">
                        <span className={o.network === 'mainnet' ? 'text-emerald-500' : 'text-amber-500'}>
                          {o.network}
                        </span>
                      </td>
                      <td className={`py-1 ${STATUS_COLORS[o.status]}`}>{o.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="mt-3 flex items-center gap-3 text-xs text-zinc-500">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - pageSize))}
                className="px-2 py-1 rounded border border-zinc-700 disabled:opacity-30 enabled:hover:text-zinc-200 enabled:hover:border-zinc-500"
              >
                ← Précédent
              </button>
              <span>Page {page} · {offset + 1}–{offset + opps.length}</span>
              <button
                disabled={opps.length < pageSize}
                onClick={() => setOffset(offset + pageSize)}
                className="px-2 py-1 rounded border border-zinc-700 disabled:opacity-30 enabled:hover:text-zinc-200 enabled:hover:border-zinc-500"
              >
                Suivant →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
