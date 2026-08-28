import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ConfirmModal from './ConfirmModal'

function setup() {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(<ConfirmModal message="Confirmer ?" onConfirm={onConfirm} onCancel={onCancel} />)
  const dialog = screen.getByRole('dialog', { hidden: true }) as HTMLDialogElement
  return { onConfirm, onCancel, dialog }
}

describe('ConfirmModal', () => {
  it("s'ouvre en modale au montage", () => {
    const { dialog } = setup()
    expect(dialog.open).toBe(true)
  })

  it('ne confirme que sur clic explicite « Confirmer »', async () => {
    const { onConfirm, onCancel } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('annule sur « Annuler » sans jamais confirmer', async () => {
    const { onConfirm, onCancel } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('annule sur clic hors du panneau', async () => {
    const { onConfirm, onCancel, dialog } = setup()
    await userEvent.click(dialog)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  // Escape déclenche `close` dans le navigateur ; on vérifie ici le câblage
  // `onClose → onCancel` qui est ce qui rend Escape effectif.
  it('annule quand le dialogue se ferme (chemin emprunté par Escape)', () => {
    const { onConfirm, onCancel, dialog } = setup()
    dialog.close()
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
