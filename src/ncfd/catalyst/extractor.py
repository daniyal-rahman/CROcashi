"""Study Card Field Extraction Engine for Phase 10 Catalyst System."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime
import json
import re
from enum import Enum

from .quality import FieldCategory


class ExtractionStatus(Enum):
    """Status of field extraction."""
    EXTRACTED = "extracted"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"


class FieldType(Enum):
    """Types of extracted fields."""
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ARRAY = "array"
    OBJECT = "object"
    EVIDENCE = "evidence"


@dataclass
class ExtractedField:
    """A single extracted field from study card data."""
    field_name: str
    field_path: str
    field_type: FieldType
    value: Any
    extraction_status: ExtractionStatus
    confidence: float  # 0.0 to 1.0
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)
    quality_notes: List[str] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.now)


@dataclass
class FieldExtractionResult:
    """Result of field extraction for a study card."""
    study_id: int
    trial_id: int
    extracted_fields: Dict[str, ExtractedField] = field(default_factory=dict)
    extraction_summary: Dict[str, Any] = field(default_factory=dict)
    extraction_errors: List[str] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.now)


class StudyCardFieldExtractor:
    """Extracts specific fields from study card data for comprehensive analysis."""
    
    # Field definitions with extraction paths and validation rules
    FIELD_DEFINITIONS = {
        # Trial Information
        "trial_info": {
            "nct_id": {"path": "trial.nct_id", "type": FieldType.TEXT, "required": True},
            "phase": {"path": "trial.phase", "type": FieldType.TEXT, "required": True},
            "indication": {"path": "trial.indication", "type": FieldType.TEXT, "required": True},
            "is_pivotal": {"path": "trial.is_pivotal", "type": FieldType.BOOLEAN, "required": True},
            "sponsor": {"path": "trial.sponsor", "type": FieldType.TEXT, "required": False},
            "start_date": {"path": "trial.start_date", "type": FieldType.DATE, "required": False},
            "completion_date": {"path": "trial.completion_date", "type": FieldType.DATE, "required": False}
        },
        
        # Endpoint Definitions
        "endpoints": {
            "primary_endpoints": {"path": "primary_endpoints", "type": FieldType.ARRAY, "required": True},
            "secondary_endpoints": {"path": "secondary_endpoints", "type": FieldType.ARRAY, "required": False},
            "endpoint_changes": {"path": "endpoint_changes", "type": FieldType.ARRAY, "required": False}
        },
        
        # Population Analysis
        "populations": {
            "itt_definition": {"path": "populations.itt", "type": FieldType.OBJECT, "required": False},
            "pp_definition": {"path": "populations.pp", "type": FieldType.OBJECT, "required": False},
            "analysis_population": {"path": "populations.analysis_primary_on", "type": FieldType.TEXT, "required": False},
            "dropout_summary": {"path": "populations.dropout_summary", "type": FieldType.OBJECT, "required": False},
            "missingness_summary": {"path": "populations.missingness_summary", "type": FieldType.OBJECT, "required": False}
        },
        
        # Results and Outcomes
        "results": {
            "primary_results": {"path": "results.primary", "type": FieldType.ARRAY, "required": True},
            "secondary_results": {"path": "results.secondary", "type": FieldType.ARRAY, "required": False},
            "subgroup_results": {"path": "results.subgroups", "type": FieldType.ARRAY, "required": False},
            "effect_sizes": {"path": "results.effect_sizes", "type": FieldType.ARRAY, "required": False},
            "confidence_intervals": {"path": "results.confidence_intervals", "type": FieldType.ARRAY, "required": False}
        },
        
        # Statistical Analysis
        "statistics": {
            "sample_size": {"path": "sample_size", "type": FieldType.OBJECT, "required": True},
            "power_calculation": {"path": "sample_size.power", "type": FieldType.NUMBER, "required": False},
            "imputation_method": {"path": "statistics.imputation_method", "type": FieldType.TEXT, "required": False},
            "multiplicity_adjustments": {"path": "statistics.multiplicity_adjustments", "type": FieldType.OBJECT, "required": False},
            "alpha_spending": {"path": "statistics.alpha_spending", "type": FieldType.OBJECT, "required": False}
        },
        
        # Protocol and Design
        "protocol": {
            "randomization": {"path": "protocol.randomization", "type": FieldType.OBJECT, "required": False},
            "blinding": {"path": "protocol.blinding", "type": FieldType.OBJECT, "required": False},
            "interim_looks": {"path": "protocol.interim_looks", "type": FieldType.ARRAY, "required": False},
            "dsmb_rules": {"path": "protocol.dsmb_rules", "type": FieldType.OBJECT, "required": False}
        },
        
        # Risk Factors and Signals
        "risk_factors": {
            "protocol_changes": {"path": "protocol_changes", "type": FieldType.ARRAY, "required": False},
            "contradictions": {"path": "contradictions", "type": FieldType.ARRAY, "required": False},
            "risk_signals": {"path": "signals", "type": FieldType.ARRAY, "required": False}
        },
        
        # Evidence and Data Location
        "evidence": {
            "data_tables": {"path": "evidence.data_tables", "type": FieldType.ARRAY, "required": False},
            "figure_references": {"path": "evidence.figures", "type": FieldType.ARRAY, "required": False},
            "page_references": {"path": "evidence.pages", "type": FieldType.ARRAY, "required": False},
            "quote_spans": {"path": "evidence.quote_spans", "type": FieldType.ARRAY, "required": False}
        },
        
        # Publication and Source
        "publication": {
            "journal_type": {"path": "publication.journal_type", "type": FieldType.TEXT, "required": False},
            "open_access": {"path": "publication.open_access", "type": FieldType.BOOLEAN, "required": False},
            "publication_date": {"path": "publication.date", "type": FieldType.DATE, "required": False},
            "doi": {"path": "publication.doi", "type": FieldType.TEXT, "required": False}
        },
        
        # Conflicts and Funding
        "conflicts": {
            "conflicts_of_interest": {"path": "conflicts.interest", "type": FieldType.ARRAY, "required": False},
            "funding_sources": {"path": "conflicts.funding", "type": FieldType.ARRAY, "required": False},
            "sponsor_role": {"path": "conflicts.sponsor_role", "type": FieldType.TEXT, "required": False}
        },
        
        # Reviewer Notes
        "reviewer_notes": {
            "limitations": {"path": "reviewer_notes.limitations", "type": FieldType.ARRAY, "required": False},
            "oddities": {"path": "reviewer_notes.oddities", "type": FieldType.ARRAY, "required": False},
            "geographic_outliers": {"path": "reviewer_notes.geographic_outliers", "type": FieldType.ARRAY, "required": False},
            "unexplained_discrepancies": {"path": "reviewer_notes.discrepancies", "type": FieldType.ARRAY, "required": False}
        }
    }
    
    def __init__(self):
        """Initialize the field extractor."""
        self.evidence_extractor = EvidenceSpanExtractor()
        self.tone_analyzer = ToneAnalyzer()
    
    def extract_study_card_fields(self, study_id: int, trial_id: int, extracted_jsonb: Dict[str, Any]) -> FieldExtractionResult:
        """
        Extract all defined fields from study card data.
        
        Args:
            study_id: Study ID
            trial_id: Trial ID
            extracted_jsonb: Extracted study card data
            
        Returns:
            FieldExtractionResult with all extracted fields
        """
        if not extracted_jsonb:
            return self._create_empty_result(study_id, trial_id)
        
        extracted_fields = {}
        extraction_errors = []
        
        try:
            # Extract fields from each category
            for category_name, field_defs in self.FIELD_DEFINITIONS.items():
                for field_name, field_def in field_defs.items():
                    try:
                        extracted_field = self._extract_single_field(
                            field_name, field_def, extracted_jsonb
                        )
                        if extracted_field:
                            extracted_fields[field_name] = extracted_field
                    except Exception as e:
                        error_msg = f"Error extracting {field_name}: {str(e)}"
                        extraction_errors.append(error_msg)
                        continue
            
            # Generate extraction summary
            extraction_summary = self._generate_extraction_summary(extracted_fields)
            
            return FieldExtractionResult(
                study_id=study_id,
                trial_id=trial_id,
                extracted_fields=extracted_fields,
                extraction_summary=extraction_summary,
                extraction_errors=extraction_errors
            )
            
        except Exception as e:
            extraction_errors.append(f"Critical extraction error: {str(e)}")
            return FieldExtractionResult(
                study_id=study_id,
                trial_id=trial_id,
                extraction_errors=extraction_errors
            )
    
    def _extract_single_field(self, field_name: str, field_def: Dict[str, Any], data: Dict[str, Any]) -> Optional[ExtractedField]:
        """Extract a single field based on its definition."""
        field_path = field_def["path"]
        field_type = field_def["type"]
        required = field_def.get("required", False)
        
        # Get field value
        field_value = self._get_field_value(data, field_path)
        
        if field_value is None:
            if required:
                return ExtractedField(
                    field_name=field_name,
                    field_path=field_path,
                    field_type=field_type,
                    value=None,
                    extraction_status=ExtractionStatus.MISSING,
                    confidence=0.0,
                    quality_notes=[f"Required field {field_name} is missing"]
                )
            else:
                return None
        
        # Validate and process field value
        validation_result = self._validate_field_value(field_value, field_type, field_name)
        
        # Extract evidence spans if applicable
        evidence_spans = []
        if field_type in [FieldType.ARRAY, FieldType.OBJECT] and isinstance(field_value, (list, dict)):
            evidence_spans = self.evidence_extractor.extract_evidence_spans(field_value, field_path)
        
        # Analyze tone if text field
        quality_notes = []
        if field_type == FieldType.TEXT and isinstance(field_value, str):
            tone_analysis = self.tone_analyzer.analyze_tone(field_value)
            if tone_analysis:
                quality_notes.append(f"Tone: {tone_analysis}")
        
        return ExtractedField(
            field_name=field_name,
            field_path=field_path,
            field_type=field_type,
            value=field_value,
            extraction_status=validation_result["status"],
            confidence=validation_result["confidence"],
            evidence_spans=evidence_spans,
            quality_notes=quality_notes
        )
    
    def _get_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get field value using dot notation path."""
        if not field_path:
            return None
        
        keys = field_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
            
            if current is None:
                return None
        
        return current
    
    def _validate_field_value(self, value: Any, expected_type: FieldType, field_name: str) -> Dict[str, Any]:
        """Validate field value against expected type."""
        validation_result = {
            "status": ExtractionStatus.INVALID,
            "confidence": 0.0,
            "notes": []
        }
        
        try:
            if expected_type == FieldType.TEXT:
                if isinstance(value, str) and value.strip():
                    validation_result["status"] = ExtractionStatus.EXTRACTED
                    validation_result["confidence"] = 1.0
                elif isinstance(value, str) and not value.strip():
                    validation_result["status"] = ExtractionStatus.PARTIAL
                    validation_result["confidence"] = 0.3
                    validation_result["notes"].append("Empty string value")
            
            elif expected_type == FieldType.NUMBER:
                if isinstance(value, (int, float)) and value is not None:
                    validation_result["status"] = ExtractionStatus.EXTRACTED
                    validation_result["confidence"] = 1.0
                else:
                    validation_result["status"] = ExtractionStatus.MISSING
                    validation_result["confidence"] = 0.0
            
            elif expected_type == FieldType.BOOLEAN:
                if isinstance(value, bool):
                    validation_result["status"] = ExtractionStatus.EXTRACTED
                    validation_result["confidence"] = 1.0
                else:
                    validation_result["status"] = ExtractionStatus.INVALID
                    validation_result["confidence"] = 0.0
            
            elif expected_type == FieldType.DATE:
                if self._is_valid_date(value):
                    validation_result["status"] = ExtractionStatus.EXTRACTED
                    validation_result["confidence"] = 1.0
                else:
                    validation_result["status"] = ExtractionStatus.INVALID
                    validation_result["confidence"] = 0.0
            
            elif expected_type == FieldType.ARRAY:
                if isinstance(value, list):
                    if len(value) > 0:
                        validation_result["status"] = ExtractionStatus.EXTRACTED
                        validation_result["confidence"] = 1.0
                    else:
                        validation_result["status"] = ExtractionStatus.PARTIAL
                        validation_result["confidence"] = 0.5
                        validation_result["notes"].append("Empty array")
                else:
                    validation_result["status"] = ExtractionStatus.INVALID
                    validation_result["confidence"] = 0.0
            
            elif expected_type == FieldType.OBJECT:
                if isinstance(value, dict):
                    if value:
                        validation_result["status"] = ExtractionStatus.EXTRACTED
                        validation_result["confidence"] = 1.0
                    else:
                        validation_result["status"] = ExtractionStatus.PARTIAL
                        validation_result["confidence"] = 0.5
                        validation_result["notes"].append("Empty object")
                else:
                    validation_result["status"] = ExtractionStatus.INVALID
                    validation_result["confidence"] = 0.0
            
            elif expected_type == FieldType.EVIDENCE:
                if self._has_evidence_content(value):
                    validation_result["status"] = ExtractionStatus.EXTRACTED
                    validation_result["confidence"] = 1.0
                else:
                    validation_result["status"] = ExtractionStatus.PARTIAL
                    validation_result["confidence"] = 0.5
                    validation_result["notes"].append("Limited evidence content")
            
        except Exception as e:
            validation_result["notes"].append(f"Validation error: {str(e)}")
            validation_result["confidence"] = 0.0
        
        return validation_result
    
    def _is_valid_date(self, value: Any) -> bool:
        """Check if value is a valid date."""
        if isinstance(value, str):
            # Try to parse common date formats
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
                r'\d{4}',               # YYYY
            ]
            for pattern in date_patterns:
                if re.match(pattern, value):
                    return True
        elif isinstance(value, (int, float)):
            # Could be timestamp
            return True
        return False
    
    def _has_evidence_content(self, value: Any) -> bool:
        """Check if value has meaningful evidence content."""
        if isinstance(value, dict):
            evidence_keys = ['loc', 'text_preview', 'evidence', 'source']
            return any(key in value and value[key] for key in evidence_keys)
        elif isinstance(value, list):
            return any(self._has_evidence_content(item) for item in value)
        return False
    
    def _generate_extraction_summary(self, extracted_fields: Dict[str, ExtractedField]) -> Dict[str, Any]:
        """Generate summary statistics for extracted fields."""
        total_fields = len(extracted_fields)
        extracted_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.EXTRACTED)
        partial_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.PARTIAL)
        missing_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.MISSING)
        invalid_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.INVALID)
        
        avg_confidence = sum(f.confidence for f in extracted_fields.values()) / total_fields if total_fields > 0 else 0.0
        
        return {
            "total_fields": total_fields,
            "extracted_count": extracted_count,
            "partial_count": partial_count,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "extraction_rate": extracted_count / total_fields if total_fields > 0 else 0.0,
            "avg_confidence": avg_confidence,
            "completeness_score": (extracted_count + partial_count * 0.5) / total_fields if total_fields > 0 else 0.0
        }
    
    def _create_empty_result(self, study_id: int, trial_id: int) -> FieldExtractionResult:
        """Create empty extraction result for missing data."""
        return FieldExtractionResult(
            study_id=study_id,
            trial_id=trial_id,
            extraction_summary={
                "total_fields": 0,
                "extracted_count": 0,
                "partial_count": 0,
                "missing_count": 0,
                "invalid_count": 0,
                "extraction_rate": 0.0,
                "avg_confidence": 0.0,
                "completeness_score": 0.0
            },
            extraction_errors=["No study card data available"]
        )


class EvidenceSpanExtractor:
    """Extracts evidence spans and data location information."""
    
    def extract_evidence_spans(self, data: Any, field_path: str) -> List[Dict[str, Any]]:
        """Extract evidence spans from field data."""
        evidence_spans = []
        
        if isinstance(data, dict):
            evidence_spans.extend(self._extract_from_dict(data, field_path))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    evidence_spans.extend(self._extract_from_dict(item, f"{field_path}[{i}]"))
        
        return evidence_spans
    
    def _extract_from_dict(self, data: Dict[str, Any], field_path: str) -> List[Dict[str, Any]]:
        """Extract evidence from dictionary data."""
        evidence_spans = []
        
        # Look for evidence fields
        evidence_fields = ['evidence', 'loc', 'text_preview', 'source', 'reference']
        
        for field in evidence_fields:
            if field in data and data[field]:
                evidence_span = {
                    "field_path": field_path,
                    "evidence_type": field,
                    "value": data[field],
                    "extracted_at": datetime.now()
                }
                evidence_spans.append(evidence_span)
        
        # Look for nested evidence
        for key, value in data.items():
            if isinstance(value, (dict, list)) and key not in evidence_fields:
                nested_spans = self.extract_evidence_spans(value, f"{field_path}.{key}")
                evidence_spans.extend(nested_spans)
        
        return evidence_spans


class ToneAnalyzer:
    """Analyzes tone and claim strength in text fields."""
    
    # Tone indicators
    CAUTIOUS_INDICATORS = [
        "may", "might", "could", "suggest", "indicate", "appear", "seem",
        "trend", "tendency", "potential", "possible", "likely", "probably"
    ]
    
    DEFINITIVE_INDICATORS = [
        "prove", "demonstrate", "establish", "confirm", "verify", "show",
        "conclude", "determine", "find", "reveal", "identify", "discover"
    ]
    
    def analyze_tone(self, text: str) -> Optional[str]:
        """Analyze the tone of text content."""
        if not text or not isinstance(text, str):
            return None
        
        text_lower = text.lower()
        
        cautious_count = sum(1 for indicator in self.CAUTIOUS_INDICATORS if indicator in text_lower)
        definitive_count = sum(1 for indicator in self.DEFINITIVE_INDICATORS if indicator in text_lower)
        
        if definitive_count > cautious_count:
            return "definitive"
        elif cautious_count > definitive_count:
            return "cautious"
        else:
            return "neutral"
