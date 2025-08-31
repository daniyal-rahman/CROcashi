"""
FDA Lens LLM Worker

LLM worker that provides FDA regulatory insights and compliance analysis for clinical trial results.
Implements span-limited processing to ensure auditability of regulatory assessments.
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
class RegulatoryRequirement:
    """A regulatory requirement for clinical trials."""
    requirement_id: str
    category: str  # 'efficacy', 'safety', 'quality', 'statistical'
    description: str
    fda_guidance: str
    criticality: str  # 'critical', 'important', 'supporting'
    evidence_required: List[str]


@dataclass
class RegulatoryAssessment:
    """Assessment of regulatory compliance."""
    requirement_id: str
    status: str  # 'compliant', 'non_compliant', 'insufficient_data'
    confidence: float
    evidence: List[str]
    gaps: List[str]
    recommendations: List[str]
    span_ids: List[int]


@dataclass
class FDARegulatoryReport:
    """Complete FDA regulatory assessment report."""
    overall_compliance: str  # 'compliant', 'conditional', 'non_compliant'
    confidence: float
    critical_issues: List[str]
    important_issues: List[str]
    supporting_evidence: List[str]
    regulatory_assessments: List[RegulatoryAssessment]
    summary_recommendations: List[str]
    span_coverage: int


class FdaLens(BaseWorker):
    """LLM worker for FDA regulatory insights and compliance analysis."""
    
    def __init__(self):
        super().__init__(name="FdaLens", version="1.0.0")
        self.config = get_span_config()
        self.metric_registry = get_metric_registry()
        
        # Define FDA regulatory requirements
        self.regulatory_requirements = self._initialize_regulatory_requirements()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs for FDA regulatory analysis."""
        doc_id = inputs.get("doc_id")
        results = inputs.get("results", [])
        spans = inputs.get("spans", [])
        
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
                error_message="results are required for regulatory analysis"
            )
        
        if not spans:
            return WorkerResult(
                success=False,
                output=None,
                error_message="spans are required for span-limited processing"
            )
        
        try:
            # Assess regulatory compliance
            regulatory_assessments = self._assess_regulatory_compliance(results, spans)
            
            # Generate regulatory report
            regulatory_report = self._generate_regulatory_report(regulatory_assessments, spans)
            
            # Identify critical issues
            critical_issues = self._identify_critical_issues(regulatory_assessments)
            
            return WorkerResult(
                success=True,
                output={
                    "regulatory_report": regulatory_report,
                    "regulatory_assessments": regulatory_assessments,
                    "critical_issues": critical_issues,
                    "compliance_summary": self._create_compliance_summary(regulatory_report),
                    "fda_guidance_references": self._get_fda_guidance_references()
                },
                metadata={
                    "doc_id": doc_id,
                    "spans_used": len(spans),
                    "results_analyzed": len(results),
                    "span_limited": True,
                    "regulatory_framework": "FDA"
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error performing FDA regulatory analysis for document {doc_id}: {str(e)}"
            )
    
    def _initialize_regulatory_requirements(self) -> List[RegulatoryRequirement]:
        """Initialize FDA regulatory requirements for oncology trials."""
        requirements = [
            # Efficacy requirements
            RegulatoryRequirement(
                requirement_id="efficacy_primary_endpoint",
                category="efficacy",
                description="Primary endpoint must be clinically meaningful and statistically significant",
                fda_guidance="FDA Guidance on Clinical Trial Endpoints for Approval of Cancer Drugs",
                criticality="critical",
                evidence_required=["primary_endpoint_definition", "statistical_analysis", "clinical_significance"]
            ),
            
            RegulatoryRequirement(
                requirement_id="efficacy_response_rate",
                category="efficacy",
                description="Response rate must meet predefined criteria for accelerated approval",
                fda_guidance="FDA Guidance on Accelerated Approval for Cancer Drugs",
                criticality="critical",
                evidence_required=["response_criteria", "response_rate", "duration_of_response"]
            ),
            
            RegulatoryRequirement(
                requirement_id="efficacy_survival_endpoints",
                category="efficacy",
                description="Survival endpoints must demonstrate clinical benefit",
                fda_guidance="FDA Guidance on Clinical Trial Endpoints for Approval of Cancer Drugs",
                criticality="important",
                evidence_required=["survival_analysis", "median_values", "hazard_ratios"]
            ),
            
            # Safety requirements
            RegulatoryRequirement(
                requirement_id="safety_profile",
                category="safety",
                description="Safety profile must be acceptable for the intended population",
                fda_guidance="FDA Guidance on Safety Assessment for Cancer Drugs",
                criticality="critical",
                evidence_required=["adverse_events", "dose_limiting_toxicities", "safety_monitoring"]
            ),
            
            RegulatoryRequirement(
                requirement_id="safety_monitoring",
                category="safety",
                description="Comprehensive safety monitoring must be in place",
                fda_guidance="FDA Guidance on Safety Assessment for Cancer Drugs",
                criticality="important",
                evidence_required=["safety_committee", "adverse_event_reporting", "risk_management"]
            ),
            
            # Quality requirements
            RegulatoryRequirement(
                requirement_id="data_quality",
                category="quality",
                description="Data must meet quality standards for regulatory submission",
                fda_guidance="FDA Guidance on Data Quality for Clinical Trials",
                criticality="important",
                evidence_required=["data_validation", "source_documentation", "audit_trail"]
            ),
            
            RegulatoryRequirement(
                requirement_id="statistical_analysis",
                category="statistical",
                description="Statistical analysis must be appropriate and well-documented",
                fda_guidance="FDA Guidance on Statistical Considerations for Clinical Trials",
                criticality="important",
                evidence_required=["statistical_methods", "sample_size_justification", "interim_analyses"]
            )
        ]
        
        return requirements
    
    def _assess_regulatory_compliance(self, results: List[Dict[str, Any]], 
                                    spans: List[Dict[str, Any]]) -> List[RegulatoryAssessment]:
        """Assess compliance with regulatory requirements."""
        assessments = []
        
        for requirement in self.regulatory_requirements:
            assessment = self._assess_single_requirement(requirement, results, spans)
            assessments.append(assessment)
        
        return assessments
    
    def _assess_single_requirement(self, requirement: RegulatoryRequirement, 
                                 results: List[Dict[str, Any]], 
                                 spans: List[Dict[str, Any]]) -> RegulatoryAssessment:
        """Assess compliance with a single regulatory requirement."""
        evidence = []
        gaps = []
        span_ids = []
        
        # Check for required evidence
        for evidence_type in requirement.evidence_required:
            found_evidence = self._find_evidence_for_requirement(evidence_type, results, spans)
            if found_evidence:
                evidence.extend(found_evidence["texts"])
                span_ids.extend(found_evidence["span_ids"])
            else:
                gaps.append(f"Missing evidence for {evidence_type}")
        
        # Determine compliance status
        if len(gaps) == 0:
            status = "compliant"
            confidence = 0.9
        elif len(gaps) <= len(requirement.evidence_required) // 2:
            status = "conditional"
            confidence = 0.7
        else:
            status = "non_compliant"
            confidence = 0.5
        
        # Generate recommendations
        recommendations = self._generate_regulatory_recommendations(requirement, gaps)
        
        return RegulatoryAssessment(
            requirement_id=requirement.requirement_id,
            status=status,
            confidence=confidence,
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
            span_ids=list(set(span_ids))  # Remove duplicates
        )
    
    def _find_evidence_for_requirement(self, evidence_type: str, 
                                     results: List[Dict[str, Any]], 
                                     spans: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find evidence for a specific requirement type."""
        evidence_texts = []
        evidence_span_ids = []
        
        # Search in results
        for result in results:
            if self._result_matches_evidence_type(result, evidence_type):
                evidence_texts.append(f"{result['metric']}: {result['value']} {result['units']}")
                if result.get('span_ids'):
                    evidence_span_ids.extend(result['span_ids'])
        
        # Search in spans for additional context
        for span in spans:
            if self._span_matches_evidence_type(span, evidence_type):
                evidence_texts.append(span.get('text', '')[:100] + "...")
                evidence_span_ids.append(span.get('span_id'))
        
        if evidence_texts:
            return {
                "texts": evidence_texts,
                "span_ids": evidence_span_ids
            }
        
        return None
    
    def _result_matches_evidence_type(self, result: Dict[str, Any], evidence_type: str) -> bool:
        """Check if a result matches the evidence type."""
        metric = result.get('metric', '').lower()
        
        if evidence_type == "response_rate":
            return any(term in metric for term in ['orr', 'response', 'ca125'])
        elif evidence_type == "survival_analysis":
            return any(term in metric for term in ['median', 'ttp', 'os', 'pfs'])
        elif evidence_type == "adverse_events":
            return any(term in metric for term in ['toxicity', 'adverse', 'safety'])
        elif evidence_type == "statistical_methods":
            return any(term in metric for term in ['p_value', 'ci', 'hazard'])
        else:
            return False
    
    def _span_matches_evidence_type(self, span: Dict[str, Any], evidence_type: str) -> bool:
        """Check if a span matches the evidence type."""
        text = span.get('text', '').lower()
        
        if evidence_type == "primary_endpoint_definition":
            return any(term in text for term in ['primary endpoint', 'primary objective', 'primary outcome'])
        elif evidence_type == "response_criteria":
            return any(term in text for term in ['recist', 'response criteria', 'response assessment'])
        elif evidence_type == "safety_monitoring":
            return any(term in text for term in ['safety committee', 'data monitoring', 'adverse event'])
        elif evidence_type == "statistical_methods":
            return any(term in text for term in ['kaplan-meier', 'log-rank', 'cox regression', 'interim analysis'])
        else:
            return False
    
    def _generate_regulatory_recommendations(self, requirement: RegulatoryRequirement, 
                                          gaps: List[str]) -> List[str]:
        """Generate recommendations for regulatory compliance."""
        recommendations = []
        
        for gap in gaps:
            if "response_rate" in gap.lower():
                recommendations.append("Implement standardized response assessment criteria (RECIST v1.1)")
            elif "survival_analysis" in gap.lower():
                recommendations.append("Plan for survival endpoint analysis with adequate follow-up")
            elif "safety_monitoring" in gap.lower():
                recommendations.append("Establish independent data monitoring committee")
            elif "statistical_methods" in gap.lower():
                recommendations.append("Document statistical analysis plan and sample size justification")
            elif "data_quality" in gap.lower():
                recommendations.append("Implement comprehensive data validation and quality control")
            else:
                recommendations.append(f"Address missing evidence for {gap}")
        
        return recommendations
    
    def _generate_regulatory_report(self, assessments: List[RegulatoryAssessment], 
                                 spans: List[Dict[str, Any]]) -> FDARegulatoryReport:
        """Generate comprehensive regulatory report."""
        # Count compliance status
        compliant_count = sum(1 for a in assessments if a.status == "compliant")
        conditional_count = sum(1 for a in assessments if a.status == "conditional")
        non_compliant_count = sum(1 for a in assessments if a.status == "non_compliant")
        
        # Determine overall compliance
        if non_compliant_count == 0 and conditional_count == 0:
            overall_compliance = "compliant"
            confidence = 0.9
        elif non_compliant_count == 0:
            overall_compliance = "conditional"
            confidence = 0.7
        else:
            overall_compliance = "non_compliant"
            confidence = 0.5
        
        # Collect issues and evidence
        critical_issues = []
        important_issues = []
        supporting_evidence = []
        
        for assessment in assessments:
            if assessment.status == "non_compliant":
                critical_issues.extend(assessment.gaps)
            elif assessment.status == "conditional":
                important_issues.extend(assessment.gaps)
            else:
                supporting_evidence.extend(assessment.evidence)
        
        # Generate summary recommendations
        summary_recommendations = self._generate_summary_recommendations(assessments)
        
        # Calculate span coverage
        all_span_ids = set()
        for assessment in assessments:
            all_span_ids.update(assessment.span_ids)
        
        return FDARegulatoryReport(
            overall_compliance=overall_compliance,
            confidence=confidence,
            critical_issues=critical_issues,
            important_issues=important_issues,
            supporting_evidence=supporting_evidence,
            regulatory_assessments=assessments,
            summary_recommendations=summary_recommendations,
            span_coverage=len(all_span_ids)
        )
    
    def _generate_summary_recommendations(self, assessments: List[RegulatoryAssessment]) -> List[str]:
        """Generate summary recommendations for regulatory compliance."""
        recommendations = []
        
        # Group by category
        category_issues = {}
        for assessment in assessments:
            if assessment.status != "compliant":
                # Extract category from requirement ID
                category = assessment.requirement_id.split('_')[0]
                if category not in category_issues:
                    category_issues[category] = []
                category_issues[category].extend(assessment.recommendations)
        
        # Generate category-specific recommendations
        for category, issues in category_issues.items():
            if category == "efficacy":
                recommendations.append("Focus on demonstrating clinically meaningful efficacy endpoints")
            elif category == "safety":
                recommendations.append("Implement comprehensive safety monitoring and risk management")
            elif category == "quality":
                recommendations.append("Ensure data quality and integrity throughout the trial")
            elif category == "statistical":
                recommendations.append("Document robust statistical analysis plans and methods")
        
        # Add general recommendations
        if any(a.status == "non_compliant" for a in assessments):
            recommendations.append("Address critical compliance issues before regulatory submission")
        
        if any(a.status == "conditional" for a in assessments):
            recommendations.append("Develop mitigation strategies for conditional compliance areas")
        
        return recommendations
    
    def _identify_critical_issues(self, assessments: List[RegulatoryAssessment]) -> List[str]:
        """Identify critical regulatory issues."""
        critical_issues = []
        
        for assessment in assessments:
            if assessment.status == "non_compliant":
                critical_issues.extend([
                    f"{assessment.requirement_id}: {gap}"
                    for gap in assessment.gaps
                ])
        
        return critical_issues
    
    def _create_compliance_summary(self, regulatory_report: FDARegulatoryReport) -> Dict[str, Any]:
        """Create a summary of regulatory compliance."""
        return {
            "overall_compliance": regulatory_report.overall_compliance.upper(),
            "confidence": f"{regulatory_report.confidence:.1%}",
            "critical_issues_count": len(regulatory_report.critical_issues),
            "important_issues_count": len(regulatory_report.important_issues),
            "supporting_evidence_count": len(regulatory_report.supporting_evidence),
            "span_coverage": regulatory_report.span_coverage,
            "recommendations_count": len(regulatory_report.summary_recommendations)
        }
    
    def _get_fda_guidance_references(self) -> List[Dict[str, str]]:
        """Get FDA guidance references for regulatory requirements."""
        references = []
        
        for requirement in self.regulatory_requirements:
            references.append({
                "requirement_id": requirement.requirement_id,
                "category": requirement.category,
                "fda_guidance": requirement.fda_guidance,
                "criticality": requirement.criticality
            })
        
        return references
    
    def export_regulatory_report(self, regulatory_report: FDARegulatoryReport, doc_id: int) -> str:
        """Export regulatory report to JSON format."""
        try:
            export_data = {
                "doc_id": doc_id,
                "regulatory_report": {
                    "overall_compliance": regulatory_report.overall_compliance,
                    "confidence": regulatory_report.confidence,
                    "critical_issues": regulatory_report.critical_issues,
                    "important_issues": regulatory_report.important_issues,
                    "supporting_evidence": regulatory_report.supporting_evidence,
                    "span_coverage": regulatory_report.span_coverage,
                    "summary_recommendations": regulatory_report.summary_recommendations
                },
                "regulatory_assessments": [
                    {
                        "requirement_id": a.requirement_id,
                        "status": a.status,
                        "confidence": a.confidence,
                        "evidence": a.evidence,
                        "gaps": a.gaps,
                        "recommendations": a.recommendations,
                        "span_ids": a.span_ids
                    }
                    for a in regulatory_report.regulatory_assessments
                ],
                "metadata": {
                    "worker_version": self.version,
                    "assessment_timestamp": "2024-01-01T00:00:00Z",  # Should use actual timestamp
                    "regulatory_framework": "FDA",
                    "guidance_version": "2024"
                }
            }
            
            return json.dumps(export_data, indent=2, default=str)
            
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


# Global instance for easy access
_fda_lens = None


def get_fda_lens() -> FdaLens:
    """Get the global FdaLens instance."""
    global _fda_lens
    if _fda_lens is None:
        _fda_lens = FdaLens()
    return _fda_lens


def reload_fda_lens() -> FdaLens:
    """Reload the global FdaLens instance."""
    global _fda_lens
    _fda_lens = FdaLens()
    return _fda_lens
