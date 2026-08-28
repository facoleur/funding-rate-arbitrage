import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
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
        <Route
          element={
            <ErrorBoundary>
              <Layout />
            </ErrorBoundary>
          }
        >
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
