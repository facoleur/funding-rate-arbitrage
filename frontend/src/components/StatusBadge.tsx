interface Props {
  value: string
}

const colorMap: Record<string, string> = {
  RUNNING: 'bg-emerald-900 text-emerald-300',
  KILLED: 'bg-red-900 text-red-300',
  CONNECTED: 'bg-emerald-900 text-emerald-300',
  RECONNECTING: 'bg-yellow-900 text-yellow-300',
  UNHEALTHY: 'bg-red-900 text-red-300',
  OK: 'bg-emerald-900 text-emerald-300',
  RATE_LIMITED: 'bg-yellow-900 text-yellow-300',
  DOWN: 'bg-red-900 text-red-300',
  PENDING: 'bg-zinc-700 text-zinc-300',
  EXECUTED: 'bg-emerald-900 text-emerald-300',
  REJECTED: 'bg-red-900 text-red-300',
  EXPIRED: 'bg-zinc-700 text-zinc-400',
  APPROVED: 'bg-blue-900 text-blue-300',
  FILLED: 'bg-emerald-900 text-emerald-300',
  HEDGED: 'bg-yellow-900 text-yellow-300',
  STUCK: 'bg-red-900 text-red-300',
  FAILED: 'bg-red-900 text-red-300',
  PLACING: 'bg-blue-900 text-blue-300',
  HEDGING: 'bg-yellow-900 text-yellow-300',
  live: 'bg-emerald-900 text-emerald-300',
  paper: 'bg-blue-900 text-blue-300',
  backtest: 'bg-zinc-700 text-zinc-300',
  info: 'bg-blue-900 text-blue-300',
  warn: 'bg-yellow-900 text-yellow-300',
  error: 'bg-red-900 text-red-300',
}

export default function StatusBadge({ value }: Props) {
  const cls = colorMap[value] ?? 'bg-zinc-700 text-zinc-300'
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {value}
    </span>
  )
}
