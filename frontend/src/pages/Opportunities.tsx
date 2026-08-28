import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchOpportunities, type Opportunity, type OpportunityStatus } from '../api/opportunities'
import StatusBadge from '../components/StatusBadge'

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmtAge(iso: string) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

function fmtExpiry(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: '2-digit' })
}

function fmtDte(dte: number) {
  if (dte < 1) return `${Math.round(dte * 24)}h`
  return `${Math.round(dte)}j`
}

function fmtUsd(n: number) {
  if (n === 0) return '—'
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(2)}k`
  return `$${n.toFixed(2)}`
}

function displayEconomics(o: Opportunity) {
  const verified = o.verified_tradeable_size !== null
  return {
    buyPrice: verified ? o.verified_buy_limit! : o.top_ask,
    sellPrice: verified ? o.verified_sell_limit! : o.top_bid,
    size: verified ? o.verified_tradeable_size! : o.tradeable_size,
    buyPremium: verified ? o.verified_buy_premium_usd! : o.buy_premium_usd,
    sellPremium: verified ? o.verified_sell_premium_usd! : o.sell_premium_usd,
    margin: verified ? o.verified_estimated_short_margin_usd! : o.estimated_short_margin_usd,
    capital: verified ? o.verified_capital_required_usd! : o.capital_required_usd,
    fees: verified ? o.verified_fees_usd! : o.fees_usd,
    netProfit: verified ? o.verified_net_profit_usd! : o.net_profit_usd,
    netReturn: verified ? o.verified_net_return_pct! : o.net_return_pct,
    apr: verified ? o.verified_apr_pct! : o.apr_pct,
  }
}

// ─── columns ──────────────────────────────────────────────────────────────────

type ColId =
  | 'type' | 'strike' | 'expiry' | 'dte' | 'route'
  | 'size' | 'buy_ask' | 'sell_bid'
  | 'buy_premium' | 'sell_premium' | 'margin' | 'capital' | 'fees' | 'net_profit'
  | 'net_return' | 'apr' | 'status' | 'age'

interface ColDef {
  id: ColId
  label: string
  tip?: string
  right?: boolean
  defaultVisible: boolean
}

const COLS: ColDef[] = [
  { id: 'type',        label: 'Type',        defaultVisible: false },
  { id: 'strike',      label: 'Strike',      right: true, defaultVisible: false },
  { id: 'expiry',      label: 'Expiry',      defaultVisible: true },
  { id: 'dte',         label: 'DTE',         right: true, defaultVisible: true },
  { id: 'route',       label: 'Route',       defaultVisible: true },
  { id: 'size',        label: 'Size',        right: true, defaultVisible: false },
  { id: 'buy_ask',     label: 'Buy ask',     right: true, defaultVisible: false },
  { id: 'sell_bid',    label: 'Sell bid',    right: true, defaultVisible: false },
  { id: 'buy_premium', label: 'Buy premium', right: true, defaultVisible: true },
  { id: 'sell_premium',label: 'Sell premium', right: true, defaultVisible: false },
  { id: 'margin',      label: 'Est. margin', right: true, defaultVisible: true },
  { id: 'capital',     label: 'Capital',     tip: 'Prime achat + marge short estimée, sans offset de prime vente', right: true, defaultVisible: true },
  { id: 'fees',        label: 'Fees',        right: true, defaultVisible: true },
  { id: 'net_profit',  label: 'Net profit',  right: true, defaultVisible: true },
  { id: 'net_return',  label: 'Net return %', tip: 'Profit net / capital requis', right: true, defaultVisible: true },
  { id: 'apr',         label: 'APR %',       tip: 'Annualisé sur capital total (prime achat + marge sell estimée)', right: true, defaultVisible: true },
  { id: 'status',      label: 'Status',      defaultVisible: true },
  { id: 'age',         label: 'Age',         right: true, defaultVisible: true },
]

// ─── sort ─────────────────────────────────────────────────────────────────────

type SortKey = 'instrument' | ColId

function sortVal(o: Opportunity, col: SortKey): number | string {
  const d = displayEconomics(o)
  switch (col) {
    case 'instrument':  return o.instrument
    case 'type':        return o.option_type
    case 'strike':      return o.strike
    case 'expiry':      return new Date(o.expiry).getTime()
    case 'dte':         return o.days_to_expiry
    case 'route':       return `${o.buy_from}→${o.sell_to}`
    case 'size':        return d.size
    case 'buy_ask':     return d.buyPrice
    case 'sell_bid':    return d.sellPrice
    case 'buy_premium': return d.buyPremium
    case 'sell_premium':return d.sellPremium
    case 'margin':      return d.margin
    case 'capital':     return d.capital
    case 'fees':        return d.fees
    case 'net_profit':  return d.netProfit
    case 'net_return':  return d.netReturn
    case 'apr':         return d.apr
    case 'status':      return o.status
    case 'age':         return new Date(o.detected_at).getTime()
    default:            return 0
  }
}

// ─── constants ────────────────────────────────────────────────────────────────

const STATUSES: OpportunityStatus[] = ['PENDING', 'APPROVED', 'EXECUTED', 'REJECTED', 'EXPIRED']
const DEFAULT_VISIBLE = new Set(COLS.filter((c) => c.defaultVisible).map((c) => c.id))

const TH_BASE =
  'cursor-pointer select-none whitespace-nowrap border-b border-zinc-800 pb-2 pr-6 text-zinc-500 hover:text-zinc-300'
const TD_BASE =
  'whitespace-nowrap border-b border-zinc-800/50 py-1.5 pr-6'
const STICKY_BG = 'bg-zinc-950'
const HOT_BG = 'bg-emerald-950/30'

// ─── component ────────────────────────────────────────────────────────────────

export default function Opportunities() {
  const [minApr, setMinApr] = useState('')
  const [underlying, setUnderlying] = useState('')
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | ''>('')
  const [visible, setVisible] = useState<Set<ColId>>(DEFAULT_VISIBLE)
  const [sortCol, setSortCol] = useState<SortKey>('apr')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [showColMenu, setShowColMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showColMenu) return
    function onMouseDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowColMenu(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [showColMenu])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['opportunities'],
    queryFn: () => fetchOpportunities({ limit: 200 }),
    refetchInterval: 5000,
  })

  const filtered: Opportunity[] = (data ?? []).filter((o) => {
    if (minApr && displayEconomics(o).apr < parseFloat(minApr)) return false
    if (underlying && !o.symbol.startsWith(underlying)) return false
    if (statusFilter && o.status !== statusFilter) return false
    return true
  })

  const rows = [...filtered].sort((a, b) => {
    const av = sortVal(a, sortCol)
    const bv = sortVal(b, sortCol)
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortDir === 'asc' ? cmp : -cmp
  })

  function toggleSort(col: SortKey) {
    if (sortCol === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortCol(col); setSortDir('desc') }
  }

  function sortIndicator(col: SortKey) {
    if (sortCol !== col) return <span className="ml-0.5 text-zinc-700">⇅</span>
    return <span className="ml-0.5 text-zinc-300">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  function th(col: SortKey, label: string, opts: { right?: boolean; tip?: string } = {}) {
    return (
      <th
        key={col}
        title={opts.tip}
        onClick={() => toggleSort(col)}
        className={`${TH_BASE} ${opts.right ? 'text-right' : ''}`}
      >
        {label}{sortIndicator(col)}
      </th>
    )
  }

  function toggleCol(id: ColId) {
    setVisible((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 7rem)' }}>
      {/* toolbar */}
      <div className="mb-3 flex flex-shrink-0 flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-zinc-100">Opportunités</h1>
        <span className="text-xs text-zinc-500">{rows.length} lignes</span>

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
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        {/* column picker */}
        <div className="relative ml-auto" ref={menuRef}>
          <button
            onClick={() => setShowColMenu((v) => !v)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500"
          >
            Colonnes
          </button>
          {showColMenu && (
            <div className="absolute right-0 top-7 z-50 min-w-[150px] rounded border border-zinc-700 bg-zinc-900 p-2 shadow-xl">
              {COLS.map((c) => (
                <label
                  key={c.id}
                  className="flex cursor-pointer items-center gap-2 py-0.5 text-xs text-zinc-300 hover:text-zinc-100"
                >
                  <input
                    type="checkbox"
                    checked={visible.has(c.id)}
                    onChange={() => toggleCol(c.id)}
                    className="accent-emerald-500"
                  />
                  {c.label}
                  {c.tip && <span className="text-zinc-600" title={c.tip}>?</span>}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {isLoading && <p className="text-xs text-zinc-500">Chargement...</p>}
      {isError && <p className="text-xs text-red-400">Erreur de chargement</p>}

      {/* table */}
      <div className="flex-1 overflow-auto">
        <table className="border-separate border-spacing-0 text-xs">
          <thead>
            <tr className="text-left">
              {/* instrument — sticky left + top */}
              <th
                onClick={() => toggleSort('instrument')}
                className={`${TH_BASE} sticky left-0 top-0 z-30 ${STICKY_BG} pl-0`}
              >
                Instrument{sortIndicator('instrument')}
              </th>
              {visible.has('type')        && th('type',        'Type')}
              {visible.has('strike')      && th('strike',      'Strike',     { right: true })}
              {visible.has('expiry')      && th('expiry',      'Expiry')}
              {visible.has('dte')         && th('dte',         'DTE',        { right: true })}
              {visible.has('route')       && (
                <th className={`${TH_BASE}`}>Route</th>
              )}
              {visible.has('size')        && th('size',        'Size',       { right: true })}
              {visible.has('buy_ask')     && th('buy_ask',     'Buy ask',    { right: true })}
              {visible.has('sell_bid')    && th('sell_bid',    'Sell bid',   { right: true })}
              {visible.has('buy_premium') && th('buy_premium', 'Buy premium', { right: true })}
              {visible.has('sell_premium')&& th('sell_premium','Sell premium', { right: true })}
              {visible.has('margin')      && th('margin',      'Est. margin', { right: true })}
              {visible.has('capital')     && th('capital',     'Capital',    { right: true, tip: 'Prime achat + marge short estimée, sans offset de prime vente' })}
              {visible.has('fees')        && th('fees',        'Fees',       { right: true })}
              {visible.has('net_profit')  && th('net_profit',  'Net profit', { right: true })}
              {visible.has('net_return')  && th('net_return',  'Net return %', { right: true, tip: 'Profit net / capital requis' })}
              {visible.has('apr')         && th('apr',         'APR %',      { right: true, tip: 'Annualisé sur capital total (prime achat + marge sell estimée)' })}
              {visible.has('status')      && <th className={`${TH_BASE}`}>Status</th>}
              {visible.has('age')         && th('age',         'Age',        { right: true })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={99} className="pt-6 text-center text-zinc-600">
                  Aucune opportunité
                </td>
              </tr>
            )}
            {rows.map((o) => {
              const d = displayEconomics(o)
              const hot = d.apr >= 10
              const rowBg = hot ? HOT_BG : STICKY_BG

              return (
                <tr key={o.id}>
                  {/* instrument — sticky left */}
                  <td className={`sticky left-0 z-10 ${rowBg} ${TD_BASE} font-medium text-zinc-200 pl-0`}>
                    {o.instrument}
                  </td>

                  {visible.has('type') && (
                    <td className={`${TD_BASE} text-zinc-400`}>{o.option_type}</td>
                  )}
                  {visible.has('strike') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-400`}>
                      {o.strike.toLocaleString()}
                    </td>
                  )}
                  {visible.has('expiry') && (
                    <td className={`${TD_BASE} text-zinc-400`}>{fmtExpiry(o.expiry)}</td>
                  )}
                  {visible.has('dte') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-400`}>
                      {fmtDte(o.days_to_expiry)}
                    </td>
                  )}
                  {visible.has('route') && (
                    <td className={`${TD_BASE} text-zinc-400`}>
                      {o.buy_from} → {o.sell_to}
                    </td>
                  )}
                  {visible.has('size') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {d.size.toFixed(4)}
                    </td>
                  )}
                  {visible.has('buy_ask') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {d.buyPrice.toFixed(4)}
                    </td>
                  )}
                  {visible.has('sell_bid') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {d.sellPrice.toFixed(4)}
                    </td>
                  )}
                  {visible.has('buy_premium') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {fmtUsd(d.buyPremium)}
                    </td>
                  )}
                  {visible.has('sell_premium') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {fmtUsd(d.sellPremium)}
                    </td>
                  )}
                  {visible.has('margin') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {fmtUsd(d.margin)}
                    </td>
                  )}
                  {visible.has('capital') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-300`}>
                      {fmtUsd(d.capital)}
                    </td>
                  )}
                  {visible.has('fees') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-500`}>
                      {fmtUsd(d.fees)}
                    </td>
                  )}
                  {visible.has('net_profit') && (
                    <td className={`${TD_BASE} text-right tabular-nums ${hot ? 'text-emerald-400' : 'text-zinc-300'}`}>
                      {fmtUsd(d.netProfit)}
                    </td>
                  )}
                  {visible.has('net_return') && (
                    <td className={`${TD_BASE} text-right tabular-nums ${hot ? 'text-emerald-400' : 'text-zinc-300'}`}>
                      {d.netReturn.toFixed(2)}%
                    </td>
                  )}
                  {visible.has('apr') && (
                    <td className={`${TD_BASE} text-right tabular-nums font-medium ${hot ? 'text-emerald-400' : 'text-zinc-300'}`}>
                      {d.apr.toFixed(1)}%
                    </td>
                  )}
                  {visible.has('status') && (
                    <td className={`${TD_BASE}`}>
                      <StatusBadge value={o.status} />
                    </td>
                  )}
                  {visible.has('age') && (
                    <td className={`${TD_BASE} text-right tabular-nums text-zinc-500`}>
                      {fmtAge(o.detected_at)}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
