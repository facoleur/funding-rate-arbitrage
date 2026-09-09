import { Outlet } from 'react-router-dom'
import Tabs from '../../components/ui/Tabs'

export default function AnalyticsLayout() {
  return (
    <div>
      <Tabs
        tabs={[
          { to: '/analytics/backtest', label: 'Backtest' },
          { to: '/analytics/funding', label: 'Funding' },
        ]}
      />
      <Outlet />
    </div>
  )
}
