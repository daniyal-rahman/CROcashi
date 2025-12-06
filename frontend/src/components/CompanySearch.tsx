import { useState, useEffect } from 'react'
import { companyRiskApi, CompanySearchResult } from '../api/client'

interface CompanySearchProps {
  onSelectCompany: (companyId: string) => void
  selectedCompanyId?: string
}

export default function CompanySearch({ onSelectCompany, selectedCompanyId }: CompanySearchProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState<CompanySearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [riskCategoryFilter, setRiskCategoryFilter] = useState<string>('')
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    if (searchTerm.length > 2) {
      searchCompanies()
    } else {
      setResults([])
    }
  }, [searchTerm, riskCategoryFilter])

  const searchCompanies = async () => {
    setLoading(true)
    try {
      const response = await companyRiskApi.searchCompanies(
        riskCategoryFilter || undefined,
        undefined,
        undefined,
        20
      )
      // Filter by search term client-side
      const filtered = response.companies.filter(company =>
        company.company_name.toLowerCase().includes(searchTerm.toLowerCase())
      )
      setResults(filtered)
    } catch (error) {
      console.error('Error searching companies:', error)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const getRiskColor = (category: string) => {
    switch (category) {
      case 'LOW': return 'text-risk-low'
      case 'MODERATE': return 'text-risk-moderate'
      case 'HIGH': return 'text-risk-high'
      case 'CRITICAL': return 'text-risk-critical'
      default: return 'text-gray-600'
    }
  }

  return (
    <div className="w-full mb-6">
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          placeholder="Search companies..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg"
        >
          Filters
        </button>
      </div>

      {showFilters && (
        <div className="mb-2 p-3 bg-gray-50 rounded-lg">
          <label className="block text-sm font-medium mb-1">Risk Category</label>
          <select
            value={riskCategoryFilter}
            onChange={(e) => setRiskCategoryFilter(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded"
          >
            <option value="">All</option>
            <option value="LOW">Low</option>
            <option value="MODERATE">Moderate</option>
            <option value="HIGH">High</option>
            <option value="CRITICAL">Critical</option>
          </select>
        </div>
      )}

      {loading && <div className="text-center py-4">Loading...</div>}

      {!loading && results.length > 0 && (
        <div className="border border-gray-200 rounded-lg max-h-64 overflow-y-auto">
          {results.map((company) => (
            <div
              key={company.company_id}
              onClick={() => onSelectCompany(company.company_id)}
              className={`p-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0 ${
                selectedCompanyId === company.company_id ? 'bg-blue-50' : ''
              }`}
            >
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium">{company.company_name}</div>
                  <div className="text-sm text-gray-500">
                    {company.total_trials} trials • {company.active_trials} active
                  </div>
                </div>
                <div className="text-right">
                  <div className={`font-bold ${getRiskColor(company.risk_category)}`}>
                    {company.risk_score.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500">{company.risk_category}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

