import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTickers, type BookRow, type ExchangeQuote } from '../api/tickers'
import { fetchExecutorState } from '../api/executor'
import { useBookFilters } from '../hooks/useBookFilters'

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtExpiry(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: '2-digit' })
}

function fmtAge(iso: string) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

// ─── Sorting ─────────────────────────────────────────────────────────────────

type SortDir = 'asc' | 'desc'
const SORTABLE = ['expiry', 'strike', 'gross', 'net', 'apr', 'notional', 'profit', 'age'] as const
type SortCol = typeof SORTABLE[number]

function isSortCol(s: string | null): s is SortCol {
  return SORTABLE.includes(s as SortCol)
}

function sortRows(rows: BookRow[], col: SortCol | null, dir: SortDir): BookRow[] {
  if (!col) return rows.slice().sort((a, b) => {
    if (a.underlying !== b.underlying) return a.underlying.localeCompare(b.underlying)
    if (a.expiry !== b.expiry) return a.expiry.localeCompare(b.expiry)
    if (a.strike !== b.strike) return a.strike - b.strike
    return a.option_type.localeCompare(b.option_type)
  })
  const sign = dir === 'asc' ? 1 : -1
  return rows.slice().sort((a, b) => {
    let av: number, bv: number
    switch (col) {
      case 'expiry': av = new Date(a.expiry).getTime(); bv = new Date(b.expiry).getTime(); break
      case 'strike': av = a.strike; bv = b.strike; break
      case 'gross':  av = a.gross_spread_pct ?? -Infinity; bv = b.gross_spread_pct ?? -Infinity; break
      case 'net':    av = a.net_spread_pct ?? -Infinity; bv = b.net_spread_pct ?? -Infinity; break
      case 'apr':    av = a.apr_pct ?? -Infinity; bv = b.apr_pct ?? -Infinity; break
      case 'notional': av = a.max_notional_usd ?? -Infinity; bv = b.max_notional_usd ?? -Infinity; break
      case 'profit': av = a.max_profit_usd ?? -Infinity; bv = b.max_profit_usd ?? -Infinity; break
      case 'age':    av = new Date(a.updated_at).getTime(); bv = new Date(b.updated_at).getTime(); break
    }
    return (av! < bv! ? -1 : av! > bv! ? 1 : 0) * sign
  })
}

// ─── Exchange URL helpers ─────────────────────────────────────────────────────

const _M = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']

function toDeribitName(n: string) {
  const m = n.match(/^([A-Z]+)-(\d{4})(\d{2})(\d{2})-(\d+(?:\.\d+)?)-([CP])$/)
  if (!m) return null
  return `${m[1]}-${parseInt(m[4])}${_M[parseInt(m[3])-1]}${m[2].slice(2)}-${m[5]}-${m[6]}`
}

function deribitUrl(inst: string, ul: string) {
  const n = toDeribitName(inst); if (!n) return null
  const [a, b] = n.split('-'); return `https://www.deribit.com/options/${ul}/${a}-${b}/${n}`
}
function deriveUrl(inst: string) { return `https://app.derive.xyz/trade/${inst}` }
function aevoUrl(inst: string) { const n = toDeribitName(inst); if (!n) return null; return `https://app.aevo.xyz/trade/${n}` }

const ABBR: Record<string, string> = { deribit: 'Db', deribit_linear: 'DL', derive: 'Dr', aevo: 'Av' }

function ExLink({ href, ex }: { href: string; ex: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="text-[9px] font-semibold px-1 py-px rounded bg-zinc-800 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 transition-colors leading-none">
      {ABBR[ex] ?? ex.slice(0, 2)}
    </a>
  )
}

function computeLegAmounts(row: BookRow) {
  if (!row.buy_exchange || !row.sell_exchange) return { buyAmt: null, sellAmt: null }
  const bq = row.exchanges[row.buy_exchange]
  if (!bq?.ask_price || !bq?.ask_size) return { buyAmt: null, sellAmt: null }
  const sq = row.exchanges[row.sell_exchange]
  if (!sq?.bid_size) return { buyAmt: null, sellAmt: null }
  const size = Math.min(bq.ask_size, sq.bid_size)
  return { buyAmt: size * bq.ask_price, sellAmt: row.sell_collateral_usd ?? null }
}

// ─── Exec criteria ───────────────────────────────────────────────────────────

type Thresholds = { max_days_to_expiry: number; min_net_spread_pct: number; min_net_profit_usd: number }

function meetsExecCriteria(row: BookRow, thresholds: Thresholds | undefined): boolean {
  if (!thresholds) return true
  if (!row.net_spread_pct || row.net_spread_pct <= 0) return false
  if (row.days_to_expiry > thresholds.max_days_to_expiry) return false
  if (row.net_spread_pct < thresholds.min_net_spread_pct) return false
  if (row.max_profit_usd !== null && row.max_profit_usd < thresholds.min_net_profit_usd) return false
  return true
}

// ─── Shared styles ────────────────────────────────────────────────────────────

const SELECT = 'rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none'

function Th({
  label, col, active, dir, onClick, className = '',
}: {
  label: string; col: SortCol; active: boolean; dir: SortDir
  onClick: (col: SortCol) => void; className?: string
}) {
  return (
    <th onClick={() => onClick(col)}
      className={`pb-2 pr-3 cursor-pointer select-none hover:text-zinc-300 ${className}`}>
      {label}
      <span className={`ml-1 ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
        {active ? (dir === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </th>
  )
}

function QuoteCell({ q, side, highlight }: { q: ExchangeQuote | undefined; side: 'bid' | 'ask'; highlight: boolean }) {
  if (!q) return <span className="text-zinc-700">—</span>
  const price = side === 'bid' ? q.bid_price : q.ask_price
  const size  = side === 'bid' ? q.bid_size  : q.ask_size
  const stale = q.is_stale
  const color = stale ? 'text-zinc-600'
    : highlight ? (side === 'bid' ? 'text-emerald-300 font-semibold' : 'text-sky-300 font-semibold')
    : side === 'bid' ? 'text-emerald-400' : 'text-red-400'
  return (
    <span className={color} title={stale ? 'Données > 60s' : undefined}>
      {stale && price != null && <span className="mr-0.5 text-amber-600">⚠</span>}
      {price != null ? price.toFixed(2) : '—'}
      {size != null && <span className="text-zinc-500 ml-1">{size.toFixed(3)}</span>}
    </span>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Book() {
  const f = useBookFilters()
  const [showLinks, setShowLinks] = useState(true)
  const sortCol  = isSortCol(f.sorting[0]?.id ?? null) ? (f.sorting[0]!.id as SortCol) : null
  const sortDir: SortDir = f.sorting[0]?.desc === false ? 'asc' : 'desc'

  const { data = [], isLoading, isError } = useQuery({
    queryKey: ['tickers', f.underlying],
    queryFn: () => fetchTickers({ underlying: f.underlying || undefined }),
    refetchInterval: 5000,
  })

  const { data: execState } = useQuery({
    queryKey: ['executor-state'],
    queryFn: fetchExecutorState,
    refetchInterval: 30_000,
    retry: false,
  })
  const thresholds = execState?.config

  // Stable exchange list — only recompute when the set of exchange names actually changes
  const allExchanges = useMemo(() => {
    const set = new Set<string>()
    for (const r of data) for (const ex of Object.keys(r.exchanges)) set.add(ex)
    return [...set].sort()
  }, [data.map(r => Object.keys(r.exchanges).sort().join()).join('|')])  // eslint-disable-line

  const filtered = useMemo(() =>
    data
      .filter(r => !f.optionType || r.option_type === f.optionType)
      .filter(r => !f.onlyArb   || (r.net_spread_pct !== null && r.net_spread_pct > 0))
      .filter(r => !f.exchange  || f.exchange in r.exchanges)
      .filter(r => !f.maxExpiry || r.expiry.slice(0, 10) <= f.maxExpiry),
    [data, f.optionType, f.onlyArb, f.exchange, f.maxExpiry],
  )

  const rows = useMemo(() => sortRows(filtered, sortCol, sortDir), [filtered, sortCol, sortDir])

  function handleSort(col: SortCol) {
    const desc = sortCol === col ? sortDir === 'asc' : !['net', 'gross', 'profit', 'notional'].includes(col)
    f.onSortingChange([{ id: col, desc }])
  }

  function th(col: SortCol, label: string, className = '') {
    return <Th col={col} label={label} active={sortCol === col} dir={sortDir} onClick={handleSort} className={className} />
  }

  return (
    <div className="h-full flex flex-col">
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-base font-semibold text-zinc-100">Book</h1>
        <span className="text-xs text-zinc-500">
          {rows.length}{data.length !== rows.length ? ` / ${data.length}` : ''} instruments
        </span>
      </div>

      <div className="mb-4 flex flex-wrap gap-3 items-center">
        <select value={f.underlying} onChange={e => f.setUnderlying(e.target.value)} className={SELECT}>
          <option value="">BTC + ETH</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </select>

        <select value={f.optionType} onChange={e => f.setOptionType(e.target.value)} className={SELECT}>
          <option value="">Calls + Puts</option>
          <option value="C">Calls</option>
          <option value="P">Puts</option>
        </select>

        <select value={f.exchange} onChange={e => f.setExchange(e.target.value)} className={SELECT}>
          <option value="">Tous les exchanges</option>
          {allExchanges.map(ex => <option key={ex} value={ex}>{ex}</option>)}
        </select>

        <div className="flex items-center gap-1.5">
          <label className="text-xs text-zinc-500">Expiry ≤</label>
          <input type="date" value={f.maxExpiry} onChange={e => f.setMaxExpiry(e.target.value)}
            className={SELECT + ' w-36'} />
        </div>

        <label className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer select-none">
          <input type="checkbox" checked={f.onlyArb} onChange={e => f.setOnlyArb(e.target.checked)}
            className="accent-emerald-500" />
          Arb seulement
        </label>

        <label className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer select-none">
          <input type="checkbox" checked={showLinks} onChange={e => setShowLinks(e.target.checked)}
            className="accent-zinc-500" />
          Liens exchanges
        </label>

        {f.hasFilters && (
          <button onClick={f.resetFilters} className="text-xs text-zinc-500 hover:text-zinc-200">
            Reset filtres
          </button>
        )}
      </div>

      {isLoading && <p className="text-xs text-zinc-500">Chargement...</p>}
      {isError   && <p className="text-xs text-red-400">Erreur de chargement</p>}
      {!isLoading && rows.length === 0 && !isError && (
        <p className="text-xs text-zinc-500">Aucune donnée.</p>
      )}

      {rows.length > 0 && (
        <div className="flex-1 min-h-0 overflow-auto -mr-6 -mb-6">
          <table className="w-full text-xs border-separate border-spacing-0 whitespace-nowrap">
            <thead className="sticky top-0 z-10 bg-zinc-950">
              <tr className="border-b border-zinc-800 text-center text-zinc-500">
                <th className="pb-2 pr-3 text-left sticky left-0 bg-zinc-950 z-20">Instrument</th>
                {th('expiry', 'Expiry')}
                {th('strike', 'Strike')}
                <th className="pb-2 pr-3">Type</th>
                {allExchanges.map(ex => (
                  <th key={ex} className="pb-2 pr-3" colSpan={2}>{ex}</th>
                ))}
                {th('gross', 'Gross%')}
                {th('net', 'Net%')}
                {th('apr', 'APR%')}
                {th('notional', 'Cap.$')}
                {th('profit', 'Profit$')}
                <th className="pb-2 pr-3">Arb</th>
                <th className="pb-2 pr-3 text-sky-500/70">Buy$</th>
                <th className="pb-2 pr-3 text-emerald-500/70" title="Collatéral requis pour la jambe vente (formule marge initiale ≈ max(10%, 15%-OTM%) × S × size)">Margin$</th>
                {th('age', 'Age')}
              </tr>
              <tr className="border-b border-zinc-800/40 text-center text-zinc-600">
                <th className="sticky left-0 bg-zinc-950 z-20" />
                <th colSpan={3} />
                {allExchanges.map(ex => (
                  <th key={ex} colSpan={2} className="pb-1 font-normal text-[10px]">
                    <span className="pr-5">bid</span>
                    <span>ask</span>
                  </th>
                ))}
                <th colSpan={8} />
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const hasArb  = row.net_spread_pct !== null && row.net_spread_pct > 0
                const hasGross = row.gross_spread_pct !== null && row.gross_spread_pct > 0
                const dUrl = deribitUrl(row.instrument, row.underlying)
                const avUrl = aevoUrl(row.instrument)
                const { buyAmt, sellAmt } = computeLegAmounts(row)
                const eligible = meetsExecCriteria(row, thresholds)

                return (
                  <tr key={row.instrument} className={`border-b border-zinc-800/40 ${hasArb ? 'bg-emerald-950/20' : ''} ${!eligible ? 'opacity-50' : ''}`}>
                    <td className="py-1 pr-3 sticky left-0 bg-zinc-950 z-10">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-zinc-200">{row.instrument}</span>
                        {showLinks && row.exchanges['deribit'] && dUrl && <ExLink href={dUrl} ex="deribit" />}
                        {showLinks && row.exchanges['deribit_linear'] && dUrl && <ExLink href={dUrl} ex="deribit_linear" />}
                        {showLinks && row.exchanges['derive'] && <ExLink href={deriveUrl(row.instrument)} ex="derive" />}
                        {showLinks && row.exchanges['aevo'] && avUrl && <ExLink href={avUrl} ex="aevo" />}
                      </div>
                    </td>
                    <td className="py-1 pr-3 text-zinc-400">{fmtExpiry(row.expiry)}</td>
                    <td className="py-1 pr-3 text-right text-zinc-300 tabular-nums">{row.strike.toLocaleString()}</td>
                    <td className="py-1 pr-3">
                      <span className={`font-medium ${row.option_type === 'C' ? 'text-blue-400' : 'text-orange-400'}`}>
                        {row.option_type === 'C' ? 'Call' : 'Put'}
                      </span>
                    </td>
                    {allExchanges.map(ex => {
                      const q = row.exchanges[ex]
                      return (
                        <>
                          <td key={`${ex}-bid`} className={`py-1 pr-1 text-right ${hasArb && ex === row.sell_exchange ? 'bg-emerald-950/40' : ''}`}>
                            <QuoteCell q={q} side="bid" highlight={hasArb && ex === row.sell_exchange} />
                          </td>
                          <td key={`${ex}-ask`} className={`py-1 pr-3 text-right ${hasArb && ex === row.buy_exchange ? 'bg-sky-950/40' : ''}`}>
                            <QuoteCell q={q} side="ask" highlight={hasArb && ex === row.buy_exchange} />
                          </td>
                        </>
                      )
                    })}
                    <td className={`py-1 pr-3 text-right ${hasGross ? 'text-zinc-300' : 'text-zinc-500'}`}>
                      {row.gross_spread_pct != null ? `${row.gross_spread_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right font-medium ${hasArb ? 'text-emerald-400' : 'text-zinc-500'}`}>
                      {row.net_spread_pct != null ? `${row.net_spread_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right font-medium ${hasArb ? 'text-emerald-300' : 'text-zinc-500'}`}>
                      {row.apr_pct != null ? `${row.apr_pct.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right ${hasArb ? 'text-zinc-300' : 'text-zinc-600'}`}>
                      {row.max_notional_usd != null ? `$${row.max_notional_usd.toFixed(2)}` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right font-medium ${hasArb ? 'text-emerald-300' : 'text-zinc-500'}`}>
                      {row.max_profit_usd != null ? `$${row.max_profit_usd.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-1 pr-3 text-xs">
                      {hasArb
                        ? <span className="text-emerald-400">{row.buy_exchange} → {row.sell_exchange}</span>
                        : <span className="text-zinc-600">—</span>}
                    </td>
                    <td className={`py-1 pr-3 text-right ${hasArb ? 'text-sky-300' : 'text-zinc-600'}`}>
                      {buyAmt != null ? `$${buyAmt.toFixed(2)}` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right ${hasArb ? 'text-emerald-300' : 'text-zinc-600'}`}>
                      {sellAmt != null ? `$${sellAmt.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-1 pr-3 text-zinc-500">{fmtAge(row.updated_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
