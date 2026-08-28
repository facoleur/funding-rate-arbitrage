import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/**
 * Filet de dernier recours pour les erreurs de rendu.
 *
 * Affiche volontairement le message et la stack : c'est un outil interne
 * mono-utilisateur, et une page blanche coûterait plus cher qu'une trace.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div className="whitespace-pre-wrap p-8 font-mono text-xs text-red-400">
          <p className="mb-2 font-bold text-red-300">Render error:</p>
          {error.message}
          {'\n\n'}
          {error.stack}
        </div>
      )
    }
    return this.props.children
  }
}
