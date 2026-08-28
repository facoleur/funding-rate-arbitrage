/**
 * Triplet chargement / erreur / vide, répété dans les 7 pages avec des libellés
 * qui avaient divergé. Rend `null` quand les données sont là.
 */
export default function QueryState({
  isLoading,
  isError = false,
  isEmpty = false,
  emptyLabel = 'Aucune donnée',
}: {
  isLoading: boolean
  isError?: boolean
  isEmpty?: boolean
  emptyLabel?: string
}) {
  if (isLoading) return <p className="text-xs text-zinc-500">Chargement...</p>
  if (isError) return <p className="text-xs text-red-400">Erreur de chargement</p>
  if (isEmpty) return <p className="text-xs text-zinc-600">{emptyLabel}</p>
  return null
}
