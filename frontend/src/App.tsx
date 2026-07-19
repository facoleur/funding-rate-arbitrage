import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Opportunities from './pages/Opportunities'
import Trades from './pages/Trades'
import Positions from './pages/Positions'
import Executor from './pages/Executor'
import Book from './pages/Book'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Opportunities />} />
          <Route path="trades" element={<Trades />} />
          <Route path="positions" element={<Positions />} />
          <Route path="executor" element={<Executor />} />
          <Route path="book" element={<Book />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
