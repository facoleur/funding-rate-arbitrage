import { useQuery } from '@tanstack/react-query'
import { fetchExchanges, fetchPositions, type ExchangeState, type Position } from '../api/positions'
import StatusBadge from '../components/StatusBadge'
import QueryState from '../components/ui/QueryState'
import { DataTable, HeadRow, THead, Td, Th } from '../components/ui/table'
import { fmtExpiry, fmtTime, hoursUntil } from '../lib/format'

function ExchangeCard({ ex, positions }: { ex: ExchangeState; positions: Position[] }) {
  const ownPositions = positions.filter((p) => p.exchange === ex.exchange)

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100 capitalize">{ex.exchange}</h2>
        <div className="flex gap-2">
          <StatusBadge value={ex.ws_status} />
          <StatusBadge value={ex.rest_status} />
        </div>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3 text-xs">
        <div className="col-span-2">
          <p className="text-zinc-500 mb-1">Balances</p>
          {Object.keys(ex.balances).length === 0 ? (
            <p className="text-zinc-600 italic">—</p>
          ) : (
            <div className="flex flex-col gap-0.5">
              {Object.entries(ex.balances).map(([token, amount]) => (
                <div key={token} className="flex items-baseline gap-1.5">
                  <span className="text-zinc-400 uppercase tracking-wide text-[10px]">{token}</span>
                  <span className="text-base font-medium text-zinc-100 tabular-nums">
                    {amount < 1 ? amount.toFixed(6) : amount.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <div>
            <p className="text-zinc-500">Margin used</p>
            <p className="text-lg font-medium text-zinc-100">${ex.margin_used_usd.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-zinc-500">Positions</p>
            <p className="text-lg font-medium text-zinc-100">{ownPositions.length}</p>
          </div>
        </div>
      </div>

      {ownPositions.length > 0 && (
        <DataTable>
          <THead>
            <HeadRow>
              <Th>Instrument</Th>
              <Th align="right">Size</Th>
              <Th align="right">Avg price</Th>
              <Th>Expiry</Th>
            </HeadRow>
          </THead>
          <tbody>
            {ownPositions.map((p) => {
              const expiry = p.instrument.split('-')[1] ?? p.last_seen_at
              const urgent = hoursUntil(expiry) < 24
              return (
                <tr key={p.id}>
                  <Td className="font-medium text-zinc-200">{p.instrument}</Td>
                  <Td align="right" className="text-zinc-300">
                    {p.size}
                  </Td>
                  <Td align="right" className="text-zinc-300">
                    ${p.avg_price.toFixed(2)}
                  </Td>
                  <Td className={urgent ? 'font-medium text-red-400' : 'text-zinc-400'}>
                    {fmtExpiry(expiry)}
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </DataTable>
      )}

      <p className="mt-2 text-xs text-zinc-600">Mis à jour {fmtTime(ex.updated_at)}</p>
    </div>
  )
}

export default function Positions() {
  const { data: exchanges, isLoading: exLoading } = useQuery({
    queryKey: ['exchanges'],
    queryFn: fetchExchanges,
    refetchInterval: 10000,
  })

  const { data: positions } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 10000,
  })

  return (
    <div>
      <h1 className="mb-6 text-base font-semibold text-zinc-100">Positions</h1>
      <QueryState
        isLoading={exLoading}
        isEmpty={(exchanges ?? []).length === 0}
        emptyLabel="Aucune donnée exchange"
      />
      <div className="grid gap-4 grid-cols-1 xl:grid-cols-2">
        {(exchanges ?? []).map((ex) => (
          <ExchangeCard key={ex.exchange} ex={ex} positions={positions ?? []} />
        ))}
      </div>
    </div>
  )
}
