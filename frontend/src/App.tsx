import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import OpportunitiesLayout from './pages/opportunities/OpportunitiesLayout'
import Live from './pages/opportunities/Live'
import History from './pages/opportunities/History'
import Trades from './pages/Trades'
import Book from './pages/Book'
import ExecutorLayout from './pages/executor/ExecutorLayout'
import Status from './pages/executor/Status'
import Positions from './pages/executor/Positions'
import AnalyticsLayout from './pages/analytics/AnalyticsLayout'
import Funding from './pages/analytics/Funding'

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
          <Route index element={<Navigate to="/opportunites/live" replace />} />
          <Route path="opportunites" element={<OpportunitiesLayout />}>
            <Route index element={<Navigate to="live" replace />} />
            <Route path="live" element={<Live />} />
            <Route path="historique" element={<History />} />
          </Route>
          <Route path="trades" element={<Trades />} />
          <Route path="book" element={<Book />} />
          <Route path="executor" element={<ExecutorLayout />}>
            <Route index element={<Status />} />
            <Route path="positions" element={<Positions />} />
          </Route>
          <Route path="analytics" element={<AnalyticsLayout />}>
            <Route index element={<Navigate to="funding" replace />} />
            <Route path="funding" element={<Funding />} />
          </Route>
          <Route path="*" element={<Navigate to="/opportunites/live" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
