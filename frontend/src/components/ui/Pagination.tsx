/**
 * Pagination par offset. `count` est le nombre de lignes de la page courante :
 * une page incomplète signifie qu'il n'y a pas de suivante.
 */
export default function Pagination({
  offset,
  pageSize,
  count,
  onOffsetChange,
}: {
  offset: number
  pageSize: number
  count: number
  onOffsetChange: (offset: number) => void
}) {
  const page = Math.floor(offset / pageSize) + 1

  return (
    <div className="mt-3 flex items-center gap-3 text-xs text-zinc-500">
      <button
        disabled={offset === 0}
        onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
        className="rounded border border-zinc-700 px-2 py-1 disabled:opacity-30 enabled:hover:border-zinc-500 enabled:hover:text-zinc-200"
      >
        ← Précédent
      </button>
      <span>
        Page {page}
        {count > 0 && ` · ${offset + 1}–${offset + count}`}
      </span>
      <button
        disabled={count < pageSize}
        onClick={() => onOffsetChange(offset + pageSize)}
        className="rounded border border-zinc-700 px-2 py-1 disabled:opacity-30 enabled:hover:border-zinc-500 enabled:hover:text-zinc-200"
      >
        Suivant →
      </button>
    </div>
  )
}
