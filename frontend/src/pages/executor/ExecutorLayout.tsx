import { Outlet } from 'react-router-dom'
import Tabs from '../../components/ui/Tabs'

export default function ExecutorLayout() {
  return (
    <div>
      <Tabs
        tabs={[
          { to: '/executor', label: 'Status', end: true },
          { to: '/executor/positions', label: 'Positions' },
        ]}
      />
      <Outlet />
    </div>
  )
}
