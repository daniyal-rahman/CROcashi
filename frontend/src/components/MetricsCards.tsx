import { CompanyMetrics } from '../api/client'

interface MetricsCardsProps {
  metrics: CompanyMetrics
}

export default function MetricsCards({ metrics }: MetricsCardsProps) {
  const cards = [
    {
      title: 'Total Trials',
      value: metrics.total_trials,
      color: 'bg-blue-500'
    },
    {
      title: 'Active Trials',
      value: metrics.active_trials,
      color: 'bg-green-500'
    },
    {
      title: 'Terminated',
      value: metrics.terminated_count,
      color: 'bg-red-500'
    },
    {
      title: 'Total Drugs',
      value: metrics.total_drugs ?? 0,
      color: 'bg-cyan-500'
    },
    {
      title: 'Pipeline Velocity',
      value: metrics.pipeline_velocity.toFixed(1),
      subtitle: 'programs/year',
      color: 'bg-purple-500'
    },
    {
      title: 'Publications',
      value: metrics.publications_count ?? 0,
      subtitle: metrics.publications_with_trials > 0 
        ? `${metrics.publications_with_trials} about trials`
        : undefined,
      color: 'bg-teal-500'
    },
    {
      title: 'SEC Filings',
      value: metrics.filings_with_drugs ?? 0,
      subtitle: 'with drug mentions',
      color: 'bg-orange-500'
    },
    {
      title: 'Phase 1 Success',
      value: metrics.success_rate_phase_1 
        ? `${(metrics.success_rate_phase_1 * 100).toFixed(1)}%`
        : 'N/A',
      color: 'bg-indigo-500'
    },
    {
      title: 'Phase 2 Success',
      value: metrics.success_rate_phase_2
        ? `${(metrics.success_rate_phase_2 * 100).toFixed(1)}%`
        : 'N/A',
      color: 'bg-indigo-500'
    },
    {
      title: 'Phase 3 Success',
      value: metrics.success_rate_phase_3
        ? `${(metrics.success_rate_phase_3 * 100).toFixed(1)}%`
        : 'N/A',
      color: 'bg-indigo-500'
    },
    {
      title: 'Days Since Update',
      value: metrics.days_since_last_update ?? 'N/A',
      color: 'bg-yellow-500'
    }
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {cards.map((card, index) => (
        <div key={index} className="bg-white rounded-lg shadow-md p-4">
          <div className="text-sm text-gray-600 mb-1">{card.title}</div>
          <div className="flex items-baseline">
            <div className="text-2xl font-bold">{card.value}</div>
            {card.subtitle && (
              <div className="ml-2 text-sm text-gray-500">{card.subtitle}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

