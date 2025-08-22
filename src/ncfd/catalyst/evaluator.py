"""Automatic Study Card Evaluator for Phase 10 Catalyst System."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import logging
from enum import Enum

from .quality import StudyCardQualityAnalyzer, StudyCardQuality, FieldCategory
from .extractor import StudyCardFieldExtractor, FieldExtractionResult
from .validation import StudyCardFieldValidator, FieldValidationResult
from .models import StudyCardRanking

logger = logging.getLogger(__name__)


class RiskFactor(Enum):
    """Risk factors that affect study card quality and ranking."""
    PROTOCOL_CHANGE_POST_LPR = "protocol_change_post_lpr"      # S1 signal
    UNDERPOWERED_STUDY = "underpowered_study"                  # S2 signal
    SUBGROUP_ONLY_WIN = "subgroup_only_win"                    # S3 signal
    PP_ANALYSIS_INSTEAD_ITT = "pp_analysis_instead_itt"        # S4 signal
    EFFECT_SIZE_ANOMALY = "effect_size_anomaly"                # S5 signal
    MISSING_EVIDENCE = "missing_evidence"                      # Evidence gaps
    INCONSISTENT_DATA = "inconsistent_data"                    # Data contradictions
    LOW_COVERAGE_QUALITY = "low_coverage_quality"              # Poor extraction
    ENDPOINT_CHANGES = "endpoint_changes"                      # Protocol modifications
    POPULATION_ISSUES = "population_issues"                    # Population problems


@dataclass
class RiskAssessment:
    """Assessment of risk factors for a study card."""
    risk_factor: RiskFactor
    severity: str  # "low", "medium", "high", "critical"
    description: str
    evidence: str
    impact_score: float  # 0.0 to 1.0
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class AutomaticEvaluation:
    """Automatic evaluation result for a study card."""
    study_id: int
    trial_id: int
    quality_score: float  # 0.0 to 1.0
    quality_rank: int  # 1-10 scale
    confidence_score: float  # 0.0 to 1.0
    risk_factors: List[RiskAssessment] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    evaluation_notes: List[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.now)


class AutomaticStudyCardEvaluator:
    """Automatically evaluates study cards and generates 1-10 rankings."""
    
    # Risk factor impact weights
    RISK_IMPACT_WEIGHTS = {
        RiskFactor.PROTOCOL_CHANGE_POST_LPR: 0.25,      # High impact
        RiskFactor.UNDERPOWERED_STUDY: 0.20,            # High impact
        RiskFactor.SUBGROUP_ONLY_WIN: 0.15,            # Medium impact
        RiskFactor.PP_ANALYSIS_INSTEAD_ITT: 0.15,      # Medium impact
        RiskFactor.EFFECT_SIZE_ANOMALY: 0.10,          # Medium impact
        RiskFactor.MISSING_EVIDENCE: 0.08,             # Low impact
        RiskFactor.INCONSISTENT_DATA: 0.05,            # Low impact
        RiskFactor.LOW_COVERAGE_QUALITY: 0.02,         # Low impact
        RiskFactor.ENDPOINT_CHANGES: 0.03,             # Low impact
        RiskFactor.POPULATION_ISSUES: 0.02              # Low impact
    }
    
    # Quality score thresholds for ranking
    QUALITY_THRESHOLDS = {
        10: 0.95,  # Excellent quality
        9: 0.90,   # Very high quality
        8: 0.85,   # High quality
        7: 0.80,   # Good quality
        6: 0.75,   # Moderate quality
        5: 0.70,   # Fair quality
        4: 0.60,   # Poor quality
        3: 0.50,   # Very poor quality
        2: 0.30,   # Extremely poor quality
        1: 0.00    # Insufficient data
    }
    
    def __init__(self):
        """Initialize the automatic evaluator."""
        self.quality_analyzer = StudyCardQualityAnalyzer()
        self.field_extractor = StudyCardFieldExtractor()
        self.field_validator = StudyCardFieldValidator()
        
        logger.info("Automatic Study Card Evaluator initialized")
    
    def evaluate_study_card(self, study_id: int, trial_id: int, extracted_jsonb: Dict[str, Any]) -> AutomaticEvaluation:
        """
        Automatically evaluate a study card and generate 1-10 ranking.
        
        Args:
            study_id: Study ID
            trial_id: Trial ID
            extracted_jsonb: Extracted study card data
            
        Returns:
            AutomaticEvaluation with quality score, ranking, and risk assessment
        """
        try:
            logger.info(f"Starting automatic evaluation for study {study_id}, trial {trial_id}")
            
            # Step 1: Extract fields
            extraction_result = self.field_extractor.extract_study_card_fields(
                study_id, trial_id, extracted_jsonb
            )
            
            # Step 2: Validate extracted fields
            validation_result = self.field_validator.validate_extracted_fields(
                extraction_result.extracted_fields, study_id, trial_id
            )
            
            # Step 3: Analyze quality
            quality_result = self.quality_analyzer.analyze_study_card(
                study_id, trial_id, extracted_jsonb
            )
            
            # Step 4: Assess risk factors
            risk_factors = self._assess_risk_factors(
                extraction_result, validation_result, quality_result
            )
            
            # Step 5: Calculate quality score
            quality_score = self._calculate_quality_score(
                extraction_result, validation_result, quality_result, risk_factors
            )
            
            # Step 6: Generate quality rank
            quality_rank = self._score_to_rank(quality_score)
            
            # Step 7: Calculate confidence
            confidence_score = self._calculate_confidence(
                extraction_result, validation_result, quality_result, risk_factors
            )
            
            # Step 8: Generate evaluation notes
            evaluation_notes = self._generate_evaluation_notes(
                extraction_result, validation_result, quality_result, risk_factors
            )
            
            # Step 9: Compile quality metrics
            quality_metrics = self._compile_quality_metrics(
                extraction_result, validation_result, quality_result
            )
            
            evaluation = AutomaticEvaluation(
                study_id=study_id,
                trial_id=trial_id,
                quality_score=quality_score,
                quality_rank=quality_rank,
                confidence_score=confidence_score,
                risk_factors=risk_factors,
                quality_metrics=quality_metrics,
                evaluation_notes=evaluation_notes
            )
            
            logger.info(f"Automatic evaluation completed: rank {quality_rank}/10, score {quality_score:.2f}")
            return evaluation
            
        except Exception as e:
            logger.error(f"Error in automatic evaluation for study {study_id}, trial {trial_id}: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Return minimal evaluation on error
            return self._create_error_evaluation(study_id, trial_id, str(e))
    
    def _assess_risk_factors(self, extraction_result: FieldExtractionResult, 
                            validation_result: FieldValidationResult,
                            quality_result: StudyCardQuality) -> List[RiskAssessment]:
        """Assess risk factors based on extraction, validation, and quality results."""
        risk_factors = []
        
        try:
            # Check for protocol changes post-LPR (S1 signal)
            protocol_changes = self._get_field_value(extraction_result, "protocol_changes")
            if protocol_changes and isinstance(protocol_changes, list):
                for change in protocol_changes:
                    if isinstance(change, dict) and change.get("post_LPR", False):
                        risk_factors.append(RiskAssessment(
                            risk_factor=RiskFactor.PROTOCOL_CHANGE_POST_LPR,
                            severity="high",
                            description="Protocol change after LPR detected",
                            evidence=f"Change: {change.get('change', 'Unknown')}",
                            impact_score=0.9
                        ))
        except Exception as e:
            logger.warning(f"Error checking protocol changes: {e}")
            pass
        
        try:
            # Check for underpowered studies (S2 signal)
            power_calculation = self._get_field_value(extraction_result, "power_calculation")
            if power_calculation and isinstance(power_calculation, (int, float)):
                if power_calculation < 0.7:
                    risk_factors.append(RiskAssessment(
                        risk_factor=RiskFactor.UNDERPOWERED_STUDY,
                        severity="high",
                        description="Study appears underpowered",
                        evidence=f"Power: {power_calculation:.2f}",
                        impact_score=0.8
                    ))
        except Exception as e:
            logger.warning(f"Error checking underpowered studies: {e}")
            pass
        
        try:
            # Check for subgroup-only wins (S3 signal)
            primary_results = self._get_field_value(extraction_result, "primary_results")
            subgroup_results = self._get_field_value(extraction_result, "subgroup_results")
            
            if primary_results and subgroup_results and isinstance(primary_results, list) and isinstance(subgroup_results, list):
                primary_success = any(isinstance(result, dict) and result.get("success_declared", False) for result in primary_results)
                subgroup_success = any(isinstance(result, dict) and result.get("success_declared", False) for result in subgroup_results)
                
                if subgroup_success and not primary_success:
                    risk_factors.append(RiskAssessment(
                        risk_factor=RiskFactor.SUBGROUP_ONLY_WIN,
                        severity="medium",
                        description="Subgroup-only win without primary success",
                        evidence="Subgroup analysis shows success but primary endpoint failed",
                        impact_score=0.6
                    ))
        except Exception as e:
            logger.warning(f"Error checking subgroup wins: {e}")
            pass
        
        try:
            # Check for PP analysis instead of ITT (S4 signal)
            analysis_population = self._get_field_value(extraction_result, "analysis_population")
            if analysis_population == "PP":
                itt_defined = self._get_field_value(extraction_result, "itt_definition")
                if itt_defined:
                    risk_factors.append(RiskAssessment(
                        risk_factor=RiskFactor.PP_ANALYSIS_INSTEAD_ITT,
                        severity="medium",
                        description="Primary analysis on PP population instead of ITT",
                        evidence="ITT population defined but analysis performed on PP",
                        impact_score=0.5
                    ))
        except Exception as e:
            logger.warning(f"Error checking population analysis: {e}")
            pass
        
        try:
            # Check for effect size anomalies (S5 signal)
            effect_sizes = self._get_field_value(extraction_result, "effect_sizes")
            if effect_sizes and isinstance(effect_sizes, list):
                for effect in effect_sizes:
                    if isinstance(effect, dict) and "value" in effect:
                        effect_value = effect["value"]
                        if isinstance(effect_value, (int, float)):
                            # Check for unusually large effect sizes
                            if abs(effect_value) > 2.0:  # HR > 2.0 or < 0.5
                                risk_factors.append(RiskAssessment(
                                    risk_factor=RiskFactor.EFFECT_SIZE_ANOMALY,
                                    severity="medium",
                                    description="Unusually large effect size detected",
                                    evidence=f"Effect size: {effect_value}",
                                    impact_score=0.4
                                ))
        except Exception as e:
            logger.warning(f"Error checking effect sizes: {e}")
            pass
        
        # Check for missing evidence
        try:
            if extraction_result.extraction_summary["missing_count"] > 0:
                risk_factors.append(RiskAssessment(
                    risk_factor=RiskFactor.MISSING_EVIDENCE,
                    severity="low",
                    description="Missing evidence for key fields",
                    evidence=f"{extraction_result.extraction_summary['missing_count']} fields missing evidence",
                    impact_score=0.3
                ))
        except (KeyError, TypeError):
            pass  # Skip if extraction summary is not available
        
        # Check for inconsistent data
        try:
            if validation_result.validation_issues:
                consistency_issues = [issue for issue in validation_result.validation_issues 
                                    if hasattr(issue, 'rule_type') and hasattr(issue.rule_type, 'value') 
                                    and issue.rule_type.value == "field_consistency"]
                if consistency_issues:
                    risk_factors.append(RiskAssessment(
                        risk_factor=RiskFactor.INCONSISTENT_DATA,
                        severity="low",
                        description="Data consistency issues detected",
                        evidence=f"{len(consistency_issues)} consistency issues found",
                        impact_score=0.2
                    ))
        except (AttributeError, TypeError):
            pass  # Skip if validation issues are not properly structured
        
        # Check for low coverage quality
        try:
            if hasattr(quality_result, 'overall_score') and quality_result.overall_score < 0.5:
                risk_factors.append(RiskAssessment(
                    risk_factor=RiskFactor.LOW_COVERAGE_QUALITY,
                    severity="low",
                    description="Low coverage quality",
                    evidence=f"Coverage score: {quality_result.overall_score:.2f}",
                    impact_score=0.2
                ))
        except (AttributeError, TypeError):
            pass  # Skip if quality result is not properly structured
        
        return risk_factors
    
    def _calculate_quality_score(self, extraction_result: FieldExtractionResult,
                                validation_result: FieldValidationResult,
                                quality_result: StudyCardQuality,
                                risk_factors: List[RiskAssessment]) -> float:
        """Calculate overall quality score based on all assessment components."""
        # Base quality score from quality analyzer (40% weight)
        base_quality = quality_result.overall_score * 0.4
        
        # Extraction completeness score (30% weight)
        extraction_score = extraction_result.extraction_summary["completeness_score"] * 0.3
        
        # Validation quality score (20% weight)
        validation_score = validation_result.overall_quality_score / 100.0 * 0.2
        
        # Risk factor penalty (10% weight)
        risk_penalty = self._calculate_risk_penalty(risk_factors) * 0.1
        
        # Calculate final score
        final_score = base_quality + extraction_score + validation_score - risk_penalty
        
        return max(0.0, min(1.0, final_score))
    
    def _calculate_risk_penalty(self, risk_factors: List[RiskAssessment]) -> float:
        """Calculate penalty based on risk factors."""
        if not risk_factors:
            return 0.0
        
        total_penalty = 0.0
        for risk in risk_factors:
            impact_weight = self.RISK_IMPACT_WEIGHTS.get(risk.risk_factor, 0.0)
            total_penalty += risk.impact_score * impact_weight
        
        return min(0.5, total_penalty)  # Cap penalty at 50%
    
    def _score_to_rank(self, quality_score: float) -> int:
        """Convert quality score (0.0-1.0) to 1-10 ranking."""
        for rank, threshold in sorted(self.QUALITY_THRESHOLDS.items(), reverse=True):
            if quality_score >= threshold:
                return rank
        return 1
    
    def _calculate_confidence(self, extraction_result: FieldExtractionResult,
                             validation_result: FieldValidationResult,
                             quality_result: StudyCardQuality,
                             risk_factors: List[RiskAssessment]) -> float:
        """Calculate confidence in the automatic evaluation."""
        # Base confidence from quality result
        base_confidence = quality_result.confidence * 0.4
        
        # Extraction confidence
        extraction_confidence = extraction_result.extraction_summary["avg_confidence"] * 0.3
        
        # Validation confidence
        validation_confidence = (100.0 - validation_result.validation_summary["total_issues"] * 0.5) / 100.0
        validation_confidence = max(0.0, min(1.0, validation_confidence))
        validation_confidence *= 0.2
        
        # Risk factor confidence (fewer risk factors = higher confidence)
        risk_confidence = max(0.0, 1.0 - len(risk_factors) * 0.1) * 0.1
        
        total_confidence = base_confidence + extraction_confidence + validation_confidence + risk_confidence
        
        return max(0.0, min(1.0, total_confidence))
    
    def _generate_evaluation_notes(self, extraction_result: FieldExtractionResult,
                                  validation_result: FieldValidationResult,
                                  quality_result: StudyCardQuality,
                                  risk_factors: List[RiskAssessment]) -> List[str]:
        """Generate comprehensive evaluation notes."""
        notes = []
        
        # Quality analysis notes
        if quality_result.quality_notes:
            notes.extend(quality_result.quality_notes)
        
        # Extraction notes
        extraction_summary = extraction_result.extraction_summary
        notes.append(f"Field extraction: {extraction_summary['extracted_count']}/{extraction_summary['total_fields']} fields successfully extracted")
        
        if extraction_summary['missing_count'] > 0:
            notes.append(f"Missing fields: {extraction_summary['missing_count']} fields could not be extracted")
        
        # Validation notes
        validation_summary = validation_result.validation_summary
        if validation_summary['total_issues'] > 0:
            notes.append(f"Validation issues: {validation_summary['total_issues']} issues detected")
            if validation_summary['critical_issues'] > 0:
                notes.append(f"Critical issues: {validation_summary['critical_issues']} critical validation problems")
        
        # Risk factor notes
        if risk_factors:
            high_risk = [r for r in risk_factors if r.severity in ["high", "critical"]]
            medium_risk = [r for r in risk_factors if r.severity == "medium"]
            low_risk = [r for r in risk_factors if r.severity == "low"]
            
            if high_risk:
                notes.append(f"High-risk factors: {len(high_risk)} high/critical risk factors identified")
            if medium_risk:
                notes.append(f"Medium-risk factors: {len(medium_risk)} medium-risk factors identified")
            if low_risk:
                notes.append(f"Low-risk factors: {len(low_risk)} low-risk factors identified")
        
        # Overall assessment
        if quality_result.overall_score >= 0.8:
            notes.append("Overall assessment: High quality study card with comprehensive data")
        elif quality_result.overall_score >= 0.6:
            notes.append("Overall assessment: Moderate quality study card with some gaps")
        else:
            notes.append("Overall assessment: Low quality study card with significant data gaps")
        
        return notes
    
    def _compile_quality_metrics(self, extraction_result: FieldExtractionResult,
                                validation_result: FieldValidationResult,
                                quality_result: StudyCardQuality) -> Dict[str, Any]:
        """Compile comprehensive quality metrics."""
        return {
            "quality_analysis": {
                "overall_score": quality_result.overall_score,
                "field_scores": {cat.value: score.score for cat, score in quality_result.field_scores.items()},
                "risk_factors": quality_result.risk_factors if isinstance(quality_result.risk_factors, list) else []
            },
            "field_extraction": {
                "total_fields": extraction_result.extraction_summary["total_fields"],
                "extracted_count": extraction_result.extraction_summary["extracted_count"],
                "completeness_score": extraction_result.extraction_summary["completeness_score"],
                "avg_confidence": extraction_result.extraction_summary["avg_confidence"]
            },
            "field_validation": {
                "overall_score": validation_result.overall_quality_score,
                "quality_grade": validation_result.validation_summary["quality_grade"],
                "total_issues": validation_result.validation_summary["total_issues"],
                "issue_breakdown": validation_result.validation_summary["level_counts"]
            }
        }
    
    def _get_field_value(self, extraction_result: FieldExtractionResult, field_name: str) -> Any:
        """Get field value from extraction result."""
        if field_name in extraction_result.extracted_fields:
            field_data = extraction_result.extracted_fields[field_name]
            if hasattr(field_data, 'value'):
                return field_data.value
            return field_data
        return None
    
    def _create_error_evaluation(self, study_id: int, trial_id: int, error_message: str) -> AutomaticEvaluation:
        """Create evaluation result for error cases."""
        return AutomaticEvaluation(
            study_id=study_id,
            trial_id=trial_id,
            quality_score=0.0,
            quality_rank=1,
            confidence_score=0.0,
            evaluation_notes=[f"Evaluation error: {error_message}"],
            quality_metrics={"error": error_message}
        )
