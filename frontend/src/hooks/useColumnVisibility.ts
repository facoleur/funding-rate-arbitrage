import { useCallback, useState } from 'react'

/**
 * Visibilité des colonnes d'une table, persistée dans `localStorage`.
 *
 * La sélection était perdue à chaque rechargement, ce qui est pénible sur une
 * grille à 18 colonnes. On stocke la liste des colonnes visibles et on la filtre
 * à la relecture : une colonne supprimée du code disparaît sans casser le reste.
 */
export function useColumnVisibility<Id extends string>(
  storageKey: string,
  columns: readonly { id: Id; defaultVisible: boolean }[],
): { visible: Set<Id>; toggle: (id: Id) => void } {
  const [visible, setVisible] = useState<Set<Id>>(() => {
    const known = new Set(columns.map((c) => c.id))
    try {
      const stored = localStorage.getItem(storageKey)
      if (stored) {
        const parsed: unknown = JSON.parse(stored)
        if (Array.isArray(parsed)) {
          return new Set(parsed.filter((id): id is Id => known.has(id as Id)))
        }
      }
    } catch {
      // localStorage indisponible ou contenu illisible → on repart des défauts
    }
    return new Set(columns.filter((c) => c.defaultVisible).map((c) => c.id))
  })

  const toggle = useCallback(
    (id: Id) => {
      setVisible((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        try {
          localStorage.setItem(storageKey, JSON.stringify([...next]))
        } catch {
          // pas de persistance possible : la session courante reste correcte
        }
        return next
      })
    },
    [storageKey],
  )

  return { visible, toggle }
}
