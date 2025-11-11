import { useState, useEffect } from 'react'
import { companyRiskApi, CompanySearchResult } from '../api/client'

interface CompanySearchBarProps {
  onSelectCompany: (companyId: string) => void
  placeholder?: string
}

export default function CompanySearchBar({ onSelectCompany, placeholder = "Search companies..." }: CompanySearchBarProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CompanySearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [showResults, setShowResults] = useState(false)

  useEffect(() => {
    if (query.length >= 2) {
      const timeoutId = setTimeout(() => {
        searchCompanies()
      }, 300)
      return () => clearTimeout(timeoutId)
    } else {
      setResults([])
      setShowResults(false)
    }
  }, [query])

  const searchCompanies = async () => {
    setLoading(true)
    try {
      const response = await companyRiskApi.searchCompanies(
        query, // q - company name search
        undefined, // risk_category
        undefined, // therapeutic_area
        undefined, // min_programs
        10, // limit
        0 // offset
      )
      
      setResults(response.companies)
      setShowResults(true)
    } catch (err: any) {
      console.error('Search error:', err)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = (company: CompanySearchResult) => {
    onSelectCompany(company.company_id)
    setQuery('')
    setShowResults(false)
  }

  const getRiskColor = (category: string) => {
    const colors: Record<string, string> = {
      'LOW': 'bg-green-100 text-green-800',
      'MODERATE': 'bg-yellow-100 text-yellow-800',
      'HIGH': 'bg-orange-100 text-orange-800',
      'CRITICAL': 'bg-red-100 text-red-800'
    }
    return colors[category] || 'bg-gray-100 text-gray-800'
  }

  return (
    <div className="relative w-full">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => query.length >= 2 && setShowResults(true)}
          placeholder={placeholder}
          className="w-full px-4 py-3 pl-10 pr-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        />
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <svg
            className="h-5 w-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
        {loading && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
          </div>
        )}
      </div>

      {showResults && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-96 overflow-y-auto">
          {results.map((company) => (
            <div
              key={company.company_id}
              onClick={() => handleSelect(company)}
              className="px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="font-semibold text-gray-900">{company.company_name}</div>
                  <div className="text-sm text-gray-600 mt-1">
                    {company.total_trials} trials • {company.active_trials} active • {company.terminated_count} terminated
                  </div>
                </div>
                <div className="ml-4 flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-semibold ${getRiskColor(company.risk_category)}`}>
                    {company.risk_category}
                  </span>
                  <span className="text-sm font-medium text-gray-700">
                    {company.risk_score.toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showResults && query.length >= 2 && results.length === 0 && !loading && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg p-4 text-center text-gray-500">
          No companies found
        </div>
      )}
    </div>
  )
}

