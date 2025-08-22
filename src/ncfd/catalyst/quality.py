"""Study Card Quality Analysis and Scoring for Phase 10 Catalyst System."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
from enum import Enum

from .models import StudyCardRanking


class FieldCategory(Enum):
    """Categories of study card fields for quality scoring."""
    REQUIRED = "required"
    EVIDENCE = "evidence"
    ADVANCED = "advanced"
    METADATA = "metadata"


class QualityMetric(Enum):
    """Quality metrics for study card evaluation."""
    COMPLETENESS = "completeness"
    EVIDENCE_QUALITY = "evidence_quality"
    DATA_QUALITY = "data_quality"
    RISK_FACTORS = "risk_factors"


@dataclass
class FieldScore:
    """Score for a specific field category."""
    category: FieldCategory
    score: float  # 0.0 to 1.0
    weight: float  # Weight in overall scoring
    fields_checked: int
    fields_present: int
    missing_fields: List[str] = field(default_factory=list)
    quality_notes: List[str] = field(default_factory=list)


@dataclass
class StudyCardQuality:
    """Quality assessment for a study card."""
    study_id: int
    trial_id: int
    overall_score: float  # 0.0 to 1.0
    quality_rank: int  # 1-10 scale
    confidence: float  # 0.0 to 1.0
    field_scores: Dict[FieldCategory, FieldScore] = field(default_factory=dict)
    risk_factors: List[str] = field(default_factory=list)
    quality_notes: List[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.now)


class StudyCardQualityAnalyzer:
    """Analyzes study card quality and generates 1-10 rankings."""
    
    # Field weights for quality scoring
    FIELD_WEIGHTS = {
        FieldCategory.REQUIRED: 0.40,    # Trial info, endpoints, results
        FieldCategory.EVIDENCE: 0.30,    # Evidence spans, data location
        FieldCategory.ADVANCED: 0.20,    # Protocol changes, contradictions
        FieldCategory.METADATA: 0.10     # Coverage level, extraction audit
    }
    
    # Required fields that must be present
    REQUIRED_FIELDS = {
        'trial.nct_id': 'NCT ID',
        'trial.phase': 'Trial Phase',
        'trial.indication': 'Indication',
        'trial.is_pivotal': 'Pivotal Status',
        'primary_endpoints': 'Primary Endpoints',
        'arms': 'Study Arms',
        'sample_size.total_n': 'Sample Size',
        'results.primary': 'Primary Results'
    }
    
    # Evidence fields for quality assessment
    EVIDENCE_FIELDS = {
        'primary_endpoints.*.evidence': 'Endpoint Evidence',
        'results.primary.*.evidence': 'Result Evidence',
        'populations.itt.evidence': 'ITT Population Evidence',
        'populations.pp.evidence': 'PP Population Evidence',
        'arms.*.evidence': 'Arm Evidence',
        'sample_size.evidence': 'Sample Size Evidence'
    }
    
    # Advanced fields for comprehensive analysis
    ADVANCED_FIELDS = {
        'protocol_changes': 'Protocol Changes',
        'contradictions': 'Contradictions',
        'interim_looks': 'Interim Analyses',
        'subgroups': 'Subgroup Analyses',
        'signals': 'Risk Signals'
    }
    
    # Metadata fields for extraction quality
    METADATA_FIELDS = {
        'coverage_level': 'Coverage Level',
        'coverage_rationale': 'Coverage Rationale',
        'extraction_audit.missing_fields': 'Missing Fields',
        'extraction_audit.assumptions': 'Extraction Assumptions'
    }
    
    def __init__(self):
        """Initialize the quality analyzer."""
        self.quality_thresholds = {
            'high': 0.8,      # 80%+ completeness
            'medium': 0.6,    # 60-79% completeness
            'low': 0.4        # 40-59% completeness
        }
    
    def analyze_study_card(self, study_id: int, trial_id: int, extracted_jsonb: Dict[str, Any]) -> StudyCardQuality:
        """
        Analyze study card quality and generate 1-10 ranking.
        
        Args:
            study_id: Study ID
            trial_id: Trial ID
            extracted_jsonb: Extracted study card data
            
        Returns:
            StudyCardQuality with overall score and ranking
        """
        if not extracted_jsonb:
            return self._create_empty_quality(study_id, trial_id)
        
        # Analyze each field category
        field_scores = {}
        for category in FieldCategory:
            field_scores[category] = self._analyze_field_category(category, extracted_jsonb)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(field_scores)
        
        # Generate quality rank (1-10)
        quality_rank = self._score_to_rank(overall_score)
        
        # Calculate confidence
        confidence = self._calculate_confidence(field_scores, overall_score)
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(extracted_jsonb)
        
        # Generate quality notes
        quality_notes = self._generate_quality_notes(field_scores, risk_factors)
        
        return StudyCardQuality(
            study_id=study_id,
            trial_id=trial_id,
            overall_score=overall_score,
            quality_rank=quality_rank,
            confidence=confidence,
            field_scores=field_scores,
            risk_factors=risk_factors,
            quality_notes=quality_notes
        )
    
    def _analyze_field_category(self, category: FieldCategory, data: Dict[str, Any]) -> FieldScore:
        """Analyze quality for a specific field category."""
        if category == FieldCategory.REQUIRED:
            return self._analyze_required_fields(data)
        elif category == FieldCategory.EVIDENCE:
            return self._analyze_evidence_fields(data)
        elif category == FieldCategory.ADVANCED:
            return self._analyze_advanced_fields(data)
        elif category == FieldCategory.METADATA:
            return self._analyze_metadata_fields(data)
        else:
            raise ValueError(f"Unknown field category: {category}")
    
    def _analyze_required_fields(self, data: Dict[str, Any]) -> FieldScore:
        """Analyze required field completeness."""
        fields_checked = 0
        fields_present = 0
        missing_fields = []
        
        for field_path, field_name in self.REQUIRED_FIELDS.items():
            fields_checked += 1
            if self._field_exists(data, field_path):
                fields_present += 1
            else:
                missing_fields.append(field_name)
        
        score = fields_present / fields_checked if fields_checked > 0 else 0.0
        weight = self.FIELD_WEIGHTS[FieldCategory.REQUIRED]
        
        return FieldScore(
            category=FieldCategory.REQUIRED,
            score=score,
            weight=weight,
            fields_checked=fields_checked,
            fields_present=fields_present,
            missing_fields=missing_fields
        )
    
    def _analyze_evidence_fields(self, data: Dict[str, Any]) -> FieldScore:
        """Analyze evidence field quality."""
        fields_checked = 0
        fields_present = 0
        missing_fields = []
        quality_notes = []
        
        for field_path, field_name in self.EVIDENCE_FIELDS.items():
            fields_checked += 1
            evidence_data = self._get_field_value(data, field_path)
            
            if evidence_data:
                if isinstance(evidence_data, list) and len(evidence_data) > 0:
                    fields_present += 1
                    # Check evidence quality
                    evidence_quality = self._assess_evidence_quality(evidence_data)
                    if evidence_quality < 0.5:
                        quality_notes.append(f"Low quality evidence in {field_name}")
                else:
                    missing_fields.append(field_name)
            else:
                missing_fields.append(field_name)
        
        score = fields_present / fields_checked if fields_checked > 0 else 0.0
        weight = self.FIELD_WEIGHTS[FieldCategory.EVIDENCE]
        
        return FieldScore(
            category=FieldCategory.EVIDENCE,
            score=score,
            weight=weight,
            fields_checked=fields_checked,
            fields_present=fields_present,
            missing_fields=missing_fields,
            quality_notes=quality_notes
        )
    
    def _analyze_advanced_fields(self, data: Dict[str, Any]) -> FieldScore:
        """Analyze advanced field presence and quality."""
        fields_checked = 0
        fields_present = 0
        missing_fields = []
        quality_notes = []
        
        for field_path, field_name in self.ADVANCED_FIELDS.items():
            fields_checked += 1
            field_data = self._get_field_value(data, field_path)
            
            if field_data:
                if isinstance(field_data, list) and len(field_data) > 0:
                    fields_present += 1
                    # Check for risk factors
                    if field_path == 'protocol_changes':
                        quality_notes.extend(self._analyze_protocol_changes(field_data))
                    elif field_path == 'contradictions':
                        quality_notes.extend(self._analyze_contradictions(field_data))
                else:
                    missing_fields.append(field_name)
            else:
                missing_fields.append(field_name)
        
        score = fields_present / fields_checked if fields_checked > 0 else 0.0
        weight = self.FIELD_WEIGHTS[FieldCategory.ADVANCED]
        
        return FieldScore(
            category=FieldCategory.ADVANCED,
            score=score,
            weight=weight,
            fields_checked=fields_checked,
            fields_present=fields_present,
            missing_fields=missing_fields,
            quality_notes=quality_notes
        )
    
    def _analyze_metadata_fields(self, data: Dict[str, Any]) -> FieldScore:
        """Analyze metadata field quality."""
        fields_checked = 0
        fields_present = 0
        missing_fields = []
        quality_notes = []
        
        for field_path, field_name in self.METADATA_FIELDS.items():
            fields_checked += 1
            field_data = self._get_field_value(data, field_path)
            
            if field_data:
                fields_present += 1
                # Check coverage level quality
                if field_path == 'coverage_level':
                    coverage_quality = self._assess_coverage_quality(field_data)
                    if coverage_quality < 0.5:
                        quality_notes.append(f"Low coverage quality: {field_data}")
            else:
                missing_fields.append(field_name)
        
        score = fields_present / fields_checked if fields_checked > 0 else 0.0
        weight = self.FIELD_WEIGHTS[FieldCategory.METADATA]
        
        return FieldScore(
            category=FieldCategory.METADATA,
            score=score,
            weight=weight,
            fields_checked=fields_checked,
            fields_present=fields_present,
            missing_fields=missing_fields,
            quality_notes=quality_notes
        )
    
    def _calculate_overall_score(self, field_scores: Dict[FieldCategory, FieldScore]) -> float:
        """Calculate weighted overall quality score."""
        total_score = 0.0
        total_weight = 0.0
        
        for category, field_score in field_scores.items():
            total_score += field_score.score * field_score.weight
            total_weight += field_score.weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def _score_to_rank(self, score: float) -> int:
        """Convert quality score (0.0-1.0) to 1-10 ranking."""
        if score >= 0.9:
            return 10  # Excellent quality
        elif score >= 0.8:
            return 9   # Very high quality
        elif score >= 0.7:
            return 8   # High quality
        elif score >= 0.6:
            return 7   # Good quality
        elif score >= 0.5:
            return 6   # Moderate quality
        elif score >= 0.4:
            return 5   # Fair quality
        elif score >= 0.3:
            return 4   # Poor quality
        elif score >= 0.2:
            return 3   # Very poor quality
        elif score >= 0.1:
            return 2   # Extremely poor quality
        else:
            return 1   # Insufficient data
    
    def _calculate_confidence(self, field_scores: Dict[FieldCategory, FieldScore], overall_score: float) -> float:
        """Calculate confidence in the quality assessment."""
        # Base confidence on overall score
        base_confidence = overall_score
        
        # Adjust based on field score consistency
        score_variance = 0.0
        scores = [fs.score for fs in field_scores.values()]
        if len(scores) > 1:
            mean_score = sum(scores) / len(scores)
            score_variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        
        # Higher variance = lower confidence
        variance_penalty = min(0.2, score_variance * 0.5)
        
        return max(0.0, min(1.0, base_confidence - variance_penalty))
    
    def _identify_risk_factors(self, data: Dict[str, Any]) -> List[str]:
        """Identify risk factors in the study card data."""
        risk_factors = []
        
        # Check for protocol changes (S1 signal)
        protocol_changes = self._get_field_value(data, 'protocol_changes')
        if protocol_changes and isinstance(protocol_changes, list):
            for change in protocol_changes:
                if isinstance(change, dict) and change.get('post_LPR', False):
                    risk_factors.append("Protocol change after LPR (S1)")
                elif isinstance(change, str):
                    risk_factors.append(f"Protocol change: {change}")
        
        # Check for underpowered studies (S2 signal)
        sample_size = self._get_field_value(data, 'sample_size')
        if sample_size and isinstance(sample_size, dict) and sample_size.get('power'):
            power = sample_size['power']
            if power < 0.7:
                risk_factors.append(f"Underpowered study (power: {power:.2f})")
        elif sample_size and isinstance(sample_size, (int, float)):
            # If sample_size is a number, check if it's too small
            if sample_size < 100:
                risk_factors.append(f"Small sample size: {sample_size}")
        
        # Check for subgroup-only wins (S3 signal)
        results = self._get_field_value(data, 'results')
        if results and results.get('subgroups'):
            subgroups = results['subgroups']
            for subgroup in subgroups:
                if subgroup.get('success_declared') and not results.get('primary', [{}])[0].get('success_declared'):
                    risk_factors.append("Subgroup-only win without primary success")
        
        # Check for ITT vs PP discrepancies (S4 signal)
        populations = self._get_field_value(data, 'populations')
        if populations:
            itt_defined = populations.get('itt', {}).get('defined', False)
            pp_defined = populations.get('pp', {}).get('defined', False)
            if itt_defined and pp_defined:
                analysis_on = populations.get('analysis_primary_on')
                if analysis_on == 'PP':
                    risk_factors.append("Primary analysis on PP population instead of ITT")
        
        return risk_factors
    
    def _generate_quality_notes(self, field_scores: Dict[FieldCategory, FieldScore], risk_factors: List[str]) -> List[str]:
        """Generate quality assessment notes."""
        notes = []
        
        # Add field-specific notes
        for category, field_score in field_scores.items():
            if field_score.quality_notes:
                notes.extend(field_score.quality_notes)
            
            if field_score.score < 0.5:
                notes.append(f"Low {category.value} quality: {field_score.score:.1%}")
        
        # Add risk factor notes
        if risk_factors:
            notes.append(f"Identified {len(risk_factors)} risk factors")
        
        # Add overall quality note
        overall_score = self._calculate_overall_score(field_scores)
        if overall_score >= 0.8:
            notes.append("High quality study card with comprehensive data")
        elif overall_score >= 0.6:
            notes.append("Moderate quality study card with some gaps")
        else:
            notes.append("Low quality study card with significant data gaps")
        
        return notes
    
    def _field_exists(self, data: Dict[str, Any], field_path: str) -> bool:
        """Check if a field exists in the data."""
        return self._get_field_value(data, field_path) is not None
    
    def _get_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get field value using dot notation path."""
        if not field_path:
            return None
        
        keys = field_path.split('.')
        current = data
        
        for key in keys:
            if key == '*':
                # Handle wildcard for array fields
                if isinstance(current, list) and len(current) > 0:
                    current = current[0]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            
            if current is None:
                return None
        
        return current
    
    def _assess_evidence_quality(self, evidence_data: List[Dict[str, Any]]) -> float:
        """Assess the quality of evidence spans."""
        if not evidence_data:
            return 0.0
        
        total_quality = 0.0
        for evidence in evidence_data:
            # Check for required evidence fields
            has_location = 'loc' in evidence and evidence['loc']
            has_text_preview = 'text_preview' in evidence and evidence['text_preview']
            
            evidence_quality = 0.0
            if has_location:
                evidence_quality += 0.6
            if has_text_preview:
                evidence_quality += 0.4
            
            total_quality += evidence_quality
        
        return total_quality / len(evidence_data)
    
    def _assess_coverage_quality(self, coverage_level: str) -> float:
        """Assess the quality of coverage level."""
        coverage_scores = {
            'high': 1.0,
            'med': 0.7,
            'medium': 0.7,
            'low': 0.4
        }
        return coverage_scores.get(coverage_level.lower(), 0.5)
    
    def _analyze_protocol_changes(self, changes: List[Dict[str, Any]]) -> List[str]:
        """Analyze protocol changes for risk factors."""
        notes = []
        for change in changes:
            if isinstance(change, dict):
                if change.get('post_LPR', False):
                    notes.append(f"Protocol change after LPR: {change.get('change', 'Unknown')}")
            else:
                # Handle case where change is a string
                notes.append(f"Protocol change: {change}")
        return notes
    
    def _analyze_contradictions(self, contradictions: List[Dict[str, Any]]) -> List[str]:
        """Analyze contradictions for risk factors."""
        notes = []
        for contradiction in contradictions:
            contradiction_type = contradiction.get('type', 'unknown')
            notes.append(f"Contradiction detected: {contradiction_type}")
        return notes
    
    def _create_empty_quality(self, study_id: int, trial_id: int) -> StudyCardQuality:
        """Create quality assessment for empty study card."""
        return StudyCardQuality(
            study_id=study_id,
            trial_id=trial_id,
            overall_score=0.0,
            quality_rank=1,
            confidence=0.0,
            quality_notes=["No study card data available"]
        )
