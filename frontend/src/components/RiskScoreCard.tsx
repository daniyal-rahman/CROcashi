import { CompanyRiskProfile } from '../api/client'

interface RiskScoreCardProps {
  riskProfile: CompanyRiskProfile
}

export default function RiskScoreCard({ riskProfile }: RiskScoreCardProps) {
  const getRiskColor = (category: string) => {
    switch (category) {
      case 'LOW': return 'bg-green-500'
      case 'MODERATE': return 'bg-yellow-500'
      case 'HIGH': return 'bg-orange-500'
      case 'CRITICAL': return 'bg-red-500'
      default: return 'bg-gray-400'
    }
  }

  const getRiskGaugeColor = (category: string) => {
    switch (category) {
      case 'LOW': return '#10b981' // green-500
      case 'MODERATE': return '#eab308' // yellow-500
      case 'HIGH': return '#f97316' // orange-500
      case 'CRITICAL': return '#ef4444' // red-500
      default: return '#6b7280' // gray-500
    }
  }

  // Calculate gauge angle (0-180 degrees for semicircle)
  const riskScore = riskProfile.risk_score ?? 0
  const angle = (riskScore / 100) * 180

  const gaugeColor = getRiskGaugeColor(riskProfile.risk_category)

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="flex items-start justify-between gap-8">
        <div className="flex-1">
          <div className="relative w-64 h-32 mb-4">
            {/* Gauge background */}
            <svg className="w-full h-full" viewBox="0 0 200 100" style={{ overflow: 'visible' }}>
              {/* Background arc */}
              <path
                d="M 20 80 A 80 80 0 0 1 180 80"
                fill="none"
                stroke="#e5e7eb"
                strokeWidth="20"
              />
              {/* Risk arc */}
              <path
                d="M 20 80 A 80 80 0 0 1 180 80"
                fill="none"
                stroke={gaugeColor}
                strokeWidth="20"
                strokeDasharray={`${angle * Math.PI * 80 / 180} 251.2`}
                strokeDashoffset="125.6"
                strokeLinecap="round"
              />
            </svg>
            {/* Score text */}
            <div className="absolute inset-0 flex items-center justify-center pt-2">
              <div className="text-center">
                <div className="text-5xl font-bold" style={{ color: gaugeColor }}>
                  {riskScore.toFixed(0)}
                </div>
                <div className="text-sm text-gray-500 mt-1">Risk Score (0-100)</div>
              </div>
            </div>
          </div>
          
          <div className={`inline-block px-4 py-2 rounded-full ${getRiskColor(riskProfile.risk_category)} text-white font-semibold`}>
            {riskProfile.risk_category} RISK
          </div>
        </div>

        <div className="flex-1 ml-8">
          <h3 className="font-semibold mb-2">Component Breakdown</h3>
          <div className="space-y-2">
            {Object.entries(riskProfile.components).map(([key, component]) => (
              <div key={key} className="text-sm">
                <div className="flex justify-between mb-1">
                  <span className="capitalize">{key.replace('_', ' ')}</span>
                  <span className="font-medium">{component.score.toFixed(1)} / {component.weight}</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full"
                    style={{ width: `${(component.score / component.weight) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

