import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { CompanyRiskProfile, CompanyMetrics, CompanyTimelineResponse } from '../api/client'

export function exportToPDF(
  riskProfile: CompanyRiskProfile,
  metrics: CompanyMetrics,
  timeline: CompanyTimelineResponse
) {
  const doc = new jsPDF()
  
  // Title
  doc.setFontSize(20)
  doc.text('Company Risk Profile', 14, 20)
  
  // Company Info
  doc.setFontSize(14)
  doc.text(`Company: ${riskProfile.company_name || 'Unknown'}`, 14, 30)
  const riskScore = riskProfile.risk_score ?? 0
  doc.text(`Risk Score: ${riskScore.toFixed(1)} / 100`, 14, 37)
  doc.text(`Risk Category: ${riskProfile.risk_category || 'UNKNOWN'}`, 14, 44)
  
  // Metrics Table
  autoTable(doc, {
    startY: 50,
    head: [['Metric', 'Value']],
    body: [
      ['Total Trials', metrics.total_trials.toString()],
      ['Active Trials', metrics.active_trials.toString()],
      ['Terminated', metrics.terminated_count.toString()],
      ['Pipeline Velocity', `${metrics.pipeline_velocity.toFixed(1)} programs/year`],
      ['Phase 1 Success', metrics.success_rate_phase_1 ? `${(metrics.success_rate_phase_1 * 100).toFixed(1)}%` : 'N/A'],
      ['Phase 2 Success', metrics.success_rate_phase_2 ? `${(metrics.success_rate_phase_2 * 100).toFixed(1)}%` : 'N/A'],
      ['Phase 3 Success', metrics.success_rate_phase_3 ? `${(metrics.success_rate_phase_3 * 100).toFixed(1)}%` : 'N/A'],
    ],
  })
  
  // Risk Components
  const finalY = (doc as any).lastAutoTable.finalY + 10
  doc.setFontSize(14)
  doc.text('Risk Score Components', 14, finalY)
  
  autoTable(doc, {
    startY: finalY + 5,
    head: [['Component', 'Score', 'Weight']],
    body: [
      ['Failure Rate', riskProfile.components.failure_rate.score.toFixed(1), riskProfile.components.failure_rate.weight.toString()],
      ['Recent Failures', riskProfile.components.recent_failures.score.toFixed(1), riskProfile.components.recent_failures.weight.toString()],
      ['Pipeline Stagnation', riskProfile.components.pipeline_stagnation.score.toFixed(1), riskProfile.components.pipeline_stagnation.weight.toString()],
      ['Warning Signals', riskProfile.components.warning_signals.score.toFixed(1), riskProfile.components.warning_signals.weight.toString()],
    ],
  })
  
  // Timeline Events (first 20)
  const timelineY = (doc as any).lastAutoTable.finalY + 10
  doc.setFontSize(14)
  doc.text('Recent Events', 14, timelineY)
  
  const eventsData = timeline.events.slice(0, 20).map(event => [
    event.event_date,
    event.event_type,
    event.event_significance
  ])
  
  autoTable(doc, {
    startY: timelineY + 5,
    head: [['Date', 'Event Type', 'Significance']],
    body: eventsData,
  })
  
  // Save
  const filename = `${riskProfile.company_name?.replace(/[^a-z0-9]/gi, '_') || 'company'}_risk_profile.pdf`
  doc.save(filename)
}

