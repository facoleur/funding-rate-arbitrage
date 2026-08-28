import { useEffect, useRef } from 'react'

interface Props {
  message: string
  onConfirm: () => void
  onCancel: () => void
}

/**
 * `<dialog>` natif ouvert via showModal() : Escape, piège de focus et backdrop
 * sont fournis par le navigateur. Le focus part sur « Annuler » (premier élément
 * focusable), ce qui est le défaut sûr pour une confirmation de kill-switch.
 */
export default function ConfirmModal({ message, onConfirm, onCancel }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    ref.current?.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      onClose={onCancel}
      onClick={(e) => {
        // clic sur le backdrop : la cible est le <dialog> lui-même, pas son contenu
        if (e.target === ref.current) ref.current?.close()
      }}
      aria-label="Confirmation"
      className="bg-transparent p-0 text-zinc-100 backdrop:bg-black/60"
    >
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-6 shadow-xl">
        <p className="mb-6 text-sm text-zinc-200">{message}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={() => ref.current?.close()}
            className="rounded px-4 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-500"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            className="rounded bg-red-700 px-4 py-1.5 text-sm text-white hover:bg-red-600"
          >
            Confirmer
          </button>
        </div>
      </div>
    </dialog>
  )
}
