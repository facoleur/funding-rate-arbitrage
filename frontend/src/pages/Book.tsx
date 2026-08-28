import { Fragment, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchTickers, type BookRow, type ExchangeQuote } from '../api/tickers'
import { useBookFilters } from '../hooks/useBookFilters'
import { fmtAge, fmtExpiry } from '../lib/format'
import { exchangeAbbr, exchangeUrl } from '../lib/exchanges'
import { compareValues, nullLast, type SortDir } from '../lib/sort'
import { FIELD_CLASS, Select } from '../components/ui/Field'
import SortHeader from '../components/ui/SortHeader'
import { DataTable, HeadRow, THead, Td, Th } from '../components/ui/table'
import QueryState from '../components/ui/QueryState'

// ─── Sorting ─────────────────────────────────────────────────────────────────

const SORTABLE = [
  'expiry',
  'strike',
  'priceSpread',
  'buyPremium',
  'margin',
  'capital',
  'netReturn',
  'profit',
  'apr',
  'age',
] as const
type SortCol = (typeof SORTABLE)[number]

/** Colonnes où le tri le plus utile part du plus grand. */
const DESC_FIRST: SortCol[] = [
  'priceSpread',
  'netReturn',
  'profit',
  'buyPremium',
  'margin',
  'capital',
]

function isSortCol(s: string): s is SortCol {
  return (SORTABLE as readonly string[]).includes(s)
}

function sortValue(row: BookRow, col: SortCol): number {
  switch (col) {
    case 'expiry':
      return new Date(row.expiry).getTime()
    case 'strike':
      return row.strike
    case 'priceSpread':
      return nullLast(row.price_spread_pct)
    case 'buyPremium':
      return nullLast(row.buy_premium_usd)
    case 'margin':
      return nullLast(row.estimated_short_margin_usd)
    case 'capital':
      return nullLast(row.capital_required_usd)
    case 'netReturn':
      return nullLast(row.net_return_pct)
    case 'apr':
      return nullLast(row.apr_pct)
    case 'profit':
      return nullLast(row.net_profit_usd)
    case 'age':
      return new Date(row.updated_at).getTime()
  }
}

function sortRows(rows: BookRow[], col: SortCol | null, dir: SortDir): BookRow[] {
  if (!col) {
    return rows.slice().sort((a, b) => {
      if (a.underlying !== b.underlying) return a.underlying.localeCompare(b.underlying)
      if (a.expiry !== b.expiry) return a.expiry.localeCompare(b.expiry)
      if (a.strike !== b.strike) return a.strike - b.strike
      return a.option_type.localeCompare(b.option_type)
    })
  }
  return rows.slice().sort((a, b) => compareValues(sortValue(a, col), sortValue(b, col), dir))
}

// ─── Cells ───────────────────────────────────────────────────────────────────

function ExLink({ href, ex }: { href: string; ex: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded bg-zinc-800 px-1 py-px text-[9px] font-semibold leading-none text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-zinc-200"
    >
      {exchangeAbbr(ex)}
    </a>
  )
}

function QuoteCell({
  q,
  side,
  highlight,
}: {
  q: ExchangeQuote | undefined
  side: 'bid' | 'ask'
  highlight: boolean
}) {
  if (!q) return <span className="text-zinc-700">—</span>
  const price = side === 'bid' ? q.bid_price : q.ask_price
  const size = side === 'bid' ? q.bid_size : q.ask_size
  const stale = q.is_stale
  const color = stale
    ? 'text-zinc-600'
    : highlight
      ? side === 'bid'
        ? 'text-emerald-300 font-semibold'
        : 'text-sky-300 font-semibold'
      : side === 'bid'
        ? 'text-emerald-400'
        : 'text-red-400'
  return (
    <span className={color} title={stale ? 'Données > 60s' : undefined}>
      {stale && price != null && <span className="mr-0.5 text-amber-600">⚠</span>}
      {price != null ? price.toFixed(2) : '—'}
      {size != null && <span className="ml-1 text-zinc-500">{size.toFixed(3)}</span>}
    </span>
  )
}

/** Cellule numérique nullable : même mise en forme partout, `—` quand absente. */
function NumCell({
  value,
  format,
  active,
  activeClass,
}: {
  value: number | null
  format: (v: number) => string
  active: boolean
  activeClass: string
}) {
  return (
    <Td align="right" className={active ? activeClass : 'text-zinc-600'}>
      {value != null ? format(value) : '—'}
    </Td>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Book() {
  const f = useBookFilters()
  const [showLinks, setShowLinks] = useState(true)
  const sortCol = isSortCol(f.sortCol) ? f.sortCol : null

  const {
    data = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['tickers', f.underlying],
    queryFn: () => fetchTickers({ underlying: f.underlying || undefined }),
    refetchInterval: 5000,
  })

  const allExchanges = useMemo(() => {
    const set = new Set<string>()
    for (const r of data) for (const ex of Object.keys(r.exchanges)) set.add(ex)
    return [...set].sort()
  }, [data])

  const filtered = useMemo(
    () =>
      data
        .filter((r) => !f.optionType || r.option_type === f.optionType)
        .filter((r) => !f.onlyArb || (r.net_return_pct !== null && r.net_return_pct > 0))
        .filter((r) => !f.exchange || f.exchange in r.exchanges)
        .filter((r) => !f.maxExpiry || r.expiry.slice(0, 10) <= f.maxExpiry),
    [data, f.optionType, f.onlyArb, f.exchange, f.maxExpiry],
  )

  const rows = useMemo(() => sortRows(filtered, sortCol, f.sortDir), [filtered, sortCol, f.sortDir])

  function handleSort(col: SortCol) {
    const desc = sortCol === col ? f.sortDir === 'asc' : DESC_FIRST.includes(col)
    f.setSort(col, desc ? 'desc' : 'asc')
  }

  /** Colonnes chiffrées : alignées à droite, comme leur contenu. */
  const NUMERIC: SortCol[] = [
    'strike',
    'priceSpread',
    'buyPremium',
    'margin',
    'capital',
    'netReturn',
    'profit',
    'apr',
  ]

  function th(col: SortCol, label: string) {
    return (
      <SortHeader
        col={col}
        label={label}
        align={NUMERIC.includes(col) ? 'right' : 'left'}
        active={sortCol === col}
        dir={f.sortDir}
        onSort={handleSort}
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-base font-semibold text-zinc-100">Book</h1>
        <span className="text-xs text-zinc-500">
          {rows.length}
          {data.length !== rows.length ? ` / ${data.length}` : ''} instruments
        </span>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select value={f.underlying} onChange={f.setUnderlying}>
          <option value="">BTC + ETH</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>

        <Select value={f.optionType} onChange={f.setOptionType}>
          <option value="">Calls + Puts</option>
          <option value="C">Calls</option>
          <option value="P">Puts</option>
        </Select>

        <Select value={f.exchange} onChange={f.setExchange}>
          <option value="">Tous les exchanges</option>
          {allExchanges.map((ex) => (
            <option key={ex} value={ex}>
              {ex}
            </option>
          ))}
        </Select>

        <div className="flex items-center gap-1.5">
          <label className="text-xs text-zinc-500">Expiry ≤</label>
          <input
            type="date"
            value={f.maxExpiry}
            onChange={(e) => f.setMaxExpiry(e.target.value)}
            className={`${FIELD_CLASS} w-36`}
          />
        </div>

        <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={f.onlyArb}
            onChange={(e) => f.setOnlyArb(e.target.checked)}
            className="accent-emerald-500"
          />
          Arb seulement
        </label>

        <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={showLinks}
            onChange={(e) => setShowLinks(e.target.checked)}
            className="accent-zinc-500"
          />
          Liens exchanges
        </label>

        {f.hasFilters && (
          <button onClick={f.resetFilters} className="text-xs text-zinc-500 hover:text-zinc-200">
            Reset filtres
          </button>
        )}
      </div>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={rows.length === 0}
        emptyLabel="Aucune donnée."
      />

      {rows.length > 0 && (
        <div className="-mb-6 -mr-6 min-h-0 flex-1 overflow-auto">
          <DataTable className="whitespace-nowrap">
            <THead sticky>
              {/* Rangée 1 : libellés. Le trait est porté par la rangée 2. */}
              <HeadRow divider={false}>
                <Th className="sticky left-0 z-20 bg-zinc-950">Instrument</Th>
                {th('expiry', 'Expiry')}
                {th('strike', 'Strike')}
                <Th>Type</Th>
                {allExchanges.map((ex) => (
                  <Th key={ex} align="center" colSpan={2}>
                    {ex}
                  </Th>
                ))}
                {th('priceSpread', 'Price spread %')}
                {th('buyPremium', 'Buy premium')}
                {th('margin', 'Est. margin')}
                {th('capital', 'Capital')}
                {th('netReturn', 'Net return %')}
                {th('profit', 'Net profit')}
                {th('apr', 'APR %')}
                <Th>Arb</Th>
                {th('age', 'Age')}
              </HeadRow>
              {/* Rangée 2 : sous-libellés bid/ask sous chaque exchange. */}
              <HeadRow className="text-zinc-600">
                <Th className="sticky left-0 z-20 bg-zinc-950" />
                <Th colSpan={3} />
                {allExchanges.map((ex) => (
                  <Th key={ex} colSpan={2} align="center" className="pb-1 text-[10px] font-normal">
                    <span className="pr-5">bid</span>
                    <span>ask</span>
                  </Th>
                ))}
                <Th colSpan={9} />
              </HeadRow>
            </THead>
            <tbody>
              {rows.map((row) => {
                const hasArb = row.net_return_pct !== null && row.net_return_pct > 0
                const hasGross = row.price_spread_pct !== null && row.price_spread_pct > 0
                // `eligible` est le verdict du backend — même prédicat que le screener.

                return (
                  <tr
                    key={row.instrument}
                    className={`${hasArb ? 'bg-emerald-950/20' : ''} ${
                      !row.eligible ? 'opacity-50' : ''
                    }`}
                  >
                    <Td className="sticky left-0 z-10 bg-zinc-950">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-zinc-200">{row.instrument}</span>
                        {showLinks &&
                          Object.keys(row.exchanges).map((ex) => {
                            const href = exchangeUrl(ex, row.instrument, row.underlying)
                            return href ? <ExLink key={ex} href={href} ex={ex} /> : null
                          })}
                      </div>
                    </Td>
                    <Td className="text-zinc-400">{fmtExpiry(row.expiry)}</Td>
                    <Td align="right" className="tabular-nums text-zinc-300">
                      {row.strike.toLocaleString()}
                    </Td>
                    <Td>
                      <span
                        className={`font-medium ${
                          row.option_type === 'C' ? 'text-blue-400' : 'text-orange-400'
                        }`}
                      >
                        {row.option_type === 'C' ? 'Call' : 'Put'}
                      </span>
                    </Td>
                    {allExchanges.map((ex) => {
                      const q = row.exchanges[ex]
                      return (
                        <Fragment key={ex}>
                          <Td
                            align="right"
                            pad="tight"
                            className={
                              hasArb && ex === row.sell_exchange ? 'bg-emerald-950/40' : ''
                            }
                          >
                            <QuoteCell
                              q={q}
                              side="bid"
                              highlight={hasArb && ex === row.sell_exchange}
                            />
                          </Td>
                          <Td
                            align="right"
                            className={hasArb && ex === row.buy_exchange ? 'bg-sky-950/40' : ''}
                          >
                            <QuoteCell
                              q={q}
                              side="ask"
                              highlight={hasArb && ex === row.buy_exchange}
                            />
                          </Td>
                        </Fragment>
                      )
                    })}
                    <NumCell
                      value={row.price_spread_pct}
                      format={(v) => `${v.toFixed(2)}%`}
                      active={hasGross}
                      activeClass="text-zinc-300"
                    />
                    <NumCell
                      value={row.buy_premium_usd}
                      format={(v) => `$${v.toFixed(2)}`}
                      active={hasArb}
                      activeClass="text-sky-300"
                    />
                    <NumCell
                      value={row.estimated_short_margin_usd}
                      format={(v) => `$${v.toFixed(2)}`}
                      active={hasArb}
                      activeClass="text-zinc-300"
                    />
                    <NumCell
                      value={row.capital_required_usd}
                      format={(v) => `$${v.toFixed(2)}`}
                      active={hasArb}
                      activeClass="text-zinc-300"
                    />
                    <NumCell
                      value={row.net_return_pct}
                      format={(v) => `${v.toFixed(2)}%`}
                      active={hasArb}
                      activeClass="font-medium text-emerald-400"
                    />
                    <NumCell
                      value={row.net_profit_usd}
                      format={(v) => `$${v.toFixed(2)}`}
                      active={hasArb}
                      activeClass="font-medium text-emerald-300"
                    />
                    <NumCell
                      value={row.apr_pct}
                      format={(v) => `${v.toFixed(1)}%`}
                      active={hasArb}
                      activeClass="font-medium text-emerald-300"
                    />
                    <Td>
                      {hasArb ? (
                        <span className="text-emerald-400">
                          {row.buy_exchange} → {row.sell_exchange}
                        </span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </Td>
                    <Td align="right" className="text-zinc-500">
                      {fmtAge(row.updated_at)}
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </DataTable>
        </div>
      )}
    </div>
  )
}
