import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTickers, type BookRow } from '../api/tickers'

type SortCol = 'expiry' | 'strike' | 'gross' | 'net' | 'profit' | 'age'
type SortDir = 'asc' | 'desc'

function fmtExpiry(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  })
}

function fmtAge(iso: string) {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

function fmtPrice(v: number | null) {
  if (v == null) return <span className="text-zinc-700">—</span>
  return <span>{v.toFixed(2)}</span>
}

function fmtSize(v: number | null) {
  if (v == null) return <span className="text-zinc-700" />
  return <span className="text-zinc-500 ml-1">{v.toFixed(3)}</span>
}

const _MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']

function toDeribitInstrument(normalized: string): string | null {
  const m = normalized.match(/^([A-Z]+)-(\d{4})(\d{2})(\d{2})-(\d+(?:\.\d+)?)-([CP])$/)
  if (!m) return null
  const [, underlying, year, month, day, strike, type] = m
  const mon = _MONTHS[parseInt(month) - 1]
  const d = parseInt(day).toString()
  return `${underlying}-${d}${mon}${year.slice(2)}-${strike}-${type}`
}

function deribitUrl(instrument: string, underlying: string): string | null {
  const dName = toDeribitInstrument(instrument)
  if (!dName) return null
  const parts = dName.split('-')
  const expiryGroup = `${parts[0]}-${parts[1]}`
  return `https://www.deribit.com/options/${underlying}/${expiryGroup}/${dName}`
}

function deriveUrl(instrument: string): string {
  return `https://app.derive.xyz/trade/${instrument}`
}

const EXCHANGE_ABBR: Record<string, string> = {
  deribit: 'Db',
  derive: 'Dr',
}

function ExchangeLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={`Voir sur ${label}`}
      className="text-[9px] font-semibold px-1 py-px rounded bg-zinc-800 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 transition-colors leading-none"
    >
      {EXCHANGE_ABBR[label.toLowerCase()] ?? label.slice(0, 2)}
    </a>
  )
}

function SortIcon({ col: _col, active, dir }: { col: string; active: boolean; dir: SortDir }) {
  if (!active) return <span className="ml-1 text-zinc-700">↕</span>
  return <span className="ml-1 text-zinc-300">{dir === 'asc' ? '↑' : '↓'}</span>
}

function sortRows(rows: BookRow[], col: SortCol | null, dir: SortDir): BookRow[] {
  if (!col) {
    return [...rows].sort((a, b) => {
      if (a.underlying !== b.underlying) return a.underlying.localeCompare(b.underlying)
      if (a.expiry !== b.expiry) return a.expiry.localeCompare(b.expiry)
      if (a.strike !== b.strike) return a.strike - b.strike
      return a.option_type.localeCompare(b.option_type)
    })
  }
  return [...rows].sort((a, b) => {
    let av: number, bv: number
    if (col === 'expiry') {
      av = new Date(a.expiry).getTime()
      bv = new Date(b.expiry).getTime()
    } else if (col === 'strike') {
      av = a.strike; bv = b.strike
    } else if (col === 'gross') {
      av = a.gross_spread_pct ?? -Infinity
      bv = b.gross_spread_pct ?? -Infinity
    } else if (col === 'net') {
      av = a.net_spread_pct ?? -Infinity
      bv = b.net_spread_pct ?? -Infinity
    } else if (col === 'profit') {
      av = a.max_profit_usd ?? -Infinity
      bv = b.max_profit_usd ?? -Infinity
    } else {
      av = new Date(a.updated_at).getTime()
      bv = new Date(b.updated_at).getTime()
    }
    return dir === 'asc' ? av - bv : bv - av
  })
}

export default function Book() {
  const [underlying, setUnderlying] = useState('')
  const [optionType, setOptionType] = useState('')
  const [onlyArb, setOnlyArb] = useState(false)
  const [sortCol, setSortCol] = useState<SortCol | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['tickers', underlying],
    queryFn: () => fetchTickers({ underlying: underlying || undefined }),
    refetchInterval: 5000,
  })

  const filtered = (data ?? [])
    .filter((r) => !optionType || r.option_type === optionType)
    .filter((r) => !onlyArb || (r.net_spread_pct !== null && r.net_spread_pct > 0))

  const rows = sortRows(filtered, sortCol, sortDir)
  const allExchanges = [...new Set((data ?? []).flatMap((r) => Object.keys(r.exchanges)))].sort()

  function handleSort(col: SortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortCol(col)
      setSortDir(col === 'net' || col === 'gross' || col === 'profit' ? 'desc' : 'asc')
    }
  }

  function thSort(col: SortCol, label: string, className = '') {
    return (
      <th
        className={`pb-2 pr-3 cursor-pointer select-none hover:text-zinc-300 ${className}`}
        onClick={() => handleSort(col)}
      >
        {label}
        <SortIcon col={col} active={sortCol === col} dir={sortDir} />
      </th>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-base font-semibold text-zinc-100">Book</h1>
        <span className="text-xs text-zinc-500">{rows.length} instruments</span>
      </div>

      <div className="mb-4 flex gap-3 items-center">
        <select
          value={underlying}
          onChange={(e) => setUnderlying(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
        >
          <option value="">BTC + ETH</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </select>
        <select
          value={optionType}
          onChange={(e) => setOptionType(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
        >
          <option value="">Calls + Puts</option>
          <option value="C">Calls</option>
          <option value="P">Puts</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyArb}
            onChange={(e) => setOnlyArb(e.target.checked)}
            className="accent-emerald-500"
          />
          Arb seulement
        </label>
        {sortCol && (
          <button
            onClick={() => setSortCol(null)}
            className="text-xs text-zinc-600 hover:text-zinc-400"
          >
            Reset tri
          </button>
        )}
      </div>

      {isLoading && <p className="text-xs text-zinc-500">Chargement...</p>}
      {isError && <p className="text-xs text-red-400">Erreur de chargement</p>}

      {!isLoading && rows.length === 0 && !isError && (
        <p className="text-xs text-zinc-600">
          Aucune donnée. Attends ~1s après le démarrage du container workers.
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-auto max-h-[calc(100vh-11rem)]">
          <table className="w-full text-xs border-separate border-spacing-0">
            <thead className="sticky top-0 z-10 bg-zinc-950">
              <tr className="border-b border-zinc-800 text-left text-zinc-500">
                <th className="pb-2 pr-3">Instrument</th>
                {thSort('expiry', 'Expiry')}
                {thSort('strike', 'Strike', 'text-right')}
                <th className="pb-2 pr-3">Type</th>
                {allExchanges.map((ex) => (
                  <th key={ex} className="pb-2 pr-3 text-right" colSpan={2}>
                    {ex}
                  </th>
                ))}
                {thSort('gross', 'Gross%', 'text-right')}
                {thSort('net', 'Net%', 'text-right')}
                {thSort('profit', 'Profit$', 'text-right')}
                <th className="pb-2 pr-3">Arb</th>
                {thSort('age', 'Age')}
              </tr>
              <tr className="border-b border-zinc-800/50 text-zinc-600">
                <th colSpan={4} />
                {allExchanges.map((ex) => (
                  <>
                    <th key={ex + '-bid'} className="pb-1 pr-2 text-right font-normal">bid</th>
                    <th key={ex + '-ask'} className="pb-1 pr-3 text-right font-normal">ask</th>
                  </>
                ))}
                <th colSpan={5} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const hasArb = row.net_spread_pct !== null && row.net_spread_pct > 0
                const hasGross = row.gross_spread_pct !== null && row.gross_spread_pct > 0
                const dUrl = deribitUrl(row.instrument, row.underlying)

                return (
                  <tr
                    key={row.instrument}
                    className={`border-b border-zinc-800/40 ${hasArb ? 'bg-emerald-950/20' : ''}`}
                  >
                    <td className="py-1 pr-3 font-medium text-zinc-200">
                      <div className="flex items-center gap-1.5">
                        <span>{row.instrument}</span>
                        {row.exchanges['deribit'] && dUrl && (
                          <ExchangeLink href={dUrl} label="Deribit" />
                        )}
                        {row.exchanges['derive'] && (
                          <ExchangeLink href={deriveUrl(row.instrument)} label="Derive" />
                        )}
                      </div>
                    </td>
                    <td className="py-1 pr-3 text-zinc-400">{fmtExpiry(row.expiry)}</td>
                    <td className="py-1 pr-3 text-right text-zinc-300">{row.strike.toLocaleString()}</td>
                    <td className="py-1 pr-3">
                      <span className={`font-medium ${row.option_type === 'C' ? 'text-blue-400' : 'text-orange-400'}`}>
                        {row.option_type === 'C' ? 'Call' : 'Put'}
                      </span>
                    </td>
                    {allExchanges.map((ex) => {
                      const q = row.exchanges[ex]
                      const isBuyLeg = ex === row.buy_exchange
                      const isSellLeg = ex === row.sell_exchange
                      const stale = q?.is_stale ?? false
                      return (
                        <>
                          <td
                            key={ex + '-bid'}
                            className={`py-1 pr-2 text-right ${
                              stale
                                ? 'text-zinc-600'
                                : isSellLeg
                                  ? 'text-emerald-300 font-semibold bg-emerald-950/40'
                                  : 'text-emerald-400/60'
                            }`}
                            title={stale ? 'Données > 60s' : undefined}
                          >
                            {stale && q?.bid_price != null && <span className="mr-0.5 text-amber-600">⚠</span>}
                            {fmtPrice(q?.bid_price ?? null)}
                            {fmtSize(q?.bid_size ?? null)}
                          </td>
                          <td
                            key={ex + '-ask'}
                            className={`py-1 pr-3 text-right ${
                              stale
                                ? 'text-zinc-600'
                                : isBuyLeg
                                  ? 'text-sky-300 font-semibold bg-sky-950/40'
                                  : 'text-red-400/60'
                            }`}
                            title={stale ? 'Données > 60s' : undefined}
                          >
                            {fmtPrice(q?.ask_price ?? null)}
                            {fmtSize(q?.ask_size ?? null)}
                          </td>
                        </>
                      )
                    })}
                    <td className={`py-1 pr-3 text-right ${hasGross ? 'text-zinc-300' : 'text-zinc-600'}`}>
                      {row.gross_spread_pct !== null ? `${row.gross_spread_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right font-medium ${hasArb ? 'text-emerald-400' : 'text-zinc-700'}`}>
                      {row.net_spread_pct !== null ? `${row.net_spread_pct.toFixed(2)}%` : '—'}
                    </td>
                    <td className={`py-1 pr-3 text-right font-medium ${hasArb ? 'text-emerald-300' : 'text-zinc-700'}`}>
                      {row.max_profit_usd !== null ? `$${row.max_profit_usd.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-1 pr-3 text-xs text-zinc-500">
                      {hasArb ? (
                        <span className="text-emerald-400">
                          {row.buy_exchange} → {row.sell_exchange}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-1 text-zinc-600">{fmtAge(row.updated_at)}</td>
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
