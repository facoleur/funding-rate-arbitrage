import { Outlet } from 'react-router-dom'
import Tabs from '../../components/ui/Tabs'

export default function StructuredLayout() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0">
        <h1 className="mb-2 text-base font-semibold text-zinc-100">Structured</h1>
        <Tabs
          tabs={[
            { to: '/structured/live', label: 'Live' },
            { to: '/structured/historique', label: 'Historique' },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
