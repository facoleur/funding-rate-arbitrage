import { useEffect, useRef, useState } from 'react'

/** Menu déroulant de sélection des colonnes affichées. */
export default function ColumnPicker<Id extends string>({
  columns,
  visible,
  onToggle,
}: {
  columns: readonly { id: Id; label: string; tip?: string }[]
  visible: Set<Id>
  onToggle: (id: Id) => void
}) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onMouseDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [open])

  return (
    <div className="relative ml-auto" ref={menuRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500"
      >
        Colonnes
      </button>
      {open && (
        <div className="absolute right-0 top-7 z-50 min-w-[150px] rounded border border-zinc-700 bg-zinc-900 p-2 shadow-xl">
          {columns.map((c) => (
            <label
              key={c.id}
              className="flex cursor-pointer items-center gap-2 py-0.5 text-xs text-zinc-300 hover:text-zinc-100"
            >
              <input
                type="checkbox"
                checked={visible.has(c.id)}
                onChange={() => onToggle(c.id)}
                className="accent-emerald-500"
              />
              {c.label}
              {c.tip && (
                <span className="text-zinc-600" title={c.tip}>
                  ?
                </span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
