import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import CompanySearchBar from '../components/CompanySearchBar'
import FailedTrialsList from '../components/FailedTrialsList'
import RiskScoreCard from '../components/RiskScoreCard'
import MetricsCards from '../components/MetricsCards'
import TimelineVisualization from '../components/TimelineVisualization'
import { companyRiskApi, CompanyRiskProfile, CompanyMetrics, CompanyTimelineResponse } from '../api/client'
import { exportToPDF } from '../utils/pdfExport'

export default function CompanyRiskDashboard() {
  const { companyId } = useParams<{ companyId?: string }>()
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | undefined>(companyId)
  const [riskProfile, setRiskProfile] = useState<CompanyRiskProfile | null>(null)
  const [metrics, setMetrics] = useState<CompanyMetrics | null>(null)
  const [timeline, setTimeline] = useState<CompanyTimelineResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showDetails, setShowDetails] = useState(false)

  useEffect(() => {
    if (companyId) {
      setSelectedCompanyId(companyId)
      setShowDetails(true)
    }
  }, [companyId])

  useEffect(() => {
    if (selectedCompanyId && showDetails) {
      loadCompanyData(selectedCompanyId)
    } else {
      // Clear data when going back to list
      setRiskProfile(null)
      setMetrics(null)
      setTimeline(null)
      setError(null)
    }
  }, [selectedCompanyId, showDetails])

  const loadCompanyData = async (companyId: string) => {
    setLoading(true)
    setError(null)
    try {
      const [profile, metricsData, timelineData] = await Promise.all([
        companyRiskApi.getRiskProfile(companyId),
        companyRiskApi.getMetrics(companyId),
        companyRiskApi.getTimeline(companyId)
      ])
      setRiskProfile(profile)
      setMetrics(metricsData)
      setTimeline(timelineData)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load company data')
      console.error('Error loading company data:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleSelectCompany = (companyId: string) => {
    setSelectedCompanyId(companyId)
    setShowDetails(true)
  }

  const handleBackToList = () => {
    setShowDetails(false)
    setSelectedCompanyId(undefined)
  }

  const handleExportPDF = () => {
    if (riskProfile && metrics && timeline) {
      exportToPDF(riskProfile, metrics, timeline)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-4">Biotech Risk Dashboard</h1>
          
          {/* Search Bar */}
          <div className="mb-6">
            <CompanySearchBar onSelectCompany={handleSelectCompany} />
          </div>
        </div>

        {/* Show Details View */}
        {showDetails && selectedCompanyId ? (
          <div>
            {/* Back Button */}
            <button
              onClick={handleBackToList}
              className="mb-4 flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 19l-7-7m0 0l7-7m-7 7h18"
                />
              </svg>
              <span>Back to List</span>
            </button>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
                {error}
              </div>
            )}

            {loading && (
              <div className="text-center py-8">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                <div className="mt-2 text-gray-600">Loading company data...</div>
              </div>
            )}

            {!loading && riskProfile && metrics && (
              <>
                <div className="mb-6 flex justify-between items-center">
                  <h2 className="text-2xl font-bold text-gray-800">
                    {riskProfile.company_name || 'Company Details'}
                  </h2>
                  <button
                    onClick={handleExportPDF}
                    className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    Export to PDF
                  </button>
                </div>

                <div className="space-y-6">
                  <RiskScoreCard riskProfile={riskProfile} />
                  <MetricsCards metrics={metrics} />
                  
                  {timeline && (
                    <TimelineVisualization events={timeline.events} />
                  )}
                </div>
              </>
            )}
          </div>
        ) : (
          /* Show Failed Trials List */
          <FailedTrialsList
            onSelectCompany={handleSelectCompany}
            onSelectTrial={(trialId) => {
              // For now, just show a message - can be enhanced later
              console.log('Trial selected:', trialId)
            }}
          />
        )}
      </div>
    </div>
  )
}

