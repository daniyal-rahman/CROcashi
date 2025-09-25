"""
Quality Gate Validation Service for Study Card Pipeline.

Handles quality validation of study cards, factsheets, and patterns.
This service extracts the quality gate validation logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from ncfd.db.session import session_scope
from ncfd.db.models import Gate, GateAssessment

logger = logging.getLogger(__name__)


@dataclass
class QualityValidationResult:
    """Result of quality gate validation."""
    is_valid: bool
    validation_errors: List[str]
    validation_warnings: List[str]
    quality_score: float
    validation_details: Dict[str, Any]


class QualityGateValidationService:
    """
    Service for validating study card pipeline outputs.
    
    This service handles:
    - Study card quality validation
    - Factsheet quality validation
    - Pattern detection quality validation
    - Overall pipeline quality assessment
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the quality gate validation service.
        
        Args:
            config: Configuration dictionary with validation settings
        """
        self.config = config
        self.validation_config = config.get('quality_gate', {})
        
        # Configuration values
        self.min_quotes = self.validation_config.get('min_quotes', 3)
        self.min_llm_artifacts = self.validation_config.get('min_llm_artifacts', 1)
        self.min_study_cards = self.validation_config.get('min_study_cards', 1)
        self.min_factsheets = self.validation_config.get('min_factsheets', 1)
        self.min_patterns = self.validation_config.get('min_patterns', 0)
        self.fail_on_validation = self.validation_config.get('fail_on_validation', True)
    
    async def validate_study_card_quality(
        self, 
        study_cards: List[Dict[str, Any]], 
        factsheets: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        quotes: List[Dict[str, Any]],
        trial_id: str
    ) -> QualityValidationResult:
        """
        Validate the quality of study card pipeline outputs.
        
        Args:
            study_cards: List of extracted study cards
            factsheets: List of extracted factsheets
            patterns: List of detected patterns
            quotes: List of extracted quotes
            trial_id: Trial ID for context
            
        Returns:
            QualityValidationResult with validation results
        """
        logger.info(f"🔍 Starting quality validation for trial {trial_id}: {len(study_cards)} study cards, {len(factsheets)} factsheets, {len(patterns)} patterns, {len(quotes)} quotes")
        
        validation_errors = []
        validation_warnings = []
        quality_score = 0.0
        validation_details = {}
        
        try:
            # Validate study cards
            study_card_validation = self._validate_study_cards(study_cards)
            validation_errors.extend(study_card_validation['errors'])
            validation_warnings.extend(study_card_validation['warnings'])
            quality_score += study_card_validation['score']
            validation_details['study_cards'] = study_card_validation
            
            # Validate factsheets
            factsheet_validation = self._validate_factsheets(factsheets)
            validation_errors.extend(factsheet_validation['errors'])
            validation_warnings.extend(factsheet_validation['warnings'])
            quality_score += factsheet_validation['score']
            validation_details['factsheets'] = factsheet_validation
            
            # Validate patterns
            pattern_validation = self._validate_patterns(patterns)
            validation_errors.extend(pattern_validation['errors'])
            validation_warnings.extend(pattern_validation['warnings'])
            quality_score += pattern_validation['score']
            validation_details['patterns'] = pattern_validation
            
            # Validate quotes
            quote_validation = self._validate_quotes(quotes)
            validation_errors.extend(quote_validation['errors'])
            validation_warnings.extend(quote_validation['warnings'])
            quality_score += quote_validation['score']
            validation_details['quotes'] = quote_validation
            
            # Calculate overall quality score
            total_components = 4  # study_cards, factsheets, patterns, quotes
            quality_score = quality_score / total_components
            
            # Determine if validation passed
            is_valid = len(validation_errors) == 0
            
            # Add overall validation warnings
            if quality_score < 0.5:
                validation_warnings.append(f"Overall quality score is low: {quality_score:.2f}")
            
            if len(study_cards) < self.min_study_cards:
                validation_errors.append(f"Insufficient study cards: {len(study_cards)} < {self.min_study_cards}")
            
            if len(factsheets) < self.min_factsheets:
                validation_errors.append(f"Insufficient factsheets: {len(factsheets)} < {self.min_factsheets}")
            
            if len(quotes) < self.min_quotes:
                validation_errors.append(f"Insufficient quotes: {len(quotes)} < {self.min_quotes}")
            
            logger.info(f"Quality validation completed: valid={is_valid}, score={quality_score:.2f}, errors={len(validation_errors)}")
            
            # Persist gate assessments to database
            try:
                await self._persist_gate_assessments(trial_id, is_valid, quality_score, validation_details)
            except Exception as e:
                logger.error(f"Error persisting gate assessments: {e}")
                validation_warnings.append(f"Gate persistence failed: {str(e)}")
            
            logger.info(f"✅ Quality validation completed for trial {trial_id}: {'PASSED' if is_valid else 'FAILED'} (score: {quality_score:.2f})")
            
            return QualityValidationResult(
                is_valid=is_valid,
                validation_errors=validation_errors,
                validation_warnings=validation_warnings,
                quality_score=quality_score,
                validation_details=validation_details
            )
            
        except Exception as e:
            error_msg = f"Error during quality validation: {str(e)}"
            validation_errors.append(error_msg)
            logger.error(error_msg)
            
            return QualityValidationResult(
                is_valid=False,
                validation_errors=validation_errors,
                validation_warnings=validation_warnings,
                quality_score=0.0,
                validation_details=validation_details
            )
    
    def _validate_study_cards(self, study_cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate study card quality."""
        errors = []
        warnings = []
        score = 0.0
        
        if not study_cards:
            errors.append("No study cards found")
            return {'errors': errors, 'warnings': warnings, 'score': 0.0}
        
        # Check study card structure
        for i, study_card in enumerate(study_cards):
            if not isinstance(study_card, dict):
                errors.append(f"Study card {i} is not a dictionary")
                continue
            
            # Check required fields
            required_fields = ['trial_id', 'document_id', 'summary_text']
            for field in required_fields:
                if field not in study_card or not study_card[field]:
                    errors.append(f"Study card {i} missing required field: {field}")
            
            # Check content quality
            if 'summary_text' in study_card and study_card['summary_text']:
                summary_length = len(study_card['summary_text'])
                if summary_length < 50:
                    warnings.append(f"Study card {i} summary too short: {summary_length} characters")
                elif summary_length > 1000:
                    warnings.append(f"Study card {i} summary too long: {summary_length} characters")
                else:
                    score += 0.25  # Good summary length
        
        # Check minimum count
        if len(study_cards) >= self.min_study_cards:
            score += 0.5
        else:
            errors.append(f"Insufficient study cards: {len(study_cards)} < {self.min_study_cards}")
        
        return {'errors': errors, 'warnings': warnings, 'score': score}
    
    def _validate_factsheets(self, factsheets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate factsheet quality using content-agnostic quality gates."""
        errors = []
        warnings = []
        score = 0.0
        
        if not factsheets:
            errors.append("No factsheets found")
            return {'errors': errors, 'warnings': warnings, 'score': 0.0}
        
        # Check factsheet structure and quality gates
        for i, factsheet in enumerate(factsheets):
            if not isinstance(factsheet, dict):
                errors.append(f"Factsheet {i} is not a dictionary")
                continue
            
            # Debug logging to see what we're receiving
            logger.info(f"🔍 DEBUG: Quality validation factsheet {i}:")
            logger.info(f"  keys: {list(factsheet.keys())}")
            logger.info(f"  study_type: {factsheet.get('study_type')}")
            logger.info(f"  factsheet_sections: {factsheet.get('factsheet_sections', {})}")
            logger.info(f"  provenance: {factsheet.get('provenance', {})}")
            
            # G1.HasContent: Check if factsheet has meaningful content
            if not self._has_meaningful_factsheet_content(factsheet):
                errors.append(f"Factsheet {i} has no meaningful content")
                continue
            
            # G2.HasProvenance: Check if populated fields have provenance
            if not self._has_provenance_for_content(factsheet):
                errors.append(f"Factsheet {i} content lacks provenance")
                continue
            
            # G3.No-Contradiction: Check for contradictions
            contradiction_reason = self._check_factsheet_contradictions(factsheet)
            if contradiction_reason:
                errors.append(f"Factsheet {i} contradiction: {contradiction_reason}")
                continue
            
            # G4.Scope-Consistent: Check study type consistency
            scope_reason = self._check_factsheet_scope_consistency(factsheet)
            if scope_reason:
                warnings.append(f"Factsheet {i} scope inconsistency: {scope_reason}")
            
            # Calculate score based on content quality
            score += self._calculate_factsheet_score(factsheet)
        
        # Check minimum count
        if len(factsheets) >= self.min_factsheets:
            score += 0.5
        else:
            errors.append(f"Insufficient factsheets: {len(factsheets)} < {self.min_factsheets}")
        
        # Normalize score
        if factsheets:
            score = score / len(factsheets)
        
        return {'errors': errors, 'warnings': warnings, 'score': score}
    
    def _has_meaningful_factsheet_content(self, factsheet: Dict[str, Any]) -> bool:
        """Check if factsheet has meaningful content (G1.HasContent)."""
        # Check new JSONB sections
        factsheet_sections = factsheet.get('factsheet_sections', {})
        meaningful_fields = [
            'key_findings', 'efficacy_data', 'safety_data', 
            'mechanism_data', 'biomarker_data', 'dosing_data',
            'population_data', 'limitations'
        ]
        
        # Check both lowercase and uppercase field names
        for field in meaningful_fields:
            # Check lowercase
            if factsheet_sections.get(field) and str(factsheet_sections[field]).strip():
                return True
            # Check uppercase
            upper_field = field.upper()
            if factsheet_sections.get(upper_field) and str(factsheet_sections[upper_field]).strip():
                return True
        
        # Check legacy fields for backward compatibility
        legacy_fields = ['results', 'primary_endpoint_results', 'safety_results']
        for field in legacy_fields:
            if factsheet.get(field) and str(factsheet[field]).strip():
                return True
        
        return False
    
    def _has_provenance_for_content(self, factsheet: Dict[str, Any]) -> bool:
        """Check if factsheet content has provenance (G2.HasProvenance)."""
        provenance = factsheet.get('provenance', {})
        factsheet_sections = factsheet.get('factsheet_sections', {})
        
        # Count fields with content and fields with provenance
        total_content_fields = 0
        fields_with_provenance = 0
        
        # Check if each populated field has provenance
        for field, value in factsheet_sections.items():
            if value and str(value).strip():
                total_content_fields += 1
                
                # Check both exact field name and case variations
                field_provenance = provenance.get(field) or provenance.get(field.lower()) or provenance.get(field.upper())
                
                if field_provenance and field_provenance.get('quotes'):
                    fields_with_provenance += 1
        
        # Require 80% traceback threshold as requested
        if total_content_fields == 0:
            return True  # No content to trace back
        
        traceback_percentage = fields_with_provenance / total_content_fields
        logger.info(f"Provenance traceback: {fields_with_provenance}/{total_content_fields} = {traceback_percentage:.1%}")
        
        return traceback_percentage >= 0.8
    
    def _check_factsheet_contradictions(self, factsheet: Dict[str, Any]) -> Optional[str]:
        """Check for contradictions in factsheet (G3.No-Contradiction)."""
        factsheet_sections = factsheet.get('factsheet_sections', {})
        
        # Check for contradiction between "no safety data" and populated safety_data
        safety_data = factsheet_sections.get('safety_data', '')
        if 'no safety data' in str(safety_data).lower() and safety_data.strip():
            return "Claims 'no safety data' but safety_data is populated"
        
        # Check for contradiction between "no efficacy data" and populated efficacy_data
        efficacy_data = factsheet_sections.get('efficacy_data', '')
        if 'no efficacy data' in str(efficacy_data).lower() and efficacy_data.strip():
            return "Claims 'no efficacy data' but efficacy_data is populated"
        
        return None
    
    def _check_factsheet_scope_consistency(self, factsheet: Dict[str, Any]) -> Optional[str]:
        """Check study type consistency (G4.Scope-Consistent)."""
        study_type = factsheet.get('study_type', '')
        factsheet_sections = factsheet.get('factsheet_sections', {})
        
        # If preclinical study but has clinical enrollment data
        if study_type == 'preclinical' and factsheet_sections.get('total_enrolled'):
            return "Preclinical study has clinical enrollment data"
        
        # If clinical study but has preclinical-specific data
        if study_type == 'clinical_trial' and factsheet_sections.get('dosing_data'):
            dosing_data = str(factsheet_sections['dosing_data']).lower()
            if 'mg/kg' in dosing_data or 'animal' in dosing_data:
                return "Clinical study has preclinical dosing data"
        
        return None
    
    def _calculate_factsheet_score(self, factsheet: Dict[str, Any]) -> float:
        """Calculate quality score for a factsheet."""
        score = 0.0
        factsheet_sections = factsheet.get('factsheet_sections', {})
        
        # Base score for having content
        if self._has_meaningful_factsheet_content(factsheet):
            score += 0.5
        
        # Bonus for provenance
        if self._has_provenance_for_content(factsheet):
            score += 0.3
        
        # Bonus for normalized facts
        if factsheet.get('normalized_facts'):
            score += 0.2
        
        return min(score, 1.0)
    
    def _validate_patterns(self, patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate pattern detection quality."""
        errors = []
        warnings = []
        score = 0.0
        
        if not patterns:
            warnings.append("No patterns detected")
            return {'errors': errors, 'warnings': warnings, 'score': 0.5}  # Not critical
        
        # Check pattern structure
        for i, pattern in enumerate(patterns):
            if not isinstance(pattern, dict):
                errors.append(f"Pattern {i} is not a dictionary")
                continue
            
            # Check required fields
            required_fields = ['trial_id', 'document_id', 'family_id', 'pattern_id']
            for field in required_fields:
                if field not in pattern or not pattern[field]:
                    errors.append(f"Pattern {i} missing required field: {field}")
        
        # Check minimum count
        if len(patterns) >= self.min_patterns:
            score += 0.5
        else:
            warnings.append(f"Few patterns detected: {len(patterns)} < {self.min_patterns}")
        
        return {'errors': errors, 'warnings': warnings, 'score': score}
    
    def _validate_quotes(self, quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate quote extraction quality."""
        errors = []
        warnings = []
        score = 0.0
        
        if not quotes:
            errors.append("No quotes found")
            return {'errors': errors, 'warnings': warnings, 'score': 0.0}
        
        # Check quote structure
        for i, quote in enumerate(quotes):
            if not isinstance(quote, dict):
                errors.append(f"Quote {i} is not a dictionary")
                continue
            
            # Check required fields
            required_fields = ['trial_id', 'document_id', 'text']
            for field in required_fields:
                if field not in quote or not quote[field]:
                    errors.append(f"Quote {i} missing required field: {field}")
            
            # Check content quality
            if 'text' in quote and quote['text']:
                text_length = len(quote['text'])
                if text_length < 10:
                    warnings.append(f"Quote {i} text too short: {text_length} characters")
                elif text_length > 1000:  # Increased from 500 to 1000 as requested
                    warnings.append(f"Quote {i} text too long: {text_length} characters")
                else:
                    score += 0.1  # Good quote length
        
        # Check minimum count
        if len(quotes) >= self.min_quotes:
            score += 0.5
        else:
            errors.append(f"Insufficient quotes: {len(quotes)} < {self.min_quotes}")
        
        return {'errors': errors, 'warnings': warnings, 'score': score}
    
    async def _persist_gate_assessments(self, trial_id: str, is_valid: bool, quality_score: float, validation_details: Dict[str, Any]) -> None:
        """Persist gate assessments to database."""
        try:
            with session_scope() as session:
                # Check if gate record already exists
                existing_gate = session.query(Gate).filter(
                    Gate.trial_id == int(trial_id),
                    Gate.g_id == 'G1',
                    Gate.run_id == 'refactored_pipeline'
                ).first()
                
                if existing_gate:
                    # Update existing gate record
                    existing_gate.fired_bool = is_valid
                    existing_gate.rationale_text = f"Overall quality validation: score={quality_score:.2f}, valid={is_valid}"
                else:
                    # Create new gate record
                    gate_record = Gate(
                        trial_id=int(trial_id),
                        run_id='refactored_pipeline',
                        g_id='G1',  # Overall quality gate
                        fired_bool=is_valid,
                        supporting_s_ids=[],  # No specific signal IDs for overall gate
                        lr_used=None,
                        rationale_text=f"Overall quality validation: score={quality_score:.2f}, valid={is_valid}"
                    )
                    session.add(gate_record)
                
                # Create gate assessment record (handle duplicates)
                gate_id = f"G1_{trial_id}"
                
                # Check if assessment already exists
                existing_assessment = session.query(GateAssessment).filter(
                    GateAssessment.gate_id == gate_id
                ).first()
                
                if existing_assessment:
                    # Update existing assessment
                    existing_assessment.status = 'PASS' if is_valid else 'FAIL'
                    existing_assessment.p_gate = quality_score
                    existing_assessment.rationale = {
                        'overall_score': quality_score,
                        'is_valid': is_valid,
                        'validation_details': validation_details
                    }
                    existing_assessment.confidence_in_assessment = quality_score
                    existing_assessment.assessment_notes = {
                        'study_cards_count': validation_details.get('study_cards', {}).get('count', 0),
                        'factsheets_count': validation_details.get('factsheets', {}).get('count', 0),
                        'patterns_count': validation_details.get('patterns', {}).get('count', 0),
                        'quotes_count': validation_details.get('quotes', {}).get('count', 0)
                    }
                    existing_assessment.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new assessment
                    gate_assessment = GateAssessment(
                        gate_id=gate_id,
                        status='PASS' if is_valid else 'FAIL',
                        p_gate=quality_score,
                        rationale={
                            'overall_score': quality_score,
                            'is_valid': is_valid,
                            'validation_details': validation_details
                        },
                        assessment_method='refactored_pipeline',
                        confidence_in_assessment=quality_score,
                        assessment_notes={
                            'study_cards_count': validation_details.get('study_cards', {}).get('count', 0),
                            'factsheets_count': validation_details.get('factsheets', {}).get('count', 0),
                            'patterns_count': validation_details.get('patterns', {}).get('count', 0),
                            'quotes_count': validation_details.get('quotes', {}).get('count', 0)
                        },
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    session.add(gate_assessment)
                
                session.commit()
                logger.info(f"Persisted gate assessment for trial {trial_id}: G1={'PASS' if is_valid else 'FAIL'}")
                
        except Exception as e:
            logger.error(f"Error persisting gate assessments for trial {trial_id}: {e}")
            raise
