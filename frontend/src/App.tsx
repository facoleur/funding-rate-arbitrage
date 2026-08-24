import { Component, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="p-8 text-red-400 font-mono text-xs whitespace-pre-wrap">
          <p className="text-red-300 font-bold mb-2">Render error:</p>
          {(this.state.error as Error).message}
          {'\n\n'}
          {(this.state.error as Error).stack}
        </div>
      )
    }
    return this.props.children
  }
}
import Opportunities from './pages/Opportunities'
import Trades from './pages/Trades'
import Positions from './pages/Positions'
import Executor from './pages/Executor'
import Book from './pages/Book'
import History from './pages/History'
import Funding from './pages/Funding'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ErrorBoundary><Layout /></ErrorBoundary>}>
          <Route index element={<Opportunities />} />
          <Route path="trades" element={<Trades />} />
          <Route path="positions" element={<Positions />} />
          <Route path="book" element={<Book />} />
          <Route path="history" element={<History />} />
          <Route path="funding" element={<Funding />} />
          <Route path="executor" element={<Executor />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
