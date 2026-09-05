import { Outlet } from 'react-router-dom'
import Tabs from '../../components/ui/Tabs'

export default function OpportunitiesLayout() {
  return (
    <div className="flex h-full flex-col">
      <Tabs
        tabs={[
          { to: '/opportunites/live', label: 'Live' },
          { to: '/opportunites/historique', label: 'Historique' },
        ]}
      />
      <div className="min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
