import { useQuery } from '@tanstack/react-query'
import { fetchExchanges, fetchPositions, type ExchangeState, type Position } from '../api/positions'
import StatusBadge from '../components/StatusBadge'

function fmtExpiry(iso: string) {
  const d = new Date(iso)
  const hoursLeft = (d.getTime() - Date.now()) / 3600000
  const str = d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: '2-digit' })
  return { str, urgent: hoursLeft < 24 }
}

function ExchangeCard({
  ex,
  positions,
}: {
  ex: ExchangeState
  positions: Position[]
}) {
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
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-500">
              <th className="pb-1.5 pr-4">Instrument</th>
              <th className="pb-1.5 pr-4 text-right">Size</th>
              <th className="pb-1.5 pr-4 text-right">Avg price</th>
              <th className="pb-1.5">Expiry</th>
            </tr>
          </thead>
          <tbody>
            {ownPositions.map((p) => {
              const { str, urgent } = fmtExpiry(p.instrument.split('-')[1] ?? p.last_seen_at)
              return (
                <tr key={p.id} className="border-b border-zinc-800/40">
                  <td className="py-1 pr-4 text-zinc-200 font-medium">{p.instrument}</td>
                  <td className="py-1 pr-4 text-right text-zinc-300">{p.size}</td>
                  <td className="py-1 pr-4 text-right text-zinc-300">${p.avg_price.toFixed(2)}</td>
                  <td className={`py-1 ${urgent ? 'text-red-400 font-medium' : 'text-zinc-400'}`}>
                    {str}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <p className="mt-2 text-xs text-zinc-600">
        Mis à jour {new Date(ex.updated_at).toLocaleTimeString('fr-FR')}
      </p>
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
      {exLoading && <p className="text-xs text-zinc-500">Chargement...</p>}
      <div className="grid gap-4 grid-cols-1 xl:grid-cols-2">
        {(exchanges ?? []).map((ex) => (
          <ExchangeCard key={ex.exchange} ex={ex} positions={positions ?? []} />
        ))}
        {!exLoading && (exchanges ?? []).length === 0 && (
          <p className="text-xs text-zinc-600">Aucune donnée exchange</p>
        )}
      </div>
    </div>
  )
}
