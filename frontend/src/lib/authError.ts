/**
 * Signal global « la requête a été refusée par l'authentification ».
 *
 * Le site est derrière `basic_auth` Caddy : un 401 ne se rattrape pas dans la
 * page (les identifiants sont gérés par le navigateur), la seule sortie est un
 * rechargement qui redéclenche le dialogue. On expose donc un booléen unique,
 * consommé par `<AuthBanner>` via `useSyncExternalStore`.
 */

let unauthorized = false
const listeners = new Set<() => void>()

export function reportUnauthorized(): void {
  if (unauthorized) return
  unauthorized = true
  for (const listener of listeners) listener()
}

export function subscribeUnauthorized(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function isUnauthorized(): boolean {
  return unauthorized
}

/** Réservé aux tests — remet le module à zéro entre deux cas. */
export function resetUnauthorized(): void {
  unauthorized = false
  listeners.clear()
}
