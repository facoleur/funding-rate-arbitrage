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
import { fmtDateTime, fmtUsd } from '../../lib/format'
import type { SortDir } from '../../lib/sort'

type Status = StructuredOpportunity['live_status']
type VenueMode = '' | 'intra' | 'cross'

const STATUS_COLORS: Record<Status, string> = {
  LIVE: 'text-amber-400',
  STALE: 'text-zinc-400',
  EXPIRED: 'text-zinc-500',
}

const SORT_COLS: { key: StructuredSortCol; label: string; align?: Align }[] = [
  { key: 'detected_at', label: 'First seen' },
  { key: 'last_seen_at', label: 'Last seen' },
  { key: 'peak_total_profit_usd', label: 'Peak $', align: 'right' },
  { key: 'max_total_profit_usd', label: 'Dernier $', align: 'right' },
  { key: 'samples_count', label: 'Pts', align: 'right' },
]

function fmtLifetime(sec: number): string {
  if (sec < 90) return `${Math.round(sec)}s`
  if (sec < 5400) return `${Math.round(sec / 60)}min`
  if (sec < 172800) return `${(sec / 3600).toFixed(1)}h`
  return `${(sec / 86400).toFixed(1)}j`
}

function venueMix(o: StructuredOpportunity): string[] {
  return [...new Set(o.legs.map((l) => l.exchange))]
}

export default function StructuredHistory() {
  const navigate = useNavigate()
  const [days, setDays] = useState(7)
  const [underlying, setUnderlying] = useState('')
  const [statusFilter, setStatusFilter] = useState<Status | ''>('')
  const [venueMode, setVenueMode] = useState<VenueMode>('')
  const [excludeSettlementRisk, setExcludeSettlementRisk] = useState(false)
  const [minPeak, setMinPeak] = useState('')
  const [sortBy, setSortBy] = useState<StructuredSortCol>('detected_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(col: StructuredSortCol) {
    if (col === sortBy) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['structured', 'history', days, sortBy, sortDir],
    queryFn: () =>
      fetchStructuredOpportunities({ days, sort_by: sortBy, sort_dir: sortDir, limit: 1000 }),
    refetchInterval: 15_000,
  })

  const rows = useMemo(() => {
    return (data ?? []).filter((o) => {
      if (underlying && o.underlying !== underlying) return false
      if (statusFilter && o.live_status !== statusFilter) return false
      if (venueMode === 'intra' && !o.is_fixed_payoff) return false
      if (venueMode === 'cross' && o.is_fixed_payoff) return false
      if (excludeSettlementRisk && o.settlement_risk) return false
      if (minPeak && o.peak_total_profit_usd < parseFloat(minPeak)) return false
      return true
    })
  }, [data, underlying, statusFilter, venueMode, excludeSettlementRisk, minPeak])

  return (
    <div className="flex h-full flex-col">
      <PageToolbar count={rows.length}>
        <Select value={days} onChange={(v) => setDays(Number(v))}>
          <option value={1}>1 jour</option>
          <option value={7}>7 jours</option>
          <option value={30}>30 jours</option>
        </Select>
        <Select value={underlying} onChange={setUnderlying}>
          <option value="">Tous</option>
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </Select>
        <Select value={statusFilter} onChange={(v) => setStatusFilter(v as Status | '')}>
          <option value="">Tous statuts</option>
          <option value="LIVE">LIVE</option>
          <option value="STALE">STALE</option>
          <option value="EXPIRED">EXPIRED</option>
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
        <NumberField
          value={minPeak}
          placeholder="Peak min $"
          onChange={setMinPeak}
          className="w-28"
        />
      </PageToolbar>

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={rows.length === 0}
        emptyLabel="Aucune opportunité sur cette période."
      />

      {rows.length > 0 && (
        <div className="min-h-0 flex-1 overflow-auto">
          <DataTable>
            <THead sticky>
              <HeadRow>
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
                <Th align="right">Lifetime</Th>
                <Th align="right">Decay</Th>
                <Th>Underlying</Th>
                <Th>Strikes</Th>
                <Th>Venues</Th>
                <Th>Statut</Th>
              </HeadRow>
            </THead>
            <tbody>
              {rows.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => navigate(`/structured/${o.id}`)}
                  className="cursor-pointer hover:bg-zinc-800/40"
                >
                  <Td className="whitespace-nowrap text-zinc-500">{fmtDateTime(o.detected_at)}</Td>
                  <Td className="whitespace-nowrap text-zinc-500">{fmtDateTime(o.last_seen_at)}</Td>
                  <Td align="right" className="font-medium text-emerald-400">
                    {fmtUsd(o.peak_total_profit_usd)}
                  </Td>
                  <Td align="right" className="text-zinc-300">
                    {fmtUsd(o.max_total_profit_usd)}
                  </Td>
                  <Td align="right" className="text-zinc-400">
                    {o.samples_count}
                  </Td>
                  <Td align="right" className="text-zinc-300">
                    {fmtLifetime(o.lifetime_sec)}
                  </Td>
                  <Td align="right" className={o.decay_pct > 50 ? 'text-red-400' : 'text-zinc-400'}>
                    {o.decay_pct.toFixed(0)}%
                  </Td>
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
                  <Td className={STATUS_COLORS[o.live_status]}>
                    {o.live_status}
                    {o.close_reason && (
                      <span className="ml-1 text-[10px] text-zinc-600">({o.close_reason})</span>
                    )}
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
