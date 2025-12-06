import { useState, useEffect, useMemo } from 'react'
import { apiClient, companyRiskApi } from '../api/client'

export interface FailedTrial {
  event_id: string
  event_type: string
  event_date: string
  event_data?: Record<string, any>
  entities: {
    company?: { id: string; name: string }
    trial?: { id: string; nct_id?: string; title?: string }
    drug?: { id: string; name: string }
    disease?: { id: string; name: string }
  }
  risk_score?: number
  risk_category?: string
}

type SortMode = 'date' | 'risk'

interface FailedTrialsListProps {
  onSelectCompany: (companyId: string) => void
  onSelectTrial: (trialId: string) => void
}

export default function FailedTrialsList({ onSelectCompany, onSelectTrial }: FailedTrialsListProps) {
  const [failures, setFailures] = useState<FailedTrial[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortMode, setSortMode] = useState<SortMode>('date')
  const [loadingRiskScores, setLoadingRiskScores] = useState(false)

  useEffect(() => {
    loadFailures()
  }, [])

  const loadFailures = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.get('/api/failures/recent?days=90&limit=50')
      const failuresData = response.data
      
      // Load risk scores for each company
      setLoadingRiskScores(true)
      const failuresWithRisk = await Promise.all(
        failuresData.map(async (failure: FailedTrial) => {
          if (failure.entities.company?.id) {
            try {
              const riskProfile = await companyRiskApi.getRiskProfile(failure.entities.company.id)
              return {
                ...failure,
                risk_score: riskProfile.risk_score,
                risk_category: riskProfile.risk_category
              }
            } catch (err) {
              console.warn(`Failed to load risk score for ${failure.entities.company.id}:`, err)
              return failure
            }
          }
          return failure
        })
      )
      
      setFailures(failuresWithRisk)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load failures')
      console.error('Error loading failures:', err)
    } finally {
      setLoading(false)
      setLoadingRiskScores(false)
    }
  }

  const sortedFailures = useMemo(() => {
    const sorted = [...failures]
    
    if (sortMode === 'risk') {
      // Sort by risk score (highest first), then by date
      sorted.sort((a, b) => {
        const riskA = a.risk_score ?? 0
        const riskB = b.risk_score ?? 0
        if (riskB !== riskA) {
          return riskB - riskA
        }
        // If risk scores are equal, sort by date (most recent first)
        return new Date(b.event_date).getTime() - new Date(a.event_date).getTime()
      })
    } else {
      // Sort by date (most recent first)
      sorted.sort((a, b) => {
        return new Date(b.event_date).getTime() - new Date(a.event_date).getTime()
      })
    }
    
    return sorted
  }, [failures, sortMode])

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  const getEventTypeLabel = (eventType: string) => {
    const labels: Record<string, string> = {
      'trial.status.terminated': 'Trial Terminated',
      'trial.status.withdrawn': 'Trial Withdrawn',
      'program.milestone.rejected': 'Program Rejected',
      'regulatory.rejection': 'Regulatory Rejection'
    }
    return labels[eventType] || eventType
  }

  const getRiskBadgeColor = (eventType: string) => {
    if (eventType.includes('terminated') || eventType.includes('rejection')) {
      return 'bg-red-100 text-red-800'
    }
    return 'bg-orange-100 text-orange-800'
  }

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        <div className="mt-2 text-gray-600">Loading recent failures...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
        {error}
      </div>
    )
  }

  if (failures.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg mb-2">No recent failures found</p>
        <p className="text-sm">Try adjusting the time range or check back later.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold text-gray-800">Recent High-Risk & Failed Trials</h2>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{failures.length} failures</span>
          
          {/* Sort Toggle */}
          <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setSortMode('date')}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                sortMode === 'date'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              By Date
            </button>
            <button
              onClick={() => setSortMode('risk')}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                sortMode === 'risk'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              By Risk Score
            </button>
          </div>
        </div>
      </div>

      {loadingRiskScores && (
        <div className="text-center py-2 text-sm text-gray-500">
          Loading risk scores...
        </div>
      )}

      {/* Info about risk scores */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
        <div className="flex items-start gap-2">
          <svg className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-sm text-blue-800">
            <p className="font-semibold mb-1">About Risk Scores:</p>
            <p className="text-blue-700">
              Risk scores are calculated at the <strong>company level</strong>, not individual trial level. 
              A single terminated trial may show LOW risk if the company has many successful trials (low failure rate). 
              Risk scores consider: failure rate (40 pts), recent failures (30 pts), pipeline stagnation (20 pts), and warning signals (10 pts).
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {sortedFailures.map((failure) => (
          <div
            key={failure.event_id}
            className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => {
              if (failure.entities.company) {
                onSelectCompany(failure.entities.company.id)
              } else if (failure.entities.trial) {
                onSelectTrial(failure.entities.trial.id)
              }
            }}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`px-2 py-1 rounded text-xs font-semibold ${getRiskBadgeColor(failure.event_type)}`}>
                    {getEventTypeLabel(failure.event_type)}
                  </span>
                  <span className="text-sm text-gray-500">{formatDate(failure.event_date)}</span>
                </div>

                {failure.entities.trial?.title && (
                  <h3 className="font-semibold text-gray-900 mb-1">
                    {failure.entities.trial.title}
                  </h3>
                )}

                {failure.entities.trial?.nct_id && (
                  <p className="text-sm text-gray-600 mb-2">NCT ID: {failure.entities.trial.nct_id}</p>
                )}

                <div className="flex flex-wrap gap-3 text-sm text-gray-600 items-center">
                  {failure.entities.company && (
                    <span className="flex items-center gap-1">
                      <span className="font-medium">Company:</span>
                      <span className="text-blue-600 hover:text-blue-800 font-semibold">
                        {failure.entities.company.name}
                      </span>
                    </span>
                  )}
                  {failure.entities.drug && (
                    <span className="flex items-center gap-1">
                      <span className="font-medium">Drug:</span>
                      <span>{failure.entities.drug.name}</span>
                    </span>
                  )}
                  {failure.entities.disease && (
                    <span className="flex items-center gap-1">
                      <span className="font-medium">Disease:</span>
                      <span>{failure.entities.disease.name}</span>
                    </span>
                  )}
                  {failure.risk_score !== undefined && (
                    <span className="flex items-center gap-1 ml-auto">
                      <span className="font-medium">Risk:</span>
                      <span className={`font-semibold ${
                        failure.risk_category === 'CRITICAL' ? 'text-red-600' :
                        failure.risk_category === 'HIGH' ? 'text-orange-600' :
                        failure.risk_category === 'MODERATE' ? 'text-yellow-600' :
                        'text-green-600'
                      }`}>
                        {failure.risk_score.toFixed(0)} ({failure.risk_category})
                      </span>
                    </span>
                  )}
                </div>
              </div>

              <div className="ml-4">
                <svg
                  className="w-5 h-5 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

