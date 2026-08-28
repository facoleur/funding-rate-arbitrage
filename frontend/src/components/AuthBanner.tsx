import { useSyncExternalStore } from 'react'

import { isUnauthorized, subscribeUnauthorized } from '../lib/authError'

export default function AuthBanner() {
  const unauthorized = useSyncExternalStore(subscribeUnauthorized, isUnauthorized)
  if (!unauthorized) return null

  return (
    <div
      role="alert"
      className="flex items-center justify-center gap-3 border-b border-amber-800 bg-amber-950 px-4 py-2 text-xs text-amber-200"
    >
      <span>Authentification refusée (401) — la session n'est plus valide.</span>
      <button
        onClick={() => window.location.reload()}
        className="rounded border border-amber-700 px-2 py-0.5 hover:bg-amber-900"
      >
        Recharger
      </button>
    </div>
  )
}
