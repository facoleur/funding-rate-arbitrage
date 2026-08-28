import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import {
  fetchOpportunities,
  type Opportunity,
  type OpportunityEconomics,
  type OpportunityStatus,
} from '../api/opportunities'
import { fetchExecutorState } from '../api/executor'
import StatusBadge from '../components/StatusBadge'
import { NumberField, Select } from '../components/ui/Field'
import SortHeader from '../components/ui/SortHeader'
import ColumnPicker from '../components/ui/ColumnPicker'
import { DataTable, HeadRow, THead, Td, Th, type Align } from '../components/ui/table'
import QueryState from '../components/ui/QueryState'
import { useColumnVisibility } from '../hooks/useColumnVisibility'
import { fmtAge, fmtDte, fmtExpiry, fmtUsdOrDash } from '../lib/format'
import { compareValues, type SortDir } from '../lib/sort'

// ─── Colonnes ────────────────────────────────────────────────────────────────

type ColId =
  | 'type'
  | 'strike'
  | 'expiry'
  | 'dte'
  | 'route'
  | 'size'
  | 'buy_ask'
  | 'sell_bid'
  | 'buy_premium'
  | 'sell_premium'
  | 'margin'
  | 'capital'
  | 'fees'
  | 'net_profit'
  | 'net_return'
  | 'apr'
  | 'status'
  | 'age'

interface Column {
  id: ColId
  label: string
  tip?: string
  align?: Align
  /** Une colonne non triable rend un `<th>` inerte. */
  sortable?: boolean
  defaultVisible: boolean
  /** Clé de tri. */
  value: (o: Opportunity, e: OpportunityEconomics) => number | string
  /** Contenu de la cellule ; par défaut `value`. */
  cell?: (o: Opportunity, e: OpportunityEconomics) => ReactNode
  /** Classes de la cellule, éventuellement dépendantes du surlignage. */
  cellClass?: (hot: boolean) => string
}

const MUTED = () => 'text-zinc-400'
const NUM = () => 'text-zinc-300'
const HOT_NUM = (hot: boolean) => (hot ? 'text-emerald-400' : 'text-zinc-300')

const COLUMNS: readonly Column[] = [
  {
    id: 'type',
    label: 'Type',
    defaultVisible: false,
    value: (o) => o.option_type,
    cellClass: MUTED,
  },
  {
    id: 'strike',
    label: 'Strike',
    align: 'right',
    defaultVisible: false,
    value: (o) => o.strike,
    cell: (o) => o.strike.toLocaleString(),
    cellClass: MUTED,
  },
  {
    id: 'expiry',
    label: 'Expiry',
    defaultVisible: true,
    value: (o) => new Date(o.expiry).getTime(),
    cell: (o) => fmtExpiry(o.expiry),
    cellClass: MUTED,
  },
  {
    id: 'dte',
    label: 'DTE',
    align: 'right',
    defaultVisible: true,
    value: (o) => o.days_to_expiry,
    cell: (o) => fmtDte(o.days_to_expiry),
    cellClass: MUTED,
  },
  {
    id: 'route',
    label: 'Route',
    sortable: false,
    defaultVisible: true,
    value: (o) => `${o.buy_from}→${o.sell_to}`,
    cell: (o) => `${o.buy_from} → ${o.sell_to}`,
    cellClass: MUTED,
  },
  {
    id: 'size',
    label: 'Size',
    align: 'right',
    defaultVisible: false,
    value: (_o, e) => e.tradeable_size,
    cell: (_o, e) => e.tradeable_size.toFixed(4),
    cellClass: NUM,
  },
  {
    id: 'buy_ask',
    label: 'Buy ask',
    align: 'right',
    defaultVisible: false,
    value: (_o, e) => e.buy_price,
    cell: (_o, e) => e.buy_price.toFixed(4),
    cellClass: NUM,
  },
  {
    id: 'sell_bid',
    label: 'Sell bid',
    align: 'right',
    defaultVisible: false,
    value: (_o, e) => e.sell_price,
    cell: (_o, e) => e.sell_price.toFixed(4),
    cellClass: NUM,
  },
  {
    id: 'buy_premium',
    label: 'Buy premium',
    align: 'right',
    defaultVisible: true,
    value: (_o, e) => e.buy_premium_usd,
    cell: (_o, e) => fmtUsdOrDash(e.buy_premium_usd),
    cellClass: NUM,
  },
  {
    id: 'sell_premium',
    label: 'Sell premium',
    align: 'right',
    defaultVisible: false,
    value: (_o, e) => e.sell_premium_usd,
    cell: (_o, e) => fmtUsdOrDash(e.sell_premium_usd),
    cellClass: NUM,
  },
  {
    id: 'margin',
    label: 'Est. margin',
    align: 'right',
    defaultVisible: true,
    value: (_o, e) => e.estimated_short_margin_usd,
    cell: (_o, e) => fmtUsdOrDash(e.estimated_short_margin_usd),
    cellClass: NUM,
  },
  {
    id: 'capital',
    label: 'Capital',
    align: 'right',
    defaultVisible: true,
    tip: 'Prime achat + marge short estimée, sans offset de prime vente',
    value: (_o, e) => e.capital_required_usd,
    cell: (_o, e) => fmtUsdOrDash(e.capital_required_usd),
    cellClass: NUM,
  },
  {
    id: 'fees',
    label: 'Fees',
    align: 'right',
    defaultVisible: true,
    value: (_o, e) => e.fees_usd,
    cell: (_o, e) => fmtUsdOrDash(e.fees_usd),
    cellClass: () => 'text-zinc-500',
  },
  {
    id: 'net_profit',
    label: 'Net profit',
    align: 'right',
    defaultVisible: true,
    value: (_o, e) => e.net_profit_usd,
    cell: (_o, e) => fmtUsdOrDash(e.net_profit_usd),
    cellClass: HOT_NUM,
  },
  {
    id: 'net_return',
    label: 'Net return %',
    align: 'right',
    defaultVisible: true,
    tip: 'Profit net / capital requis',
    value: (_o, e) => e.net_return_pct,
    cell: (_o, e) => `${e.net_return_pct.toFixed(2)}%`,
    cellClass: HOT_NUM,
  },
  {
    id: 'apr',
    label: 'APR %',
    align: 'right',
    defaultVisible: true,
    tip: 'Annualisé sur capital total (prime achat + marge sell estimée)',
    value: (_o, e) => e.apr_pct,
    cell: (_o, e) => `${e.apr_pct.toFixed(1)}%`,
    cellClass: (hot) => `font-medium ${hot ? 'text-emerald-400' : 'text-zinc-300'}`,
  },
  {
    id: 'status',
    label: 'Status',
    sortable: false,
    defaultVisible: true,
    value: (o) => o.status,
    cell: (o) => <StatusBadge value={o.status} />,
  },
  {
    id: 'age',
    label: 'Age',
    align: 'right',
    defaultVisible: true,
    value: (o) => new Date(o.detected_at).getTime(),
    cell: (o) => fmtAge(o.detected_at),
    cellClass: () => 'text-zinc-500',
  },
]

type SortKey = 'instrument' | ColId

const STATUSES: OpportunityStatus[] = ['PENDING', 'APPROVED', 'EXECUTED', 'REJECTED', 'EXPIRED']
const COLUMNS_STORAGE_KEY = 'opportunities-columns'

const STICKY_BG = 'bg-zinc-950'
const HOT_BG = 'bg-emerald-950/30'

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Opportunities() {
  const [minApr, setMinApr] = useState('')
  const [underlying, setUnderlying] = useState('')
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | ''>('')
  const [sortCol, setSortCol] = useState<SortKey>('apr')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const { visible, toggle } = useColumnVisibility(COLUMNS_STORAGE_KEY, COLUMNS)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['opportunities'],
    queryFn: () => fetchOpportunities({ limit: 200 }),
    refetchInterval: 5000,
  })

  // Le surlignage « hot » suit le seuil réellement configuré côté screener.
  const { data: execState } = useQuery({
    queryKey: ['executor'],
    queryFn: fetchExecutorState,
    refetchInterval: 30_000,
    retry: false,
  })
  const hotAprThreshold = execState?.config.min_apr_pct ?? 10

  const shown = COLUMNS.filter((c) => visible.has(c.id))

  const filtered = (data ?? []).filter((o) => {
    if (minApr && o.effective.apr_pct < parseFloat(minApr)) return false
    if (underlying && !o.symbol.startsWith(underlying)) return false
    if (statusFilter && o.status !== statusFilter) return false
    return true
  })

  const rows = [...filtered].sort((a, b) => {
    if (sortCol === 'instrument') return compareValues(a.instrument, b.instrument, sortDir)
    const column = COLUMNS.find((c) => c.id === sortCol)
    if (!column) return 0
    return compareValues(column.value(a, a.effective), column.value(b, b.effective), sortDir)
  })

  function toggleSort(col: SortKey) {
    if (sortCol === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 7rem)' }}>
      {/* toolbar */}
      <div className="mb-3 flex flex-shrink-0 flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-zinc-100">Opportunités</h1>
        <span className="text-xs text-zinc-500">{rows.length} lignes</span>

        <NumberField value={minApr} placeholder="APR min %" onChange={setMinApr} className="w-28" />
        <Select value={underlying} onChange={setUnderlying}>
          <option value="">Tous</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>
        <Select value={statusFilter} onChange={(v) => setStatusFilter(v as OpportunityStatus | '')}>
          <option value="">Tous statuts</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>

        <ColumnPicker columns={COLUMNS} visible={visible} onToggle={toggle} />
      </div>

      <QueryState isLoading={isLoading} isError={isError} />

      <div className="flex-1 overflow-auto">
        <DataTable className="whitespace-nowrap">
          <THead>
            <HeadRow>
              {/* instrument — épinglé à gauche et en haut */}
              <SortHeader
                col="instrument"
                label="Instrument"
                active={sortCol === 'instrument'}
                dir={sortDir}
                onSort={toggleSort}
                className={`sticky left-0 top-0 z-30 ${STICKY_BG} pl-0`}
              />
              {shown.map((c) =>
                c.sortable === false ? (
                  <Th key={c.id} align={c.align}>
                    {c.label}
                  </Th>
                ) : (
                  <SortHeader
                    key={c.id}
                    col={c.id}
                    label={c.label}
                    tip={c.tip}
                    align={c.align}
                    active={sortCol === c.id}
                    dir={sortDir}
                    onSort={toggleSort}
                  />
                ),
              )}
            </HeadRow>
          </THead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={shown.length + 1} className="pt-6 text-center text-zinc-600">
                  Aucune opportunité
                </td>
              </tr>
            )}
            {rows.map((o) => {
              const e = o.effective
              const hot = e.apr_pct >= hotAprThreshold

              return (
                <tr key={o.id}>
                  <Td
                    className={`sticky left-0 z-10 ${
                      hot ? HOT_BG : STICKY_BG
                    } pl-0 font-medium text-zinc-200`}
                  >
                    {o.instrument}
                  </Td>
                  {shown.map((c) => (
                    <Td
                      key={c.id}
                      align={c.align}
                      className={`${c.align === 'right' ? 'tabular-nums' : ''} ${
                        c.cellClass?.(hot) ?? ''
                      }`}
                    >
                      {c.cell ? c.cell(o, e) : c.value(o, e)}
                    </Td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </DataTable>
      </div>
    </div>
  )
}
