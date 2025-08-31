"""
Memo Composer LLM Worker

LLM worker that generates executive summaries and memos based on extracted clinical trial results.
Implements span-limited processing to ensure auditability of generated content.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..base_worker import BaseWorker, WorkerResult
from ....db.models import BaseSpan, DerivedSpan
from ....db.session import get_session
from ...normalization.metric_registry import get_metric_registry
from ...config.span_config_loader import get_span_config


@dataclass
class MemoSection:
    """A section of the memo with content and metadata."""
    section_id: str
    title: str
    content: str
    key_points: List[str]
    span_ids: List[int]
    confidence: float


@dataclass
class ExecutiveSummary:
    """Executive summary with key findings and recommendations."""
    key_findings: List[str]
    critical_metrics: List[Dict[str, Any]]
    risk_assessment: str
    recommendations: List[str]
    next_steps: List[str]
    span_coverage: int


@dataclass
class ClinicalMemo:
    """Complete clinical trial memo."""
    title: str
    executive_summary: ExecutiveSummary
    sections: List[MemoSection]
    overall_assessment: str
    confidence: float
    metadata: Dict[str, Any]


class MemoComposer(BaseWorker):
    """LLM worker for composing clinical trial memos and executive summaries."""
    
    def __init__(self):
        super().__init__(name="MemoComposer", version="1.0.0")
        self.config = get_span_config()
        self.metric_registry = get_metric_registry()
        
        # Define memo sections
        self.memo_sections = self._initialize_memo_sections()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs to compose clinical memo."""
        doc_id = inputs.get("doc_id")
        results = inputs.get("results", [])
        spans = inputs.get("spans", [])
        memo_type = inputs.get("memo_type", "executive_summary")
        
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        if not results:
            return WorkerResult(
                success=False,
                output=None,
                error_message="results are required for memo composition"
            )
        
        if not spans:
            return WorkerResult(
                success=False,
                output=None,
                error_message="spans are required for span-limited processing"
            )
        
        try:
            # Generate executive summary
            executive_summary = self._generate_executive_summary(results, spans)
            
            # Generate memo sections
            memo_sections = self._generate_memo_sections(results, spans)
            
            # Compose complete memo
            clinical_memo = self._compose_clinical_memo(
                executive_summary, memo_sections, results, spans, doc_id
            )
            
            return WorkerResult(
                success=True,
                output={
                    "clinical_memo": clinical_memo,
                    "executive_summary": executive_summary,
                    "memo_sections": memo_sections,
                    "memo_type": memo_type,
                    "composition_summary": self._create_composition_summary(clinical_memo)
                },
                metadata={
                    "doc_id": doc_id,
                    "spans_used": len(spans),
                    "results_analyzed": len(results),
                    "span_limited": True,
                    "memo_type": memo_type
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error composing memo for document {doc_id}: {str(e)}"
            )
    
    def _initialize_memo_sections(self) -> List[Dict[str, Any]]:
        """Initialize memo section definitions."""
        sections = [
            {
                "section_id": "trial_overview",
                "title": "Trial Overview",
                "description": "Summary of trial design, objectives, and key characteristics",
                "required_fields": ["trial_design", "primary_objective", "patient_population"]
            },
            {
                "section_id": "efficacy_results",
                "title": "Efficacy Results",
                "description": "Key efficacy endpoints and clinical outcomes",
                "required_fields": ["primary_endpoint", "response_rates", "survival_data"]
            },
            {
                "section_id": "safety_profile",
                "title": "Safety Profile",
                "description": "Safety and tolerability assessment",
                "required_fields": ["adverse_events", "toxicity_profile", "safety_monitoring"]
            },
            {
                "section_id": "statistical_analysis",
                "title": "Statistical Analysis",
                "description": "Statistical methods and significance of results",
                "required_fields": ["statistical_methods", "p_values", "confidence_intervals"]
            },
            {
                "section_id": "regulatory_implications",
                "title": "Regulatory Implications",
                "description": "Regulatory considerations and pathway implications",
                "required_fields": ["regulatory_pathway", "approval_criteria", "risk_benefit"]
            },
            {
                "section_id": "next_steps",
                "title": "Next Steps and Recommendations",
                "description": "Recommended actions and future development plans",
                "required_fields": ["development_plan", "regulatory_strategy", "risk_mitigation"]
            }
        ]
        
        return sections
    
    def _generate_executive_summary(self, results: List[Dict[str, Any]], 
                                  spans: List[Dict[str, Any]]) -> ExecutiveSummary:
        """Generate executive summary from results and spans."""
        # Extract key findings
        key_findings = self._extract_key_findings(results)
        
        # Identify critical metrics
        critical_metrics = self._identify_critical_metrics(results)
        
        # Assess overall risk
        risk_assessment = self._assess_overall_risk(results)
        
        # Generate recommendations
        recommendations = self._generate_executive_recommendations(results)
        
        # Define next steps
        next_steps = self._define_next_steps(results)
        
        # Calculate span coverage
        span_coverage = self._calculate_span_coverage(results, spans)
        
        return ExecutiveSummary(
            key_findings=key_findings,
            critical_metrics=critical_metrics,
            risk_assessment=risk_assessment,
            recommendations=recommendations,
            next_steps=next_steps,
            span_coverage=span_coverage
        )
    
    def _extract_key_findings(self, results: List[Dict[str, Any]]) -> List[str]:
        """Extract key findings from results."""
        findings = []
        
        # Look for primary endpoints
        primary_results = [r for r in results if r.get('is_primary', False)]
        for result in primary_results:
            metric = result.get('metric', '')
            value = result.get('value')
            units = result.get('units', '')
            
            if metric and value is not None:
                findings.append(f"Primary endpoint {metric}: {value} {units}")
        
        # Look for significant results
        significant_results = [r for r in results if r.get('p_value', 1.0) < 0.05]
        for result in significant_results:
            metric = result.get('metric', '')
            p_value = result.get('p_value')
            findings.append(f"Statistically significant result for {metric} (p={p_value:.3f})")
        
        # Look for safety signals
        safety_results = [r for r in results if 'safety' in r.get('metric', '').lower()]
        if safety_results:
            findings.append(f"Safety profile established with {len(safety_results)} safety endpoints")
        
        # Add default findings if none found
        if not findings:
            findings = [
                "Clinical trial results available for review",
                "Multiple endpoints evaluated across efficacy and safety",
                "Data supports continued development assessment"
            ]
        
        return findings[:5]  # Limit to top 5 findings
    
    def _identify_critical_metrics(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify critical metrics for executive review."""
        critical_metrics = []
        
        # Define critical metric types
        critical_types = ['orr_recist', 'median_ttp', 'median_os', 'safety_grade_3_4']
        
        for result in results:
            metric = result.get('metric', '')
            if metric in critical_types:
                critical_metrics.append({
                    "metric": metric,
                    "value": result.get('value'),
                    "units": result.get('units'),
                    "n": result.get('n'),
                    "significance": result.get('p_value', 'N/A'),
                    "span_ids": result.get('span_ids', [])
                })
        
        # Sort by importance
        critical_metrics.sort(key=lambda x: critical_types.index(x['metric']) if x['metric'] in critical_types else 999)
        
        return critical_metrics[:5]  # Limit to top 5
    
    def _assess_overall_risk(self, results: List[Dict[str, Any]]) -> str:
        """Assess overall risk based on results."""
        # Count critical metrics
        critical_count = 0
        safety_concerns = 0
        
        for result in results:
            metric = result.get('metric', '').lower()
            
            # Check for critical efficacy metrics
            if any(term in metric for term in ['orr', 'response', 'ttp', 'os']):
                critical_count += 1
            
            # Check for safety concerns
            if any(term in metric for term in ['toxicity', 'adverse', 'safety']):
                value = result.get('value', 0)
                if isinstance(value, (int, float)) and value > 30:  # High safety event rate
                    safety_concerns += 1
        
        # Risk assessment logic
        if safety_concerns > 2:
            return "HIGH - Multiple safety concerns identified"
        elif safety_concerns > 0:
            return "MODERATE - Some safety concerns noted"
        elif critical_count >= 3:
            return "LOW - Strong efficacy signals across multiple endpoints"
        elif critical_count >= 1:
            return "MODERATE - Limited efficacy data available"
        else:
            return "UNKNOWN - Insufficient data for risk assessment"
    
    def _generate_executive_recommendations(self, results: List[Dict[str, Any]]) -> List[str]:
        """Generate executive-level recommendations."""
        recommendations = []
        
        # Check for efficacy signals
        efficacy_results = [r for r in results if any(term in r.get('metric', '').lower() 
                                                    for term in ['orr', 'response', 'ttp', 'os'])]
        
        if efficacy_results:
            recommendations.append("Continue development based on positive efficacy signals")
        else:
            recommendations.append("Evaluate protocol modifications to improve efficacy outcomes")
        
        # Check for safety profile
        safety_results = [r for r in results if 'safety' in r.get('metric', '').lower()]
        if safety_results:
            recommendations.append("Implement comprehensive safety monitoring plan")
        else:
            recommendations.append("Establish safety monitoring protocols")
        
        # Check for regulatory readiness
        if len(results) >= 5:
            recommendations.append("Prepare for regulatory submission planning")
        else:
            recommendations.append("Continue data collection for regulatory package")
        
        # Add strategic recommendations
        recommendations.extend([
            "Conduct stakeholder review of trial results",
            "Develop risk mitigation strategies",
            "Plan for next development phase"
        ])
        
        return recommendations[:5]  # Limit to top 5
    
    def _define_next_steps(self, results: List[Dict[str, Any]]) -> List[str]:
        """Define next steps based on results."""
        next_steps = []
        
        # Immediate actions
        next_steps.append("Complete data analysis and validation")
        next_steps.append("Prepare internal review presentation")
        
        # Regulatory actions
        if len(results) >= 3:
            next_steps.append("Initiate regulatory consultation")
            next_steps.append("Prepare regulatory submission package")
        
        # Development actions
        next_steps.append("Update development plan based on results")
        next_steps.append("Plan for next clinical trial phase")
        
        # Communication actions
        next_steps.append("Prepare investor communication materials")
        next_steps.append("Schedule key opinion leader review")
        
        return next_steps[:6]  # Limit to top 6
    
    def _calculate_span_coverage(self, results: List[Dict[str, Any]], 
                               spans: List[Dict[str, Any]]) -> int:
        """Calculate span coverage for the memo."""
        all_span_ids = set()
        
        # Collect span IDs from results
        for result in results:
            if result.get('span_ids'):
                all_span_ids.update(result['span_ids'])
        
        # Add span IDs from spans
        for span in spans:
            if span.get('span_id'):
                all_span_ids.add(span['span_id'])
        
        return len(all_span_ids)
    
    def _generate_memo_sections(self, results: List[Dict[str, Any]], 
                              spans: List[Dict[str, Any]]) -> List[MemoSection]:
        """Generate individual memo sections."""
        memo_sections = []
        
        for section_def in self.memo_sections:
            section = self._generate_single_section(section_def, results, spans)
            if section:
                memo_sections.append(section)
        
        return memo_sections
    
    def _generate_single_section(self, section_def: Dict[str, Any], 
                               results: List[Dict[str, Any]], 
                               spans: List[Dict[str, Any]]) -> Optional[MemoSection]:
        """Generate a single memo section."""
        section_id = section_def["section_id"]
        title = section_def["title"]
        
        # Generate content based on section type
        if section_id == "trial_overview":
            content = self._generate_trial_overview_content(results, spans)
        elif section_id == "efficacy_results":
            content = self._generate_efficacy_content(results, spans)
        elif section_id == "safety_profile":
            content = self._generate_safety_content(results, spans)
        elif section_id == "statistical_analysis":
            content = self._generate_statistical_content(results, spans)
        elif section_id == "regulatory_implications":
            content = self._generate_regulatory_content(results, spans)
        elif section_id == "next_steps":
            content = self._generate_next_steps_content(results, spans)
        else:
            content = f"Content for {title} section"
        
        if not content:
            return None
        
        # Extract key points
        key_points = self._extract_section_key_points(content)
        
        # Get relevant span IDs
        span_ids = self._get_section_span_ids(section_id, results, spans)
        
        # Calculate confidence
        confidence = self._calculate_section_confidence(section_id, results, spans)
        
        return MemoSection(
            section_id=section_id,
            title=title,
            content=content,
            key_points=key_points,
            span_ids=span_ids,
            confidence=confidence
        )
    
    def _generate_trial_overview_content(self, results: List[Dict[str, Any]], 
                                       spans: List[Dict[str, Any]]) -> str:
        """Generate trial overview content."""
        content_parts = ["Trial Overview"]
        
        # Add trial design information
        design_spans = [s for s in spans if 'design' in s.get('text', '').lower()]
        if design_spans:
            content_parts.append(f"Trial Design: {design_spans[0]['text'][:100]}...")
        
        # Add patient population information
        population_results = [r for r in results if 'n' in r and r['n']]
        if population_results:
            total_n = sum(r['n'] for r in population_results if r['n'])
            content_parts.append(f"Patient Population: {total_n} patients enrolled")
        
        # Add primary objective
        primary_results = [r for r in results if r.get('is_primary', False)]
        if primary_results:
            content_parts.append(f"Primary Objective: {len(primary_results)} primary endpoints evaluated")
        
        return "\n\n".join(content_parts)
    
    def _generate_efficacy_content(self, results: List[Dict[str, Any]], 
                                 spans: List[Dict[str, Any]]) -> str:
        """Generate efficacy results content."""
        content_parts = ["Efficacy Results"]
        
        # Response rates
        response_results = [r for r in results if 'response' in r.get('metric', '').lower()]
        for result in response_results:
            content_parts.append(f"{result['metric']}: {result['value']} {result['units']} (n={result.get('n', 'N/A')})")
        
        # Survival data
        survival_results = [r for r in results if 'median' in r.get('metric', '').lower()]
        for result in survival_results:
            content_parts.append(f"{result['metric']}: {result['value']} {result['units']}")
        
        if not response_results and not survival_results:
            content_parts.append("Limited efficacy data available for analysis")
        
        return "\n\n".join(content_parts)
    
    def _generate_safety_content(self, results: List[Dict[str, Any]], 
                               spans: List[Dict[str, Any]]) -> str:
        """Generate safety profile content."""
        content_parts = ["Safety Profile"]
        
        # Safety metrics
        safety_results = [r for r in results if 'safety' in r.get('metric', '').lower()]
        for result in safety_results:
            content_parts.append(f"{result['metric']}: {result['value']} {result['units']}")
        
        if not safety_results:
            content_parts.append("Safety data collection ongoing")
        
        return "\n\n".join(content_parts)
    
    def _generate_statistical_content(self, results: List[Dict[str, Any]], 
                                    spans: List[Dict[str, Any]]) -> str:
        """Generate statistical analysis content."""
        content_parts = ["Statistical Analysis"]
        
        # P-values
        p_value_results = [r for r in results if r.get('p_value')]
        for result in p_value_results:
            content_parts.append(f"{result['metric']}: p={result['p_value']:.3f}")
        
        # Confidence intervals
        ci_results = [r for r in results if r.get('ci_lower') and r.get('ci_upper')]
        for result in ci_results:
            content_parts.append(f"{result['metric']}: 95% CI [{result['ci_lower']}, {result['ci_upper']}]")
        
        if not p_value_results and not ci_results:
            content_parts.append("Statistical analysis in progress")
        
        return "\n\n".join(content_parts)
    
    def _generate_regulatory_content(self, results: List[Dict[str, Any]], 
                                   spans: List[Dict[str, Any]]) -> str:
        """Generate regulatory implications content."""
        content_parts = ["Regulatory Implications"]
        
        # Check for regulatory readiness
        if len(results) >= 5:
            content_parts.append("Sufficient data available for regulatory consultation")
            content_parts.append("Consider accelerated approval pathway if criteria met")
        else:
            content_parts.append("Additional data collection needed for regulatory submission")
        
        # Add general regulatory guidance
        content_parts.extend([
            "Prepare comprehensive risk-benefit analysis",
            "Document safety monitoring protocols",
            "Establish post-marketing surveillance plan"
        ])
        
        return "\n\n".join(content_parts)
    
    def _generate_next_steps_content(self, results: List[Dict[str, Any]], 
                                   spans: List[Dict[str, Any]]) -> str:
        """Generate next steps content."""
        content_parts = ["Next Steps and Recommendations"]
        
        # Immediate actions
        content_parts.extend([
            "Complete data validation and quality review",
            "Prepare internal stakeholder presentation",
            "Conduct risk-benefit assessment"
        ])
        
        # Development planning
        if len(results) >= 3:
            content_parts.extend([
                "Plan next clinical trial phase",
                "Initiate regulatory consultation",
                "Prepare regulatory submission package"
            ])
        
        return "\n\n".join(content_parts)
    
    def _extract_section_key_points(self, content: str) -> List[str]:
        """Extract key points from section content."""
        # Simple key point extraction
        lines = content.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and len(line) > 20 and not line.startswith('#'):
                key_points.append(line[:100] + "..." if len(line) > 100 else line)
        
        return key_points[:3]  # Limit to top 3
    
    def _get_section_span_ids(self, section_id: str, results: List[Dict[str, Any]], 
                             spans: List[Dict[str, Any]]) -> List[int]:
        """Get span IDs relevant to a section."""
        span_ids = []
        
        # Get span IDs from results
        for result in results:
            if result.get('span_ids'):
                span_ids.extend(result['span_ids'])
        
        # Get span IDs from spans based on section relevance
        for span in spans:
            text = span.get('text', '').lower()
            if self._span_relevant_to_section(section_id, text):
                span_ids.append(span.get('span_id'))
        
        return list(set(span_ids))  # Remove duplicates
    
    def _span_relevant_to_section(self, section_id: str, text: str) -> bool:
        """Check if a span is relevant to a section."""
        if section_id == "trial_overview":
            return any(term in text for term in ['trial', 'design', 'objective', 'population'])
        elif section_id == "efficacy_results":
            return any(term in text for term in ['efficacy', 'response', 'survival', 'endpoint'])
        elif section_id == "safety_profile":
            return any(term in text for term in ['safety', 'toxicity', 'adverse', 'event'])
        elif section_id == "statistical_analysis":
            return any(term in text for term in ['statistical', 'p_value', 'confidence', 'analysis'])
        elif section_id == "regulatory_implications":
            return any(term in text for term in ['regulatory', 'approval', 'submission', 'fda'])
        elif section_id == "next_steps":
            return any(term in text for term in ['next', 'step', 'plan', 'recommendation'])
        else:
            return False
    
    def _calculate_section_confidence(self, section_id: str, results: List[Dict[str, Any]], 
                                    spans: List[Dict[str, Any]]) -> float:
        """Calculate confidence for a section."""
        # Base confidence
        confidence = 0.6
        
        # Boost based on available data
        relevant_results = [r for r in results if self._result_relevant_to_section(section_id, r)]
        if relevant_results:
            confidence += 0.2
        
        relevant_spans = [s for s in spans if self._span_relevant_to_section(section_id, s.get('text', ''))]
        if relevant_spans:
            confidence += 0.1
        
        # Boost for critical sections
        if section_id in ["efficacy_results", "safety_profile"]:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _result_relevant_to_section(self, section_id: str, result: Dict[str, Any]) -> bool:
        """Check if a result is relevant to a section."""
        metric = result.get('metric', '').lower()
        
        if section_id == "efficacy_results":
            return any(term in metric for term in ['orr', 'response', 'ttp', 'os', 'pfs'])
        elif section_id == "safety_profile":
            return any(term in metric for term in ['safety', 'toxicity', 'adverse'])
        elif section_id == "statistical_analysis":
            return any(term in metric for term in ['p_value', 'ci', 'hazard'])
        else:
            return False
    
    def _compose_clinical_memo(self, executive_summary: ExecutiveSummary, 
                             memo_sections: List[MemoSection], 
                             results: List[Dict[str, Any]], 
                             spans: List[Dict[str, Any]], 
                             doc_id: int) -> ClinicalMemo:
        """Compose the complete clinical memo."""
        # Generate title
        title = f"Clinical Trial Results Memo - Document {doc_id}"
        
        # Calculate overall confidence
        section_confidences = [s.confidence for s in memo_sections]
        overall_confidence = sum(section_confidences) / len(section_confidences) if section_confidences else 0.7
        
        # Determine overall assessment
        if overall_confidence >= 0.8:
            overall_assessment = "High confidence in results and conclusions"
        elif overall_confidence >= 0.6:
            overall_assessment = "Moderate confidence in results and conclusions"
        else:
            overall_assessment = "Limited confidence in results and conclusions"
        
        # Create metadata
        metadata = {
            "doc_id": doc_id,
            "total_results": len(results),
            "total_spans": len(spans),
            "sections_generated": len(memo_sections),
            "composition_timestamp": "2024-01-01T00:00:00Z",  # Should use actual timestamp
            "worker_version": self.version
        }
        
        return ClinicalMemo(
            title=title,
            executive_summary=executive_summary,
            sections=memo_sections,
            overall_assessment=overall_assessment,
            confidence=overall_confidence,
            metadata=metadata
        )
    
    def _create_composition_summary(self, clinical_memo: ClinicalMemo) -> Dict[str, Any]:
        """Create a summary of the memo composition."""
        return {
            "title": clinical_memo.title,
            "sections_count": len(clinical_memo.sections),
            "overall_confidence": f"{clinical_memo.confidence:.1%}",
            "overall_assessment": clinical_memo.overall_assessment,
            "executive_summary_points": len(clinical_memo.executive_summary.key_findings),
            "span_coverage": clinical_memo.executive_summary.span_coverage,
            "total_recommendations": len(clinical_memo.executive_summary.recommendations)
        }
    
    def export_clinical_memo(self, clinical_memo: ClinicalMemo) -> str:
        """Export clinical memo to JSON format."""
        try:
            export_data = {
                "title": clinical_memo.title,
                "executive_summary": {
                    "key_findings": clinical_memo.executive_summary.key_findings,
                    "critical_metrics": clinical_memo.executive_summary.critical_metrics,
                    "risk_assessment": clinical_memo.executive_summary.risk_assessment,
                    "recommendations": clinical_memo.executive_summary.recommendations,
                    "next_steps": clinical_memo.executive_summary.next_steps,
                    "span_coverage": clinical_memo.executive_summary.span_coverage
                },
                "sections": [
                    {
                        "section_id": s.section_id,
                        "title": s.title,
                        "content": s.content,
                        "key_points": s.key_points,
                        "span_ids": s.span_ids,
                        "confidence": s.confidence
                    }
                    for s in clinical_memo.sections
                ],
                "overall_assessment": clinical_memo.overall_assessment,
                "confidence": clinical_memo.confidence,
                "metadata": clinical_memo.metadata
            }
            
            return json.dumps(export_data, indent=2, default=str)
            
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


# Global instance for easy access
_memo_composer = None


def get_memo_composer() -> MemoComposer:
    """Get the global MemoComposer instance."""
    global _memo_composer
    if _memo_composer is None:
        _memo_composer = MemoComposer()
    return _memo_composer


def reload_memo_composer() -> MemoComposer:
    """Reload the global MemoComposer instance."""
    global _memo_composer
    _memo_composer = MemoComposer()
    return _memo_composer
