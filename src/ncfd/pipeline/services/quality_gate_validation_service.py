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
        logger.info(f"Validating study card quality for trial {trial_id}")
        
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
            required_fields = ['trial_id', 'document_id', 'summary']
            for field in required_fields:
                if field not in study_card or not study_card[field]:
                    errors.append(f"Study card {i} missing required field: {field}")
            
            # Check content quality
            if 'summary' in study_card and study_card['summary']:
                summary_length = len(study_card['summary'])
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
        """Validate factsheet quality."""
        errors = []
        warnings = []
        score = 0.0
        
        if not factsheets:
            errors.append("No factsheets found")
            return {'errors': errors, 'warnings': warnings, 'score': 0.0}
        
        # Check factsheet structure
        for i, factsheet in enumerate(factsheets):
            if not isinstance(factsheet, dict):
                errors.append(f"Factsheet {i} is not a dictionary")
                continue
            
            # Check required fields
            required_fields = ['trial_id', 'document_id', 'summary']
            for field in required_fields:
                if field not in factsheet or not factsheet[field]:
                    errors.append(f"Factsheet {i} missing required field: {field}")
            
            # Check content quality
            if 'summary' in factsheet and factsheet['summary']:
                summary_length = len(factsheet['summary'])
                if summary_length < 50:
                    warnings.append(f"Factsheet {i} summary too short: {summary_length} characters")
                elif summary_length > 1000:
                    warnings.append(f"Factsheet {i} summary too long: {summary_length} characters")
                else:
                    score += 0.25  # Good summary length
        
        # Check minimum count
        if len(factsheets) >= self.min_factsheets:
            score += 0.5
        else:
            errors.append(f"Insufficient factsheets: {len(factsheets)} < {self.min_factsheets}")
        
        return {'errors': errors, 'warnings': warnings, 'score': score}
    
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
            required_fields = ['trial_id', 'document_id', 'pattern_type']
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
                elif text_length > 500:
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
                # Create a gate record for the overall quality gate
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
                
                # Create gate assessment record
                gate_assessment = GateAssessment(
                    gate_id=f"G1_{trial_id}",
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
