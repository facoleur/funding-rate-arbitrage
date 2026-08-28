import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(cleanup)

/**
 * jsdom 30 n'implémente toujours pas `HTMLDialogElement.showModal()`.
 *
 * Ce polyfill reproduit uniquement ce dont les tests ont besoin : ouvrir/fermer
 * et émettre l'évènement `close`. Il ne simule ni le piège de focus ni la touche
 * Escape — ce sont des comportements du navigateur, pas du code applicatif, et
 * les tester ici reviendrait à tester le polyfill. Les tests vérifient donc le
 * câblage `onClose → onCancel`, qui est ce qui rend Escape effectif en vrai.
 */
if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false
    this.dispatchEvent(new Event('close'))
  }
}
