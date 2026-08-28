import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fmtAge,
  fmtDateTime,
  fmtDateTimeSec,
  fmtDte,
  fmtExpiry,
  fmtUsd,
  fmtUsdOrDash,
  hoursUntil,
} from './format'

/** Date construite en heure locale : le rendu est déterministe quel que soit le TZ. */
function local(y: number, m: number, d: number, h = 0, min = 0, s = 0): string {
  return new Date(y, m - 1, d, h, min, s).toISOString()
}

afterEach(() => {
  vi.useRealTimers()
})

describe('fmtUsd', () => {
  it('arrondit au centime sous 1000', () => {
    expect(fmtUsd(12.3456)).toBe('$12.35')
    expect(fmtUsd(999.99)).toBe('$999.99')
  })

  it('bascule en milliers à partir de 1000, avec deux décimales', () => {
    expect(fmtUsd(1000)).toBe('$1.00k')
    expect(fmtUsd(1234.5)).toBe('$1.23k')
  })

  it('traite zéro comme un montant réel', () => {
    expect(fmtUsd(0)).toBe('$0.00')
  })
})

describe('fmtUsdOrDash', () => {
  it('remplace zéro par un tiret', () => {
    expect(fmtUsdOrDash(0)).toBe('—')
  })

  it('formate comme fmtUsd au-delà de zéro', () => {
    expect(fmtUsdOrDash(1234.5)).toBe('$1.23k')
    expect(fmtUsdOrDash(5)).toBe('$5.00')
  })
})

describe('fmtDte', () => {
  it('passe en heures sous un jour', () => {
    expect(fmtDte(0.5)).toBe('12h')
    expect(fmtDte(0.04)).toBe('1h')
  })

  it('arrondit en jours au-delà', () => {
    expect(fmtDte(1)).toBe('1j')
    expect(fmtDte(30.4)).toBe('30j')
  })
})

describe('fmtAge', () => {
  it('graduent secondes, minutes puis heures', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 28, 12, 0, 0))

    expect(fmtAge(local(2026, 8, 28, 11, 59, 18))).toBe('42s')
    expect(fmtAge(local(2026, 8, 28, 11, 53, 0))).toBe('7m')
    expect(fmtAge(local(2026, 8, 28, 9, 0, 0))).toBe('3h')
  })
})

describe('hoursUntil', () => {
  it('compte les heures restantes, négatif une fois passé', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 28, 12, 0, 0))

    expect(hoursUntil(local(2026, 8, 28, 18, 0, 0))).toBeCloseTo(6)
    expect(hoursUntil(local(2026, 8, 28, 6, 0, 0))).toBeCloseTo(-6)
  })
})

describe('formats de date', () => {
  const iso = local(2026, 8, 28, 14, 32, 7)

  it('fmtExpiry donne jour, mois abrégé et année courte', () => {
    expect(fmtExpiry(iso)).toBe('28 août 26')
  })

  it('fmtDateTime porte l’année, pour les listes longues', () => {
    expect(fmtDateTime(iso)).toBe('28/08/26 14:32')
  })

  it('fmtDateTimeSec porte les secondes, pour les trades', () => {
    expect(fmtDateTimeSec(iso)).toBe('28/08 14:32:07')
  })
})
