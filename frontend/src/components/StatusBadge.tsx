import type { components } from '../api/generated/schema'

/**
 * Union exhaustive des valeurs que ce badge sait colorer.
 *
 * Elle est dérivée des énumérations générées depuis le contrat OpenAPI : ajouter
 * un statut côté backend fait échouer la compilation ici tant que sa couleur n'est
 * pas définie, au lieu de l'afficher silencieusement en gris.
 */
export type BadgeValue =
  | components['schemas']['OpportunityStatus']
  | components['schemas']['TradeStatus']
  | components['schemas']['Mode']
  | components['schemas']['AlertLevel']
  | components['schemas']['WsStatus']
  | components['schemas']['RestStatus']
  | components['schemas']['ExecutorStateResponse']['status']

const EMERALD = 'bg-emerald-900 text-emerald-300'
const RED = 'bg-red-900 text-red-300'
const YELLOW = 'bg-yellow-900 text-yellow-300'
const BLUE = 'bg-blue-900 text-blue-300'
const NEUTRAL = 'bg-zinc-700 text-zinc-300'

const COLORS: Record<BadgeValue, string> = {
  // Executor
  RUNNING: EMERALD,
  KILLED: RED,
  // WebSocket / REST
  CONNECTED: EMERALD,
  RECONNECTING: YELLOW,
  UNHEALTHY: RED,
  OK: EMERALD,
  RATE_LIMITED: YELLOW,
  DOWN: RED,
  // Opportunités
  PENDING: NEUTRAL,
  APPROVED: BLUE,
  EXECUTED: EMERALD,
  REJECTED: RED,
  EXPIRED: 'bg-zinc-700 text-zinc-400',
  // Trades
  PLACING: BLUE,
  LEG1_FILLED: YELLOW,
  LEG2_FILLED: YELLOW,
  FILLED: EMERALD,
  HEDGING: YELLOW,
  HEDGED: YELLOW,
  STUCK: RED,
  FAILED: RED,
  // Modes
  live: EMERALD,
  paper: BLUE,
  backtest: NEUTRAL,
  // Alertes
  info: BLUE,
  warn: YELLOW,
  error: RED,
}

export default function StatusBadge({ value }: { value: BadgeValue }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${COLORS[value]}`}>
      {value}
    </span>
  )
}
