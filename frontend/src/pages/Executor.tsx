import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchExecutorState, killExecutor, resumeExecutor } from '../api/executor'
import { fetchAlerts } from '../api/alerts'
import StatusBadge from '../components/StatusBadge'
import ConfirmModal from '../components/ConfirmModal'

function Bar({ value, max, danger }: { value: number; max: number; danger?: boolean }) {
  const pct = Math.min(100, Math.abs(max) > 0 ? (Math.abs(value) / Math.abs(max)) * 100 : 0)
  return (
    <div className="mt-1 h-1.5 w-full rounded-full bg-zinc-800">
      <div
        className={`h-1.5 rounded-full transition-all ${danger ? 'bg-red-500' : 'bg-emerald-500'}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export default function Executor() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<'kill' | 'resume' | null>(null)

  const { data: state, isLoading, isError } = useQuery({
    queryKey: ['executor'],
    queryFn: fetchExecutorState,
    refetchInterval: 5000,
  })

  const { data: alerts } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => fetchAlerts({ limit: 50 }),
    refetchInterval: 30000,
  })

  const killMut = useMutation({
    mutationFn: killExecutor,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['executor'] }),
  })

  const resumeMut = useMutation({
    mutationFn: resumeExecutor,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['executor'] }),
  })

  if (isLoading) return <p className="text-xs text-zinc-500">Chargement...</p>
  if (isError || !state) return <p className="text-xs text-red-400">Erreur de chargement</p>

  const { config, counters } = state
  const dailyLossUsed = -Math.min(0, counters.daily_pnl_usd)

  return (
    <div className="max-w-2xl">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-semibold text-zinc-100">Executor</h1>
          <StatusBadge value={state.status} />
          <span className="text-xs text-zinc-500 capitalize">{config.mode}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setModal('kill')}
            disabled={state.status === 'KILLED'}
            className="rounded border border-red-800 px-3 py-1 text-xs text-red-400 hover:bg-red-950 disabled:opacity-30"
          >
            Kill
          </button>
          <button
            onClick={() => setModal('resume')}
            disabled={state.status === 'RUNNING'}
            className="rounded border border-emerald-800 px-3 py-1 text-xs text-emerald-400 hover:bg-emerald-950 disabled:opacity-30"
          >
            Resume
          </button>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3">
        <div className="rounded border border-zinc-800 bg-zinc-900 p-3">
          <p className="mb-3 text-xs font-medium text-zinc-400 uppercase tracking-wide">Limites actives</p>
          <div className="space-y-3 text-xs">
            <div>
              <div className="flex justify-between text-zinc-400">
                <span>Positions ouvertes</span>
                <span className="text-zinc-200">{counters.open_positions} / {config.max_positions_open}</span>
              </div>
              <Bar value={counters.open_positions} max={config.max_positions_open} />
            </div>
            <div>
              <div className="flex justify-between text-zinc-400">
                <span>Perte journalière</span>
                <span className={dailyLossUsed > 0 ? 'text-red-400' : 'text-zinc-200'}>
                  ${dailyLossUsed.toFixed(2)} / ${config.max_daily_loss_usd}
                </span>
              </div>
              <Bar value={dailyLossUsed} max={config.max_daily_loss_usd} danger={dailyLossUsed > config.max_daily_loss_usd * 0.8} />
            </div>
            <div className="flex justify-between text-zinc-400">
              <span>PnL journalier</span>
              <span className={counters.daily_pnl_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                {counters.daily_pnl_usd >= 0 ? '+' : ''}${counters.daily_pnl_usd.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        <div className="rounded border border-zinc-800 bg-zinc-900 p-3">
          <p className="mb-3 text-xs font-medium text-zinc-400 uppercase tracking-wide">Config</p>
          <div className="space-y-1.5 text-xs text-zinc-400">
            <div className="flex justify-between">
              <span>APR min</span>
              <span className="text-zinc-200">{config.min_apr_pct}%</span>
            </div>
            <div className="flex justify-between">
              <span>Notional min</span>
              <span className="text-zinc-200">${config.min_notional_usd}</span>
            </div>
            <div className="flex justify-between">
              <span>Notional max / trade</span>
              <span className="text-zinc-200">${config.max_notional_per_trade_usd}</span>
            </div>
            <div className="flex justify-between">
              <span>Max positions</span>
              <span className="text-zinc-200">{config.max_positions_open}</span>
            </div>
            <div className="flex justify-between">
              <span>Perte max / jour</span>
              <span className="text-zinc-200">${config.max_daily_loss_usd}</span>
            </div>
          </div>
        </div>
      </div>

      <div>
        <p className="mb-3 text-xs font-medium text-zinc-400 uppercase tracking-wide">Alertes récentes</p>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-500">
              <th className="pb-1.5 pr-3">Niveau</th>
              <th className="pb-1.5 pr-3">Canal</th>
              <th className="pb-1.5 pr-3">Message</th>
              <th className="pb-1.5">Date</th>
            </tr>
          </thead>
          <tbody>
            {(alerts ?? []).length === 0 && (
              <tr>
                <td colSpan={4} className="pt-4 text-center text-zinc-600">Aucune alerte</td>
              </tr>
            )}
            {(alerts ?? []).map((a) => (
              <tr key={a.id} className="border-b border-zinc-800/40">
                <td className="py-1 pr-3"><StatusBadge value={a.level} /></td>
                <td className="py-1 pr-3 text-zinc-500">{a.channel}</td>
                <td className="py-1 pr-3 text-zinc-300 max-w-xs truncate">{a.message}</td>
                <td className="py-1 text-zinc-500 whitespace-nowrap">
                  {new Date(a.sent_at).toLocaleString('fr-FR', {
                    day: '2-digit', month: '2-digit',
                    hour: '2-digit', minute: '2-digit',
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal === 'kill' && (
        <ConfirmModal
          message="Confirmer le kill-switch de l'executor ? Aucun nouvel ordre ne sera placé."
          onConfirm={() => { killMut.mutate(); setModal(null) }}
          onCancel={() => setModal(null)}
        />
      )}
      {modal === 'resume' && (
        <ConfirmModal
          message="Relancer l'executor ? Les ordres pourront à nouveau être placés."
          onConfirm={() => { resumeMut.mutate(); setModal(null) }}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  )
}
