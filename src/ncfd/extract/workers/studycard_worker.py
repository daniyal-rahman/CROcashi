"""
Study Card stage worker for STUDYCARD tasks.

Handles study card generation from full-text documents.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ...ingest.pubmed.db_service import PubMedDBService, get_db_service
from ...ingest.pubmed.queue_service import TaskQueueService
from ...db.session import session_scope
from ...db.models import Document, DocumentText, TrialDocCandidate, Trial, Company
from ...db.study_card_models import MethodCard, ResultsFactsheet, GateAssessment, EvidenceSpan
from ...pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class StudyCardWorkerResult:
    """Result from Study Card worker execution."""
    task_id: int
    trial_id: int
    success: bool
    documents_processed: int = 0
    study_cards_generated: int = 0
    method_cards: int = 0
    results_cards: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None


class StudyCardWorker:
    """Worker for processing STUDYCARD tasks."""
    
    def __init__(
        self,
        queue_service: TaskQueueService,
        config: Optional[Dict] = None
    ):
        """
        Initialize Study Card worker.
        
        Args:
            queue_service: Task queue service instance
            config: Configuration dictionary
        """
        self.queue_service = queue_service
        self.config = config or {}
        
        # Initialize database service
        self.db_service = get_db_service()
        
        # Initialize the direct study card pipeline
        pipeline_config = config.get('study_card', {})
        self.orchestrator = PipelineOrchestrator(pipeline_config)
        
        # Study card settings
        self.batch_size = self.config.get('batch_size', 3)
        self.max_retries = self.config.get('max_retries', 2)
        self.retry_delay = self.config.get('retry_delay', 60)
        self.enable_method_cards = self.config.get('enable_method_cards', True)
        self.enable_results_cards = self.config.get('enable_results_cards', True)
        self.min_confidence_threshold = self.config.get('min_confidence_threshold', 0.7)
        
        # Document prioritization and rate limiting settings
        self.max_documents_per_trial = self.config.get('max_documents_per_trial', 20)
        self.max_documents_per_batch = self.config.get('max_documents_per_batch', 5)
        self.enable_fallback_processing = self.config.get('enable_fallback_processing', True)
        self.max_fallback_documents = self.config.get('max_fallback_documents', 5)
        
        # Prioritization thresholds
        self.high_priority_r_threshold = self.config.get('high_priority_r_threshold', 0.6)
        self.high_priority_s_threshold = self.config.get('high_priority_s_threshold', 0.6)
        self.medium_priority_r_threshold = self.config.get('medium_priority_r_threshold', 0.4)
        self.medium_priority_s_threshold = self.config.get('medium_priority_s_threshold', 0.4)
        self.full_text_preference_threshold = self.config.get('full_text_preference_threshold', 1.0)
        
        self.logger = logger
    
    async def process_studycard_task(self, task_data: Dict[str, Any]) -> StudyCardWorkerResult:
        """
        Process a single STUDYCARD task.
        
        Args:
            task_data: Task data from queue
            
        Returns:
            StudyCardWorkerResult with execution details
        """
        start_time = datetime.now(timezone.utc)
        task_id = task_data['id']
        trial_id = task_data['trial_id']
        
        try:
            self.logger.info(f"Processing Study Card task {task_id} for trial {trial_id}")
            
            # Get prioritized documents for this trial
            prioritized_documents, processing_stats = await self._get_prioritized_documents(trial_id)
            
            if not prioritized_documents:
                self.logger.warning(f"No documents found for trial {trial_id}")
                return StudyCardWorkerResult(
                    task_id=task_id,
                    trial_id=trial_id,
                    success=True,
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    error_message="No documents found for processing"
                )
            
            self.logger.info(f"Found {len(prioritized_documents)} prioritized documents for study card generation")
            self.logger.info(f"Processing stats: {processing_stats}")
            
            # Process documents in batches
            results = await self._process_documents_batch(trial_id, prioritized_documents)
            
            # Update trial state
            if results['success']:
                await self._update_trial_state(trial_id, results)
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return StudyCardWorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=results['success'],
                documents_processed=results['documents_processed'],
                study_cards_generated=results['study_cards_generated'],
                method_cards=results['method_cards'],
                results_cards=results['results_cards'],
                gates_passed=results['gates_passed'],
                gates_failed=results['gates_failed'],
                execution_time=execution_time,
                error_message=results.get('error_message')
            )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Unexpected error processing Study Card task {task_id}: {e}"
            self.logger.error(error_msg)
            
            return StudyCardWorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=False,
                execution_time=execution_time,
                error_message=error_msg
            )
    
    async def _get_prioritized_documents(self, trial_id: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Get prioritized documents for a trial with rate limiting.
        
        Args:
            trial_id: Trial ID
            
        Returns:
            Tuple of (prioritized_documents, processing_stats)
        """
        try:
            with session_scope() as session:
                # Get all documents linked to this trial with R/S scores
                documents = session.query(Document, DocumentText).outerjoin(
                    DocumentText, Document.doc_id == DocumentText.doc_id
                ).join(
                    TrialDocCandidate, Document.doc_id == TrialDocCandidate.doc_id
                ).filter(
                    TrialDocCandidate.trial_id == trial_id,
                    TrialDocCandidate.stage == 'U1_abstract',
                    TrialDocCandidate.selected == True
                ).all()
                
                if not documents:
                    self.logger.warning(f"No documents found for trial {trial_id}")
                    return [], {"total_documents": 0, "selected_documents": 0}
                
                # Convert to processing candidates with prioritization
                candidates = []
                for doc, doc_text in documents:
                    # Check text availability
                    has_full_text = bool(doc_text and doc_text.fulltext_text and len(doc_text.fulltext_text.strip()) > 0)
                    has_abstract = bool(doc_text and doc_text.abstract_text and len(doc_text.abstract_text.strip()) > 0)
                    
                    # Determine priority based on R/S scores and text availability
                    priority = self._determine_document_priority(
                        doc.r_score, doc.r_tier, doc.s_score, doc.s_tier,
                        has_full_text, has_abstract
                    )
                    
                    # Calculate processing score
                    processing_score = self._calculate_processing_score(
                        doc.r_score, doc.s_score, has_full_text, has_abstract,
                        len(doc_text.fulltext_text) if doc_text and doc_text.fulltext_text else 0,
                        len(doc_text.abstract_text) if doc_text and doc_text.abstract_text else 0
                    )
                    
                    candidate = {
                        'doc_id': doc.doc_id,
                        'pmid': doc.pmid,
                        'title': doc.title,
                        'r_score': float(doc.r_score) if doc.r_score else 0.0,
                        'r_tier': doc.r_tier,
                        's_score': float(doc.s_score) if doc.s_score else 0.0,
                        's_tier': doc.s_tier,
                        'has_full_text': has_full_text,
                        'has_abstract': has_abstract,
                        'priority': priority,
                        'processing_score': processing_score,
                        'fulltext_text': doc_text.fulltext_text if doc_text else None,
                        'abstract_text': doc_text.abstract_text if doc_text else None,
                        'char_count_fulltext': doc_text.char_count_fulltext if doc_text else 0
                    }
                    candidates.append(candidate)
                
                # Sort candidates by priority and processing score
                sorted_candidates = self._sort_document_candidates(candidates)
                
                # Apply rate limiting
                selected_candidates = self._apply_document_rate_limits(sorted_candidates)
                
                # Generate processing statistics
                stats = self._generate_document_processing_stats(documents, candidates, selected_candidates)
                
                self.logger.info(f"Document prioritization applied: {len(selected_candidates)} documents selected from {len(candidates)} candidates")
                
                return selected_candidates, stats
                
        except Exception as e:
            self.logger.error(f"Error getting prioritized documents for trial {trial_id}: {e}")
            return [], {"total_documents": 0, "selected_documents": 0, "error": str(e)}
    
    async def _process_documents_batch(self, trial_id: int, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process documents in batches for study card generation.
        
        Args:
            trial_id: Trial ID
            documents: List of documents to process
            
        Returns:
            Processing results
        """
        results = {
            'success': True,
            'documents_processed': 0,
            'study_cards_generated': 0,
            'method_cards': 0,
            'results_cards': 0,
            'gates_passed': 0,
            'gates_failed': 0,
            'error_message': None
        }
        
        # Process in batches with rate limiting
        batch_size = min(self.batch_size, self.max_documents_per_batch)
        for i in range(0, len(documents), batch_size):
            batch_documents = documents[i:i + batch_size]
            self.logger.info(f"Processing Study Card batch {i//batch_size + 1}: {len(batch_documents)} documents")
            
            # Log document priorities in this batch
            priorities = [doc['priority'] for doc in batch_documents]
            priority_counts = {}
            for priority in priorities:
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            self.logger.info(f"Batch priorities: {priority_counts}")
            
            batch_results = await self._process_single_batch(trial_id, batch_documents)
            
            # Aggregate results
            for key in ['documents_processed', 'study_cards_generated', 'method_cards', 
                       'results_cards', 'gates_passed', 'gates_failed']:
                results[key] += batch_results[key]
            
            # Add delay between batches to respect rate limits
            if i + batch_size < len(documents):
                await asyncio.sleep(self.retry_delay)
        
        return results
    
    async def _process_single_batch(self, trial_id: int, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a single batch of documents using the study card pipeline.
        
        Args:
            trial_id: Trial ID
            documents: List of documents in this batch
            
        Returns:
            Batch processing results
        """
        results = {
            'documents_processed': 0,
            'study_cards_generated': 0,
            'method_cards': 0,
            'results_cards': 0,
            'gates_passed': 0,
            'gates_failed': 0
        }
        
        try:
            # Prepare trial context for the pipeline
            trial_context = await self._prepare_trial_context(trial_id, documents)
            
            # Execute the study card pipeline
            pipeline_result = await self.orchestrator.run_study_card_generation([{
                'trial_id': str(trial_id),
                'trial_data': trial_context
            }])
            
            if pipeline_result.success:
                results['documents_processed'] = len(documents)
                
                # Save the generated cards to the database
                await self._save_pipeline_results(trial_id, pipeline_result)
                
                # Count generated cards
                results['study_cards_generated'] = 1 if pipeline_result.method_card or pipeline_result.results_factsheet else 0
                results['method_cards'] = 1 if pipeline_result.method_card else 0
                results['results_cards'] = 1 if pipeline_result.results_factsheet else 0
                results['gates_passed'] = len([ga for ga in pipeline_result.gate_assessments if ga.status == "PASS"])
                results['gates_failed'] = len([ga for ga in pipeline_result.gate_assessments if ga.status == "FAIL"])
                
                self.logger.info(f"Pipeline executed successfully for trial {trial_id}")
                self.logger.info(f"Generated: {results['method_cards']} method cards, {results['results_cards']} results cards, {len(pipeline_result.gate_assessments)} gate assessments")
            else:
                self.logger.error(f"Pipeline failed for trial {trial_id}: {pipeline_result.errors}")
                
        except Exception as e:
            self.logger.error(f"Error processing batch for trial {trial_id}: {e}")
        
        return results
    
    async def _prepare_trial_context(self, trial_id: int, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepare trial context for the study card pipeline.
        
        Args:
            trial_id: Trial ID
            documents: List of documents with full text
            
        Returns:
            Trial context dictionary
        """
        try:
            with session_scope() as session:
                # Get trial information
                trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                if not trial:
                    raise ValueError(f"Trial {trial_id} not found")
                
                # Get company information
                company = session.query(Company).filter(Company.company_id == trial.sponsor_company_id).first()
                
                # Prepare trial context
                trial_context = {
                    'trial_id': trial_id,
                    'nct_id': trial.nct_id,
                    'brief_title': trial.brief_title,
                    'indication': trial.indication,
                    'phase': trial.phase,
                    'status': trial.status,
                    'sponsor': company.name if company else None,
                    'documents': documents,
                    'raw_doc_texts': {
                        str(doc['doc_id']): doc['fulltext_text']
                        for doc in documents
                    }
                }
                
                return trial_context
                
        except Exception as e:
            self.logger.error(f"Error preparing trial context for trial {trial_id}: {e}")
            return {}
    
    def _convert_to_boolean(self, value):
        """Convert various value types to boolean."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            value_lower = value.lower()
            if value_lower in ['true', 'yes', '1', 'present', 'available']:
                return True
            elif value_lower in ['false', 'no', '0', 'absent', 'not available', 'none']:
                return False
            else:
                # For complex strings, return None (unknown)
                return None
        if isinstance(value, (int, float)):
            return bool(value)
        return None

    async def _save_pipeline_results(self, trial_id: int, pipeline_result) -> None:
        """
        Save the generated pipeline results to the database.
        
        Args:
            trial_id: Trial ID
            pipeline_result: DirectStudyCardResult from the pipeline
        """
        try:
            with session_scope() as session:
                # Save method card
                if pipeline_result.method_card:
                    method_card_data = pipeline_result.method_card.__dict__
                    db_method_card = MethodCard(
                        doc_id=method_card_data.get('doc_id', ''),
                        design_archetype=method_card_data.get('design_archetype'),
                        is_blinded=self._convert_to_boolean(method_card_data.get('is_blinded')),
                        analysis_set=method_card_data.get('analysis_set'),
                        population_description=method_card_data.get('population_description'),
                        stratification_factors=method_card_data.get('stratification_factors'),
                        covariate_adjustment=method_card_data.get('covariate_adjustment'),
                        primary_endpoint=method_card_data.get('primary_endpoint'),
                        secondary_endpoints=method_card_data.get('secondary_endpoints'),
                        summary_measure=method_card_data.get('summary_measure'),
                        alpha_level=method_card_data.get('alpha_level'),
                        is_one_sided=self._convert_to_boolean(method_card_data.get('is_one_sided')),
                        multiplicity_adjustment=method_card_data.get('multiplicity_adjustment'),
                        sample_size_reassessment=self._convert_to_boolean(method_card_data.get('sample_size_reassessment')),
                        interim_looks=method_card_data.get('interim_looks'),
                        interim_timing=method_card_data.get('interim_timing'),
                        spending_function=method_card_data.get('spending_function'),
                        stop_rules=method_card_data.get('stop_rules'),
                        missingness_assumption=method_card_data.get('missingness_assumption'),
                        missingness_pattern=method_card_data.get('missingness_pattern'),
                        imputation_method=method_card_data.get('imputation_method'),
                        estimand=method_card_data.get('estimand'),
                        intercurrent_events_policy=method_card_data.get('intercurrent_events_policy'),
                        endpoint_ascertainment=method_card_data.get('endpoint_ascertainment'),
                        assessment_interval=method_card_data.get('assessment_interval'),
                        adjudication_committee=self._convert_to_boolean(method_card_data.get('adjudication_committee'))
                    )
                    session.add(db_method_card)
                    self.logger.info(f"Saved method card for trial {trial_id}")
                
                # Save results factsheet
                if pipeline_result.results_factsheet:
                    results_data = pipeline_result.results_factsheet.__dict__
                    db_results_factsheet = ResultsFactsheet(
                        doc_id=results_data.get('doc_id', ''),
                        results=results_data.get('results'),
                        primary_endpoint_results=results_data.get('primary_endpoint_results'),
                        secondary_endpoint_results=results_data.get('secondary_endpoint_results'),
                        safety_results=results_data.get('safety_results'),
                        primary_analysis_set=results_data.get('primary_analysis_set'),
                        secondary_analysis_sets=results_data.get('secondary_analysis_sets'),
                        total_enrolled=results_data.get('total_enrolled'),
                        completed_primary_endpoint=results_data.get('completed_primary_endpoint'),
                        dropout_rate=results_data.get('dropout_rate'),
                        follow_up_completion=results_data.get('follow_up_completion')
                    )
                    session.add(db_results_factsheet)
                    self.logger.info(f"Saved results factsheet for trial {trial_id}")
                
                # Save gate assessments
                for gate_assessment in pipeline_result.gate_assessments:
                    gate_data = gate_assessment.__dict__
                    db_gate_assessment = GateAssessment(
                        gate_id=gate_data.get('gate_id', ''),
                        status=gate_data.get('status', 'UNCERTAIN'),
                        p_gate=gate_data.get('p_gate'),
                        rationale=gate_data.get('rationale'),
                        sensitivity=gate_data.get('sensitivity'),
                        computed_values=gate_data.get('computed_values'),
                        threshold_comparisons=gate_data.get('threshold_comparisons'),
                        assessment_method=gate_data.get('assessment_method'),
                        confidence_in_assessment=gate_data.get('confidence_in_assessment'),
                        assessment_notes=gate_data.get('assessment_notes'),
                        next_steps=gate_data.get('next_steps')
                    )
                    session.add(db_gate_assessment)
                if pipeline_result.gate_assessments:
                    self.logger.info(f"Saved {len(pipeline_result.gate_assessments)} gate assessments for trial {trial_id}")
                
                # Save evidence spans
                for evidence_span in pipeline_result.evidence_spans:
                    span_data = evidence_span.__dict__
                    db_evidence_span = EvidenceSpan(
                        doc_id=span_data.get('doc_id', ''),
                        quote=span_data.get('quote', ''),
                        section=span_data.get('section', 'unknown'),
                        char_start=span_data.get('char_start'),
                        char_end=span_data.get('char_end'),
                        confidence=span_data.get('confidence', 0.8),
                        internal_id=span_data.get('internal_id', ''),
                        kind=span_data.get('kind', 'base'),
                        status=span_data.get('status', 'draft')
                    )
                    session.add(db_evidence_span)
                if pipeline_result.evidence_spans:
                    self.logger.info(f"Saved {len(pipeline_result.evidence_spans)} evidence spans for trial {trial_id}")
                
                # Commit all changes
                session.commit()
                self.logger.info(f"Successfully saved all pipeline results for trial {trial_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to save pipeline results for trial {trial_id}: {e}")
            raise
    
    def _determine_document_priority(self, r_score, r_tier, s_score, s_tier, has_full_text, has_abstract):
        """Determine document priority based on R/S scores and text availability."""
        
        # Convert tiers to scores if scores are missing
        if r_score is None and r_tier:
            r_score = self._tier_to_score(r_tier)
        if s_score is None and s_tier:
            s_score = self._tier_to_score(s_tier)
        
        # Default to low scores if missing
        r_score = r_score or 0.0
        s_score = s_score or 0.0
        
        # High priority: R≥2 AND S≥2 AND has full text
        if (r_score >= self.high_priority_r_threshold and 
            s_score >= self.high_priority_s_threshold and 
            has_full_text):
            return "HIGH"
        
        # Medium priority: R≥2 OR S≥2 AND has full text
        if ((r_score >= self.high_priority_r_threshold or 
             s_score >= self.high_priority_s_threshold) and 
            has_full_text):
            return "MEDIUM"
        
        # Low priority: R≥1 OR S≥1 AND has full text
        if ((r_score >= self.medium_priority_r_threshold or 
             s_score >= self.medium_priority_s_threshold) and 
            has_full_text):
            return "LOW"
        
        # Fallback: High R/S but no full text (abstract only)
        if ((r_score >= self.high_priority_r_threshold or 
             s_score >= self.high_priority_s_threshold) and 
            has_abstract and not has_full_text):
            return "FALLBACK"
        
        # Default to low priority
        return "LOW"
    
    def _tier_to_score(self, tier):
        """Convert R/S tier to approximate score."""
        tier_mapping = {
            'R0': 0.0, 'R1': 0.4, 'R2': 0.6, 'R3': 0.8,
            'S0': 0.0, 'S1': 0.4, 'S2': 0.6, 'S3': 0.8
        }
        return tier_mapping.get(tier, 0.0)
    
    def _calculate_processing_score(self, r_score, s_score, has_full_text, has_abstract, full_text_length, abstract_length):
        """Calculate overall processing score for document prioritization."""
        
        # Base score from R/S scores
        r_score = float(r_score) if r_score else 0.0
        s_score = float(s_score) if s_score else 0.0
        base_score = (r_score + s_score) / 2.0
        
        # Text availability bonus
        text_bonus = 0.0
        if has_full_text:
            text_bonus += 0.3
            # Bonus for longer full text
            if full_text_length and full_text_length > 1000:
                text_bonus += min(0.2, full_text_length / 10000.0)  # Cap at 0.2
        elif has_abstract:
            text_bonus += 0.1
            # Bonus for longer abstract
            if abstract_length and abstract_length > 200:
                text_bonus += min(0.1, abstract_length / 2000.0)  # Cap at 0.1
        
        # Combine base score and text bonus
        processing_score = base_score + text_bonus
        
        return min(1.0, processing_score)  # Cap at 1.0
    
    def _sort_document_candidates(self, candidates):
        """Sort candidates by priority and processing score."""
        
        def sort_key(candidate):
            # Primary sort: priority (HIGH=1, MEDIUM=2, LOW=3, FALLBACK=4)
            priority_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3, "FALLBACK": 4}
            priority_value = priority_order.get(candidate['priority'], 5)
            
            # Secondary sort: processing score (higher = better)
            processing_score = candidate['processing_score']
            
            # Tertiary sort: R score (higher = better)
            r_score = candidate['r_score']
            
            # Final sort: S score (higher = better)
            s_score = candidate['s_score']
            
            return (priority_value, -processing_score, -r_score, -s_score)
        
        return sorted(candidates, key=sort_key)
    
    def _apply_document_rate_limits(self, candidates):
        """Apply rate limiting to selected candidates."""
        
        # Separate candidates by priority
        high_priority = [c for c in candidates if c['priority'] == 'HIGH']
        medium_priority = [c for c in candidates if c['priority'] == 'MEDIUM']
        low_priority = [c for c in candidates if c['priority'] == 'LOW']
        fallback_priority = [c for c in candidates if c['priority'] == 'FALLBACK']
        
        selected = []
        
        # Select high priority documents first
        selected.extend(high_priority[:self.max_documents_per_trial])
        
        # Add medium priority if we have room
        remaining_slots = self.max_documents_per_trial - len(selected)
        if remaining_slots > 0:
            selected.extend(medium_priority[:remaining_slots])
        
        # Add low priority if we have room
        remaining_slots = self.max_documents_per_trial - len(selected)
        if remaining_slots > 0:
            selected.extend(low_priority[:remaining_slots])
        
        # Add fallback documents if enabled and we have room
        if self.enable_fallback_processing:
            remaining_slots = self.max_documents_per_trial - len(selected)
            if remaining_slots > 0:
                selected.extend(fallback_priority[:min(remaining_slots, self.max_fallback_documents)])
        
        self.logger.info(f"Rate limiting applied: {len(selected)} documents selected from {len(candidates)} candidates")
        
        return selected
    
    def _generate_document_processing_stats(self, all_documents, candidates, selected):
        """Generate processing statistics."""
        
        # Count by priority
        priority_counts = {}
        for priority in ["HIGH", "MEDIUM", "LOW", "FALLBACK"]:
            priority_counts[priority] = len([c for c in candidates if c['priority'] == priority])
        
        # Count by text availability
        text_stats = {
            'has_full_text': len([c for c in candidates if c['has_full_text']]),
            'has_abstract_only': len([c for c in candidates if c['has_abstract'] and not c['has_full_text']]),
            'no_text': len([c for c in candidates if not c['has_abstract'] and not c['has_full_text']])
        }
        
        # R/S score statistics
        rs_stats = {
            'high_r_scores': len([c for c in candidates if c['r_score'] >= self.high_priority_r_threshold]),
            'high_s_scores': len([c for c in candidates if c['s_score'] >= self.high_priority_s_threshold]),
            'medium_r_scores': len([c for c in candidates if c['r_score'] >= self.medium_priority_r_threshold]),
            'medium_s_scores': len([c for c in candidates if c['s_score'] >= self.medium_priority_s_threshold])
        }
        
        return {
            'total_documents': len(all_documents),
            'total_candidates': len(candidates),
            'selected_documents': len(selected),
            'priority_counts': priority_counts,
            'text_availability': text_stats,
            'rs_score_stats': rs_stats,
            'rate_limit_applied': len(selected) < len(candidates)
        }

    async def _update_trial_state(self, trial_id: int, results: Dict[str, Any]):
        """
        Update trial state with study card processing results.
        
        Args:
            trial_id: Trial ID
            results: Processing results
        """
        try:
            # Update trial literature state
            state_data = {
                'gates_passed': results.get('gates_passed', 0),
                'gates_failed': results.get('gates_failed', 0),
                'study_cards_generated': results.get('study_cards_generated', 0),
                'method_cards': results.get('method_cards', 0),
                'results_cards': results.get('results_cards', 0)
            }
            
            self.db_service.update_trial_lit_state(trial_id, state_data)
            self.logger.info(f"Updated trial {trial_id} state: {results.get('gates_passed', 0)} gates passed, {results.get('gates_failed', 0)} gates failed")
            
        except Exception as e:
            self.logger.error(f"Error updating trial state for trial {trial_id}: {e}")
    
    async def run_worker(self, max_tasks: Optional[int] = None):
        """
        Run the study card worker.
        
        Args:
            max_tasks: Maximum number of tasks to process (None for unlimited)
        """
        self.logger.info("Starting Study Card worker")
        
        tasks_processed = 0
        
        try:
            while True:
                # Check if we've reached the max tasks limit
                if max_tasks is not None and tasks_processed >= max_tasks:
                    self.logger.info(f"Reached max tasks limit ({max_tasks}), stopping worker")
                    break
                
                # Lease next task
                task = self.queue_service.lease_next(['STUDYCARD'])
                if not task:
                    self.logger.info("No tasks available, waiting...")
                    await asyncio.sleep(15)
                    continue
                
                # Process the task
                try:
                    result = await self.process_studycard_task(task)
                    if result.success:
                        self.logger.info(f"Completed Study Card task {task['id']} for trial {task['trial_id']}")
                    else:
                        self.logger.error(f"Study Card task {task['id']} failed: {result.error_message}")
                    
                    tasks_processed += 1
                    
                except Exception as e:
                    self.logger.error(f"Error processing task {task.get('id', 'unknown')}: {e}")
                    tasks_processed += 1
                    continue
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, stopping worker")
        except Exception as e:
            self.logger.error(f"Worker error: {e}")
        finally:
            self.logger.info(f"Study Card worker stopped after processing {tasks_processed} tasks")
    
