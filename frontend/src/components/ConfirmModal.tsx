interface Props {
  message: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmModal({ message, onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-6 shadow-xl">
        <p className="mb-6 text-sm text-zinc-200">{message}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
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
    </div>
  )
}
