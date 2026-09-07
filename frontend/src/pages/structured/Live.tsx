import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  fetchStructuredOpportunities,
  type StructuredOpportunity,
  type StructuredSortCol,
} from '../../api/structured'
import { NumberField, Select } from '../../components/ui/Field'
import PageToolbar from '../../components/ui/PageToolbar'
import SortHeader from '../../components/ui/SortHeader'
import { DataTable, HeadRow, THead, Td, Th, type Align } from '../../components/ui/table'
import QueryState from '../../components/ui/QueryState'
import { exchangeColor } from '../../lib/exchanges'
import { fmtAge, fmtExpiry, fmtUsd } from '../../lib/format'
import type { SortDir } from '../../lib/sort'

type VenueMode = '' | 'intra' | 'cross'

const SORT_COLS: { key: StructuredSortCol; label: string; align?: Align }[] = [
  { key: 'max_size', label: 'Taille', align: 'right' },
  { key: 'min_profit', label: 'Edge/u', align: 'right' },
  { key: 'max_total_profit_usd', label: 'Profit $', align: 'right' },
  { key: 'capital_required_usd', label: 'Capital', align: 'right' },
  { key: 'samples_count', label: 'Pts', align: 'right' },
  { key: 'detected_at', label: 'Âge', align: 'right' },
]

function venueMix(o: StructuredOpportunity): string[] {
  return [...new Set(o.legs.map((l) => l.exchange))]
}

export default function StructuredLive() {
  const navigate = useNavigate()
  const [minProfit, setMinProfit] = useState('')
  const [underlying, setUnderlying] = useState('')
  const [venueMode, setVenueMode] = useState<VenueMode>('')
  const [excludeSettlementRisk, setExcludeSettlementRisk] = useState(false)
  const [sortBy, setSortBy] = useState<StructuredSortCol>('max_total_profit_usd')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(col: StructuredSortCol) {
    if (col === sortBy) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['structured', 'live', sortBy, sortDir],
    queryFn: () =>
      fetchStructuredOpportunities({
        live_status: 'LIVE',
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: 200,
      }),
    refetchInterval: 5000,
  })

  const rows = useMemo(
    () =>
      (data ?? []).filter((o) => {
        if (minProfit && o.max_total_profit_usd < parseFloat(minProfit)) return false
        if (underlying && o.underlying !== underlying) return false
        if (venueMode === 'intra' && !o.is_fixed_payoff) return false
        if (venueMode === 'cross' && o.is_fixed_payoff) return false
        if (excludeSettlementRisk && o.settlement_risk) return false
        return true
      }),
    [data, minProfit, underlying, venueMode, excludeSettlementRisk],
  )

  return (
    <div className="flex h-full flex-col">
      <PageToolbar count={rows.length} label="ouvertes">
        <NumberField
          value={minProfit}
          placeholder="Profit min $"
          onChange={setMinProfit}
          className="w-28"
        />
        <Select value={underlying} onChange={setUnderlying}>
          <option value="">Tous</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>
        <Select value={venueMode} onChange={(v) => setVenueMode(v as VenueMode)}>
          <option value="">Intra + cross</option>
          <option value="intra">Intra-exchange</option>
          <option value="cross">Cross-exchange</option>
        </Select>
        <label className="flex items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={excludeSettlementRisk}
            onChange={(e) => setExcludeSettlementRisk(e.target.checked)}
          />
          Exclure settlement risk
        </label>
      </PageToolbar>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={rows.length === 0}
        emptyLabel="Aucune opportunité structurée ouverte"
      />

      {rows.length > 0 && (
        <div className="min-h-0 flex-1 overflow-auto">
          <DataTable>
            <THead sticky>
              <HeadRow>
                <Th>Underlying</Th>
                <Th>Strikes</Th>
                <Th>Venues</Th>
                <Th>Expiry</Th>
                <Th align="right">Entrée</Th>
                {SORT_COLS.map((c) => (
                  <SortHeader
                    key={c.key}
                    col={c.key}
                    label={c.label}
                    align={c.align}
                    active={sortBy === c.key}
                    dir={sortDir}
                    onSort={handleSort}
                  />
                ))}
                <Th>Flags</Th>
              </HeadRow>
            </THead>
            <tbody>
              {rows.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => navigate(`/structured/${o.id}`)}
                  className="cursor-pointer hover:bg-zinc-800/40"
                >
                  <Td className="text-zinc-300">{o.underlying}</Td>
                  <Td className="font-mono text-[11px] text-zinc-400">
                    {o.strikes.map((k) => k.toLocaleString()).join(' / ')}
                  </Td>
                  <Td className="whitespace-nowrap text-[11px]">
                    {venueMix(o).map((ex, i) => (
                      <span key={ex}>
                        {i > 0 && <span className="text-zinc-600"> · </span>}
                        <span className={exchangeColor(ex)}>{ex}</span>
                      </span>
                    ))}
                  </Td>
                  <Td className="whitespace-nowrap text-zinc-500">{fmtExpiry(o.expiry)}</Td>
                  <Td align="right" className="tabular-nums text-zinc-400">
                    {o.entry_cost.toFixed(4)}
                  </Td>
                  <Td align="right" className="tabular-nums text-zinc-300">
                    {o.max_size.toFixed(2)}
                  </Td>
                  <Td
                    align="right"
                    className={`tabular-nums ${o.min_profit > 0 ? 'text-emerald-400' : 'text-red-400'}`}
                  >
                    {o.min_profit.toFixed(4)}
                  </Td>
                  <Td align="right" className="tabular-nums font-medium text-emerald-400">
                    {fmtUsd(o.max_total_profit_usd)}
                  </Td>
                  <Td align="right" className="tabular-nums text-zinc-400">
                    {fmtUsd(o.capital_required_usd)}
                  </Td>
                  <Td align="right" className="tabular-nums text-zinc-500">
                    {o.samples_count}
                  </Td>
                  <Td align="right" className="whitespace-nowrap text-zinc-500">
                    {fmtAge(o.detected_at)}
                  </Td>
                  <Td className="whitespace-nowrap text-[10px]">
                    {o.is_fixed_payoff ? (
                      <span className="text-emerald-500">fixé</span>
                    ) : (
                      <span className="text-zinc-500">cross</span>
                    )}
                    {o.settlement_risk && <span className="ml-1 text-amber-500">⚠ settl.</span>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </div>
      )}
    </div>
  )
}
