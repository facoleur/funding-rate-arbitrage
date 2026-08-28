import type { ReactNode } from 'react'

/** Habillage commun des champs de filtre. Cette chaîne était copiée dans 5 pages. */
export const FIELD_CLASS =
  'rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none'

export function Select({
  value,
  onChange,
  children,
  className = '',
}: {
  value: string | number
  onChange: (value: string) => void
  children: ReactNode
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`${FIELD_CLASS} ${className}`}
    >
      {children}
    </select>
  )
}

export function NumberField({
  value,
  onChange,
  placeholder,
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}) {
  return (
    <input
      type="number"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={`${FIELD_CLASS} ${className}`}
    />
  )
}
