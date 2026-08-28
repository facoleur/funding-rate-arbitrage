/**
 * Métadonnées d'affichage par exchange : couleurs, abréviations et liens profonds.
 *
 * Regroupe ce qui était éparpillé entre `Book.tsx` (abréviations + URLs) et
 * `History.tsx` (couleurs). `toNativeDeribitName` reste une concession : c'est de
 * la connaissance d'exchange côté client, en attendant que `/api/tickers` serve
 * directement l'URL.
 */

export const EXCHANGE_COLORS: Record<string, string> = {
  derive: 'text-violet-400',
  deribit: 'text-sky-400',
  deribit_linear: 'text-cyan-400',
  aevo: 'text-amber-400',
}

export const EXCHANGE_ABBR: Record<string, string> = {
  deribit: 'Db',
  deribit_linear: 'DL',
  derive: 'Dr',
  aevo: 'Av',
}

export function exchangeColor(name: string): string {
  return EXCHANGE_COLORS[name] ?? 'text-zinc-400'
}

export function exchangeAbbr(name: string): string {
  return EXCHANGE_ABBR[name] ?? name.slice(0, 2)
}

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/** Nom normalisé `BTC-20260828-50000-C` → nom natif Deribit `BTC-28AUG26-50000-C`. */
export function toNativeDeribitName(instrument: string): string | null {
  const m = instrument.match(/^([A-Z]+)-(\d{4})(\d{2})(\d{2})-(\d+(?:\.\d+)?)-([CP])$/)
  if (!m) return null
  const [, underlying, year, month, day, strike, optionType] = m
  return `${underlying}-${parseInt(day)}${MONTHS[parseInt(month) - 1]}${year.slice(2)}-${strike}-${optionType}`
}

/** Lien profond vers l'instrument sur l'exchange, ou `null` si non constructible. */
export function exchangeUrl(
  exchange: string,
  instrument: string,
  underlying: string,
): string | null {
  switch (exchange) {
    case 'deribit':
    case 'deribit_linear': {
      const native = toNativeDeribitName(instrument)
      if (!native) return null
      const [sym, expiry] = native.split('-')
      return `https://www.deribit.com/options/${underlying}/${sym}-${expiry}/${native}`
    }
    case 'derive':
      return `https://app.derive.xyz/trade/${instrument}`
    case 'aevo': {
      const native = toNativeDeribitName(instrument)
      return native ? `https://app.aevo.xyz/trade/${native}` : null
    }
    default:
      return null
  }
}
