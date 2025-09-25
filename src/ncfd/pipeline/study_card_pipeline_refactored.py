"""
Refactored Study Card Pipeline using specialized services.

This is a simplified version of the study card pipeline that uses
the new service architecture instead of the monolithic approach.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from ncfd.extract.retrieval import build_retriever
from ncfd.ingest.pubmed.document_manager import DocumentManager
from ncfd.utils.config_manager import get_config_manager

from ncfd.extract.services import (
    DocumentPrioritizationService,
    StudyCardExtractionService,
    FactsheetExtractionService,
    PatternDetectionService,
    StudyCardPersistenceService,
    QualityGateValidationService,
    SignalEvaluationService
)

logger = logging.getLogger(__name__)


@dataclass
class StudyCardPipelineOutput:
    """Output of the study card pipeline."""
    success: bool
    start_time: datetime
    end_time: datetime
    trials_processed: int
    study_cards_generated: int
    factsheets_generated: int
    patterns_detected: int
    quotes_extracted: int
    errors: List[str]
    warnings: List[str]


class StudyCardPipelineRefactored:
    """
    Refactored Study Card Pipeline using specialized services.
    
    This pipeline orchestrates the following services:
    - DocumentPrioritizationService: Prioritizes documents for processing
    - StudyCardExtractionService: Extracts study cards using LLM
    - FactsheetExtractionService: Extracts factsheets using LLM
    - PatternDetectionService: Detects pattern families
    - StudyCardPersistenceService: Persists results to database
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the refactored study card pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.config_manager = get_config_manager()
        
        # Initialize services
        self.document_prioritization = DocumentPrioritizationService(config)
        self.study_card_extraction = StudyCardExtractionService(config)
        self.factsheet_extraction = FactsheetExtractionService(config)
        self.pattern_detection = PatternDetectionService(config)
        self.persistence = StudyCardPersistenceService(config)
        self.quality_validation = QualityGateValidationService(config)
        self.signal_evaluation = SignalEvaluationService(config)
        
        # Initialize retriever
        study_card_config = self.config_manager.get_section('study_card', config)
        self.retriever = build_retriever(study_card_config)
        self.document_manager = DocumentManager()
    
    async def execute(
        self, 
        trial_list: List[Dict[str, Any]], 
        entity_packs: Optional[List[Dict[str, Any]]] = None
    ) -> StudyCardPipelineOutput:
        """
        Execute the study card pipeline for a list of trials.
        
        Args:
            trial_list: List of trials to process
            entity_packs: Optional entity packs for context
            
        Returns:
            StudyCardPipelineOutput with results
        """
        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting refactored study card pipeline for {len(trial_list)} trials")
        
        errors = []
        warnings = []
        study_cards_generated = 0
        factsheets_generated = 0
        patterns_detected = 0
        quotes_extracted = 0
        
        try:
            for i, trial in enumerate(trial_list):
                trial_id = trial.get('trial_id')
                logger.info(f"Processing trial {i+1}/{len(trial_list)}: {trial_id}")
                
                try:
                    # Get entity pack from trial object or from entity_packs parameter
                    entity_pack = trial.get('entity_pack')
                    if not entity_pack and entity_packs and i < len(entity_packs):
                        entity_pack = entity_packs[i]
                    
                    # Process trial with enhanced services
                    trial_result = await self._process_single_trial_enhanced(trial, entity_pack)
                    
                    # Accumulate results
                    study_cards_generated += trial_result['study_cards']
                    factsheets_generated += trial_result['factsheets']
                    patterns_detected += trial_result['patterns']
                    quotes_extracted += trial_result['quotes']
                    
                    if trial_result['errors']:
                        errors.extend(trial_result['errors'])
                    if trial_result['warnings']:
                        warnings.extend(trial_result['warnings'])
                        
                except Exception as e:
                    error_msg = f"Error processing trial {trial_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
            
            end_time = datetime.now(timezone.utc)
            success = len(errors) == 0
            
            logger.info(f"Study card pipeline completed: {study_cards_generated} study cards, {factsheets_generated} factsheets, {patterns_detected} patterns")
            
            # Generate audit report
            self._generate_audit_report(trial_id, study_cards_generated, factsheets_generated, patterns_detected)
            
            return StudyCardPipelineOutput(
                success=success,
                start_time=start_time,
                end_time=end_time,
                trials_processed=len(trial_list),
                study_cards_generated=study_cards_generated,
                factsheets_generated=factsheets_generated,
                patterns_detected=patterns_detected,
                quotes_extracted=quotes_extracted,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            error_msg = f"Study card pipeline failed: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            
            return StudyCardPipelineOutput(
                success=False,
                start_time=start_time,
                end_time=end_time,
                trials_processed=len(trial_list),
                study_cards_generated=study_cards_generated,
                factsheets_generated=factsheets_generated,
                patterns_detected=patterns_detected,
                quotes_extracted=quotes_extracted,
                errors=errors,
                warnings=warnings
            )
    
    async def _process_single_trial_enhanced(
        self, 
        trial: Dict[str, Any], 
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a single trial through the enhanced pipeline with all services."""
        trial_id = trial.get('trial_id')
        errors = []
        warnings = []
        
        try:
            # Step 1: Retrieve documents
            logger.info(f"📚 Step 1: Retrieving documents for trial {trial_id}")
            documents = await self._retrieve_documents(trial, entity_pack)
            
            if not documents:
                logger.warning(f"⚠️ No documents found for trial {trial_id}")
                warnings.append(f"No documents found for trial {trial_id}")
                return {
                    'study_cards': 0,
                    'factsheets': 0,
                    'patterns': 0,
                    'quotes': 0,
                    'errors': errors,
                    'warnings': warnings
                }
            
            logger.info(f"✅ Retrieved {len(documents)} documents for trial {trial_id}")
            
            # Step 2: Apply document prioritization with enhanced logic
            logger.info(f"🎯 Step 2: Applying document prioritization for trial {trial_id}")
            raw_doc_texts = getattr(self, '_raw_doc_texts', {})
            prioritization_result = await self.document_prioritization.prioritize_documents(
                documents, raw_doc_texts, trial_id, trial, entity_pack
            )
            
            if not prioritization_result.prioritized_documents:
                warnings.append(f"No documents selected for processing for trial {trial_id}")
                return {
                    'study_cards': 0,
                    'factsheets': 0,
                    'patterns': 0,
                    'quotes': 0,
                    'errors': errors,
                    'warnings': warnings
                }
            
            # Step 3: Extract study cards
            logger.info(f"Extracting study cards for trial {trial_id}")
            study_card_result = await self.study_card_extraction.extract_study_cards(
                prioritization_result.prioritized_documents, trial_id, entity_pack
            )
            
            # Step 4: Extract factsheets
            logger.info(f"Extracting factsheets for trial {trial_id}")
            factsheet_result = await self.factsheet_extraction.extract_factsheets(
                prioritization_result.prioritized_documents, trial_id, entity_pack
            )
            
            # Step 5: Detect patterns
            logger.info(f"Detecting patterns for trial {trial_id}")
            pattern_result = await self.pattern_detection.detect_patterns(
                study_card_result.study_cards,
                factsheet_result.factsheets,
                trial_id
            )
            
            # Step 6: Quality gate validation
            logger.info(f"Validating quality for trial {trial_id}")
            
            # Extract quotes from factsheet provenance
            extracted_quotes = self._extract_quotes_from_factsheets(factsheet_result.factsheets, trial_id)
            
            quality_result = await self.quality_validation.validate_study_card_quality(
                study_card_result.study_cards,
                factsheet_result.factsheets,
                pattern_result.detected_patterns,
                extracted_quotes,
                trial_id
            )
            
            if not quality_result.is_valid:
                errors.extend(quality_result.validation_errors)
                warnings.extend(quality_result.validation_warnings)
                
                # Check if we should fail hard or just warn
                if self.config.get('quality_gate', {}).get('fail_on_validation', True):
                    logger.error(f"Trial {trial_id} failed quality gate validation")
                    return {
                        'study_cards': 0,
                        'factsheets': 0,
                        'patterns': 0,
                        'quotes': 0,
                        'errors': errors,
                        'warnings': warnings
                    }
                else:
                    logger.warning(f"Trial {trial_id} has quality gate violations but continuing")
            
            # Step 7: Evaluate signals and gates
            logger.info(f"Evaluating signals and gates for trial {trial_id}")
            signal_result = await self.signal_evaluation.evaluate_signals_and_gates(
                trial_id=trial_id,
                study_cards=study_card_result.study_cards,
                factsheets=factsheet_result.factsheets,
                patterns=pattern_result.detected_patterns,
                trial_versions=[]  # Would be populated from trial tracking
            )
            
            if signal_result.success:
                logger.info(f"Signal evaluation completed for trial {trial_id}: "
                           f"{len(signal_result.fired_signals)} signals fired, "
                           f"{len(signal_result.fired_gates)} gates fired, "
                           f"P_fail={signal_result.p_fail:.3f}")
            else:
                logger.warning(f"Signal evaluation failed for trial {trial_id}: {signal_result.errors}")
            
            # Step 8: Persist results
            logger.info(f"Persisting results for trial {trial_id}")
            persistence_result = await self.persistence.persist_results(
                study_card_result.study_cards,
                factsheet_result.factsheets,
                pattern_result.detected_patterns,
                [],  # Quotes would be extracted separately
                trial_id
            )
            
            # Collect errors and warnings
            errors.extend(study_card_result.extraction_errors)
            errors.extend(factsheet_result.extraction_errors)
            errors.extend(pattern_result.detection_errors)
            errors.extend(persistence_result.persistence_errors)
            
            warnings.extend(prioritization_result.selection_reason)
            warnings.extend(quality_result.validation_warnings)
            
            return {
                'study_cards': study_card_result.successful_extractions,
                'factsheets': factsheet_result.successful_extractions,
                'patterns': pattern_result.successful_detections,
                'quotes': 0,  # Would be extracted separately
                'errors': errors,
                'warnings': warnings
            }
            
        except Exception as e:
            error_msg = f"Error processing trial {trial_id}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            
            return {
                'study_cards': 0,
                'factsheets': 0,
                'patterns': 0,
                'quotes': 0,
                'errors': errors,
                'warnings': warnings
            }
    
    async def _process_single_trial(
        self, 
        trial: Dict[str, Any], 
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a single trial through the pipeline."""
        trial_id = trial.get('trial_id')
        errors = []
        warnings = []
        
        try:
            # Step 1: Retrieve documents
            logger.info(f"Retrieving documents for trial {trial_id}")
            documents = await self._retrieve_documents(trial, entity_pack)
            
            if not documents:
                warnings.append(f"No documents found for trial {trial_id}")
                return {
                    'study_cards': 0,
                    'factsheets': 0,
                    'patterns': 0,
                    'quotes': 0,
                    'errors': errors,
                    'warnings': warnings
                }
            
            # Step 2: Prioritize documents
            logger.info(f"Prioritizing {len(documents)} documents for trial {trial_id}")
            prioritization_result = self.document_prioritization.prioritize_documents(
                documents, trial_id, entity_pack
            )
            
            if not prioritization_result.prioritized_documents:
                warnings.append(f"No documents selected for processing for trial {trial_id}")
                return {
                    'study_cards': 0,
                    'factsheets': 0,
                    'patterns': 0,
                    'quotes': 0,
                    'errors': errors,
                    'warnings': warnings
                }
            
            # Step 3: Extract study cards
            logger.info(f"Extracting study cards for trial {trial_id}")
            study_card_result = await self.study_card_extraction.extract_study_cards(
                prioritization_result.prioritized_documents, trial_id, entity_pack
            )
            
            # Step 4: Extract factsheets
            logger.info(f"Extracting factsheets for trial {trial_id}")
            factsheet_result = await self.factsheet_extraction.extract_factsheets(
                prioritization_result.prioritized_documents, trial_id, entity_pack
            )
            
            # Step 5: Detect patterns
            logger.info(f"Detecting patterns for trial {trial_id}")
            pattern_result = await self.pattern_detection.detect_patterns(
                study_card_result.study_cards,
                factsheet_result.factsheets,
                trial_id
            )
            
            # Step 6: Persist results
            logger.info(f"Persisting results for trial {trial_id}")
            persistence_result = await self.persistence.persist_results(
                study_card_result.study_cards,
                factsheet_result.factsheets,
                pattern_result.detected_patterns,
                [],  # Quotes would be extracted separately
                trial_id
            )
            
            # Collect errors and warnings
            errors.extend(study_card_result.extraction_errors)
            errors.extend(factsheet_result.extraction_errors)
            errors.extend(pattern_result.detection_errors)
            errors.extend(persistence_result.persistence_errors)
            
            warnings.extend(prioritization_result.selection_reason)
            
            return {
                'study_cards': study_card_result.successful_extractions,
                'factsheets': factsheet_result.successful_extractions,
                'patterns': pattern_result.successful_detections,
                'quotes': 0,  # Would be extracted separately
                'errors': errors,
                'warnings': warnings
            }
            
        except Exception as e:
            error_msg = f"Error processing trial {trial_id}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            
            return {
                'study_cards': 0,
                'factsheets': 0,
                'patterns': 0,
                'quotes': 0,
                'errors': errors,
                'warnings': warnings
            }
    
    async def _retrieve_documents(
        self, 
        trial: Dict[str, Any], 
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve documents for a trial."""
        try:
            # Use the retriever to get documents
            trial_id = trial.get('trial_id')
            nct_id = trial.get('nct_id')
            
            # Build trial context for the retriever
            trial_context = {
                'trial_id': trial_id,
                'nct_id': nct_id,
                'entity_pack': entity_pack,
                **trial  # Include all trial data
            }
            
            # Retrieve documents using the retriever's process method
            inputs = {
                "trial_context": trial_context,
                "date_window": trial_context.get("date_window", "2020-2024"),
                "use_real_retrieval": True
            }
            
            result = self.retriever.process(inputs)
            
            # Extract document cards and raw texts from the result
            documents = result.output.get('document_cards', []) if result.output else []
            raw_doc_texts = result.output.get('raw_doc_texts', {}) if result.output else {}
            
            # Store raw texts for later use in prioritization
            self._raw_doc_texts = raw_doc_texts
            
            return documents
            
        except Exception as e:
            logger.error(f"Error retrieving documents for trial {trial.get('trial_id')}: {e}")
            return []
    
    def _extract_quotes_from_factsheets(self, factsheets: List[Dict[str, Any]], trial_id: str) -> List[Dict[str, Any]]:
        """Extract quotes from factsheet provenance for quality validation."""
        extracted_quotes = []
        
        for factsheet in factsheets:
            if not isinstance(factsheet, dict):
                continue
                
            provenance = factsheet.get('provenance', {})
            document_id = factsheet.get('document_id', 'unknown')
            
            # Extract quotes from each field's provenance
            for field_name, field_provenance in provenance.items():
                if isinstance(field_provenance, dict) and 'quotes' in field_provenance:
                    quotes = field_provenance['quotes']
                    if isinstance(quotes, list):
                        for quote in quotes:
                            if isinstance(quote, dict) and 'text' in quote:
                                extracted_quotes.append({
                                    'trial_id': trial_id,
                                    'document_id': document_id,
                                    'field_name': field_name,
                                    'text': quote['text'],
                                    'confidence': quote.get('confidence', 0.8),
                                    'location': quote.get('loc', {})
                                })
        
        logger.info(f"Extracted {len(extracted_quotes)} quotes from {len(factsheets)} factsheets")
        return extracted_quotes
    
    def _generate_audit_report(self, trial_id: str, study_cards_count: int, factsheets_count: int, patterns_count: int):
        """Generate audit report for subgroup/endpoint analysis."""
        try:
            import json
            
            audit = {
                "trial_id": trial_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "study_cards": study_cards_count,
                    "factsheets": factsheets_count,
                    "patterns": patterns_count
                },
                "endpoint_changes": [],
                "subgroup_claims": [],
                "signal_summary": {}
            }
            
            # Query database for analysis claims
            from ncfd.db.session import session_scope
            from ncfd.db.models import Factsheet
            
            with session_scope() as session:
                
                # Get factsheets for this trial
                from sqlalchemy import text
                # Simple approach: get all factsheets and filter by trial
                factsheets = session.query(Factsheet).all()
                
                # Extract analysis claims
                for factsheet in factsheets:
                    claims = factsheet.analysis_claims or []
                    for claim in claims:
                        audit["subgroup_claims"].append({
                            "subgroup": claim.get('subgroup', {}).get('label', 'Unknown'),
                            "p_value": claim.get('subgroup_result', {}).get('p_value'),
                            "adjusted": claim.get('subgroup_result', {}).get('adjusted', True),
                            "nominal": claim.get('subgroup_result', {}).get('is_nominal', False),
                            "prespecified": claim.get('subgroup', {}).get('prespecified', True),
                            "analysis_set": claim.get('analysis_set', 'Unknown'),
                            "evidence_tier": claim.get('evidence_strength', 'unknown'),
                            "quote": claim.get('quote_spans', [{}])[0].get('text', '')[:200] if claim.get('quote_spans') else ''
                        })
            
            # Log audit summary
            logger.info("🔍 SUBGROUP/ENDPOINT AUDIT:")
            logger.info(f"  Endpoint Changes: {len(audit['endpoint_changes'])}")
            logger.info(f"  Subgroup Claims: {len(audit['subgroup_claims'])}")
            
            for claim in audit['subgroup_claims']:
                logger.info(f"    • {claim['subgroup']}: p={claim['p_value']}, adjusted={claim['adjusted']}, nominal={claim['nominal']}")
            
            # Save to file
            import os
            os.makedirs("tests/logs", exist_ok=True)
            with open(f"tests/logs/subgroup_audit_{trial_id}.json", "w") as f:
                json.dump(audit, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to generate audit report: {e}")
