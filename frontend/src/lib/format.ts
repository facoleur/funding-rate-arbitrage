/**
 * Formatters partagés par toutes les pages.
 *
 * Ce module existe parce que les mêmes fonctions étaient réécrites page par page
 * et avaient divergé : deux arrondis USD différents et trois formats de date pour
 * la même colonne. Les variantes qui subsistent ici sont délibérées, pas subies.
 */

const LOCALE = 'fr-FR'

/** `2026-08-28T00:00:00Z` → `28 août 26` */
export function fmtExpiry(iso: string): string {
  return new Date(iso).toLocaleDateString(LOCALE, {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  })
}

/** Heures restantes avant une échéance — négatif si déjà passée. */
export function hoursUntil(iso: string): number {
  return (new Date(iso).getTime() - Date.now()) / 3_600_000
}

/** Ancienneté compacte depuis un timestamp : `42s`, `7m`, `3h`. */
export function fmtAge(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

/** Jours jusqu'à expiration : sous 1 jour on bascule en heures. */
export function fmtDte(days: number): string {
  if (days < 1) return `${Math.round(days * 24)}h`
  return `${Math.round(days)}j`
}

/** Montant USD : `$12.34`, `$1.23k`. Zéro est une valeur réelle → `$0.00`. */
export function fmtUsd(n: number): string {
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(2)}k`
  return `$${n.toFixed(2)}`
}

/** Comme `fmtUsd`, mais zéro signifie « pas de donnée » et s'affiche `—`.
 *  Réservé aux grilles où 0 traduit une absence, pas un montant nul. */
export function fmtUsdOrDash(n: number): string {
  if (n === 0) return '—'
  return fmtUsd(n)
}

/** `28/08/26 14:32` — pour les listes qui s'étalent sur plusieurs mois. */
export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** `28/08 14:32:07` — pour les trades, où la seconde d'exécution compte. */
export function fmtDateTimeSec(iso: string): string {
  return new Date(iso).toLocaleString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** `14:32:07` */
export function fmtTime(iso: string | number): string {
  return new Date(iso).toLocaleTimeString(LOCALE)
}
