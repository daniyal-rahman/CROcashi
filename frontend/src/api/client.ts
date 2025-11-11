import axios from 'axios'

const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types matching backend models
export interface CompanyRiskProfile {
  company_id: string
  company_name?: string
  risk_score: number
  risk_category: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
  components: {
    failure_rate: ComponentDetails
    recent_failures: ComponentDetails
    pipeline_stagnation: ComponentDetails
    warning_signals: ComponentDetails
  }
  calculated_at: string
}

export interface ComponentDetails {
  score: number
  weight: number
  details: Record<string, any>
}

export interface CompanyMetrics {
  company_id: string
  company_name?: string
  total_trials: number
  active_trials: number
  terminated_count: number
  success_rate_phase_1?: number
  success_rate_phase_2?: number
  success_rate_phase_3?: number
  pipeline_velocity: number
  days_since_last_update?: number
  failure_clustering: Record<string, any>
  calculated_at: string
}

export interface TimelineEvent {
  event_id: string
  event_type: string
  event_date: string
  event_significance: string
  entities_involved: string[]
  event_data?: Record<string, any>
  source_id?: string
  confidence_score?: number
}

export interface CompanyTimelineResponse {
  company_id: string
  events: TimelineEvent[]
  start_date?: string
  end_date?: string
  total_events: number
}

export interface CompanySearchResult {
  company_id: string
  company_name: string
  risk_score: number
  risk_category: string
  total_trials: number
  active_trials: number
  terminated_count: number
}

export interface CompanySearchResponse {
  companies: CompanySearchResult[]
  total: number
  limit: number
  offset: number
}

// API functions
export const companyRiskApi = {
  getRiskProfile: async (companyId: string): Promise<CompanyRiskProfile> => {
    const response = await apiClient.get(`/api/companies/${companyId}/risk-profile`)
    return response.data
  },

  getMetrics: async (companyId: string): Promise<CompanyMetrics> => {
    const response = await apiClient.get(`/api/companies/${companyId}/metrics`)
    return response.data
  },

  getTimeline: async (
    companyId: string,
    startDate?: string,
    endDate?: string,
    eventTypes?: string[]
  ): Promise<CompanyTimelineResponse> => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)
    if (eventTypes) eventTypes.forEach(type => params.append('event_types', type))
    
    const response = await apiClient.get(`/api/companies/${companyId}/timeline?${params}`)
    return response.data
  },

  searchCompanies: async (
    q?: string,
    riskCategory?: string,
    therapeuticArea?: string,
    minPrograms?: number,
    limit: number = 50,
    offset: number = 0
  ): Promise<CompanySearchResponse> => {
    const params = new URLSearchParams()
    if (q) params.append('q', q)
    if (riskCategory) params.append('risk_category', riskCategory)
    if (therapeuticArea) params.append('therapeutic_area', therapeuticArea)
    if (minPrograms) params.append('min_programs', minPrograms.toString())
    params.append('limit', limit.toString())
    params.append('offset', offset.toString())
    
    const response = await apiClient.get(`/api/companies/search?${params}`)
    return response.data
  },
}

