"""
Late Fusion Orchestrator

Implements dual-path processing by default, combining LLM and deterministic workers
with global validators for provenance, units, and section constraints.

Updated to implement LLM-first, provenance-second architecture.
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict
import logging

# Import workers dynamically to avoid SQLAlchemy conflicts
# from ..workers.base_worker import BaseWorker, WorkerResult
# from ..workers.llm.method_auditor import MethodAuditor
# from ..workers.llm.results_distiller import ResultsDistiller
# from ..workers.llm.claimizer import Claimizer
# from ..workers.llm.counter_evidence_miner import CounterEvidenceMiner
# from ..workers.deterministic.gate_validator import GateValidator
# from ..workers.deterministic.gate_assessor import GateAssessor
from ..models import (
    EvidenceSpan, MethodCard, ResultsFactsheet, Claim
)
from ..models.llm_extraction_draft import LLMExtractionDraft
from ..validators import validate_all_artifacts
from ..workers.interfaces.denominator_resolver import create_denominator_resolver


class LateFusionOrchestrator:
    """
    Orchestrates dual-path processing with late fusion of LLM and deterministic results.
    
    Updated to implement LLM-first, provenance-second architecture:
    - LLM Path: LLMResultsDrafter → ProvenanceBacktracer → ResultsFinalizer
    - Deterministic Path: DeterministicResultsDistiller (unchanged)
    - Late Fusion: Combines results with global validation
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the orchestrator with configuration."""
        # Initialize logger first
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.logger.addHandler(h)
        self.logger.setLevel(logging.INFO)
        
        self.config = config or {}
        
        # Feature flags - initialize first before calling _initialize_workers()
        self.enable_llm_path = self.config.get('enable_llm_path', True)
        self.enable_deterministic_path = self.config.get('enable_deterministic_path', True)
        self.enable_late_fusion = self.config.get('enable_late_fusion', True)
        
        # LLM-first architecture configuration
        self.llm_path_config = self.config.get('llm_path', {})
        self.fusion_config = self.config.get('fusion', {})
        
        # Fusion configuration
        self.epsilon_pct = self.config.get('epsilon_pct', 0.05)  # 5% tolerance for equality
        self.denom_precedence = self.config.get('denom_precedence', ['table', 'results', 'abstract'])
        self.choose_by = self.config.get('choose_by', ['anchoring', 'n', 'confidence'])
        
        # Worker instances
        self.llm_workers = {}
        self.deterministic_workers = {}
        
        # Initialize workers based on configuration
        self._initialize_workers()
        
    def _initialize_workers(self):
        """Initialize workers based on configuration."""
        if self.enable_llm_path:
            try:
                # Dynamic imports to avoid SQLAlchemy conflicts
                from ..workers.llm.llm_results_drafter import LLMResultsDrafter
                from ..workers.provenance_backtracer import ProvenanceBacktracer
                from ..workers.results_finalizer import ResultsFinalizer
                from ..workers.llm.method_auditor import MethodAuditor
                from ..workers.llm.claimizer import Claimizer
                from ..workers.llm.counter_evidence_miner import CounterEvidenceMiner
                from ..workers.llm.mechanistic_dose_researcher import MechanisticDoseResearcher
                
                # LLM-first architecture workers
                self.llm_workers = {
                    'llm_results_drafter': LLMResultsDrafter(),
                    'provenance_backtracer': ProvenanceBacktracer(
                        bm25_topk=self.llm_path_config.get('backtrace', {}).get('bm25_topk', 20),
                        fuzzy_threshold=self.llm_path_config.get('backtrace', {}).get('fuzzy_threshold', 0.86),
                        numeric_strict=self.llm_path_config.get('backtrace', {}).get('numeric_strict', True),
                        section_bonus=self.llm_path_config.get('backtrace', {}).get('section_bonus', 0.1),
                        allow_table_only=self.llm_path_config.get('backtrace', {}).get('allow_table_only', True)
                    ),
                    'results_finalizer': ResultsFinalizer(
                        prefer_deterministic_if_tie=self.fusion_config.get('prefer_deterministic_if_tie', True),
                        min_provenance_score=self.fusion_config.get('min_provenance_score', 0.75),
                        hard_fail_if_missing_spans=self.fusion_config.get('hard_fail_if_missing_spans', True)
                    ),
                    'method_auditor': MethodAuditor(),
                    'denominator_resolver': create_denominator_resolver("llm"),
                    'claimizer': Claimizer(),
                    'counter_evidence_miner': CounterEvidenceMiner(),
                    'mechanistic_dose_researcher': MechanisticDoseResearcher()
                }
                self.logger.info("LLM path workers initialized (LLM-first architecture)")
            except ImportError as e:
                self.logger.warning(f"Could not initialize LLM workers: {e}")
                self.llm_workers = {}
        
        if self.enable_deterministic_path:
            try:
                # Dynamic imports to avoid SQLAlchemy conflicts
                from ..workers.deterministic.method_auditor import DeterministicMethodAuditor
                from ..workers.deterministic.results_distiller import DeterministicResultsDistiller
                from ..workers.deterministic.gate_validator import GateValidator
                from ..workers.deterministic.gate_assessor import GateAssessor
                
                self.deterministic_workers = {
                    'method_auditor': DeterministicMethodAuditor(),
                    'denominator_resolver': create_denominator_resolver("deterministic"),
                    'results_distiller': DeterministicResultsDistiller(),
                    'gate_validator': GateValidator(),
                    'gate_assessor': GateAssessor()
                }
                self.logger.info("Deterministic path workers initialized")
            except ImportError as e:
                self.logger.warning(f"Could not initialize deterministic workers: {e}")
                self.deterministic_workers = {}

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process evidence spans through dual-path architecture with late fusion.
        
        Updated to implement LLM-first, provenance-second architecture:
        1. Deterministic Path: Process pre-triaged spans
        2. LLM Path: Read raw text → Draft results → Backtrace spans → Finalize
        3. Late Fusion: Merge and validate final results
        """
        start_time = time.time()
        
        pipeline_results = {
            'success': False,
            'method_card': None,
            'results_factsheet': None,
            'claims': None,
            'contradicting_claims': None,
            'ambiguity_ledger': {},
            'execution_time': 0.0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Extract inputs
            evidence_spans = inputs.get('evidence_spans', [])
            trial_context = inputs.get('trial_context', {})
            design_json = inputs.get('design_json', {})
            pocket_context = inputs.get('pocket_context', None)
            raw_doc_text = inputs.get('raw_doc_text', "")
            
            # Get doc_id
            doc_id = None
            if evidence_spans:
                doc_id = evidence_spans[0].doc_id
            elif trial_context:
                doc_id = trial_context.get('doc_id')
            
            if not doc_id:
                pipeline_results['errors'].append("Cannot process without valid doc_id")
                return pipeline_results
            
            # Step 1: Validate spans
            self.logger.info("Step 1: Validating evidence spans")
            span_validation = self._validate_spans(evidence_spans)
            if not span_validation['is_valid']:
                pipeline_results['warnings'].extend(span_validation['warnings'])
            
            # Step 2: Process deterministic path
            deterministic_results = {}
            if self.enable_deterministic_path:
                self.logger.info("Step 2: Processing deterministic path")
                deterministic_results = self._process_deterministic_path(
                    evidence_spans, trial_context, design_json, pocket_context
                )
                if not deterministic_results['success']:
                    pipeline_results['warnings'].extend(deterministic_results['errors'])
            
            # Step 3: Process LLM path (LLM-first architecture)
            llm_results = {}
            if self.enable_llm_path:
                self.logger.info("Step 3: Processing LLM path (LLM-first architecture)")
                llm_results = self._process_llm_path_llm_first(
                    evidence_spans, trial_context, design_json, pocket_context, raw_doc_text, doc_id
                )
                if not llm_results['success']:
                    pipeline_results['warnings'].extend(llm_results['errors'])
            
            # Step 4: Late fusion and finalization
            fusion_results = {}
            if self.enable_late_fusion:
                self.logger.info("Step 4: Late fusion and finalization")
                fusion_results = self._perform_late_fusion_llm_first(
                    deterministic_results, llm_results, evidence_spans, doc_id
                )
                if not fusion_results['success']:
                    pipeline_results['errors'].extend(fusion_results['errors'])
                else:
                    # Update pipeline results with fused artifacts
                    pipeline_results.update(fusion_results)
            
            # Step 5: Final validation and output preparation
            self.logger.info("Step 5: Final validation and output preparation")
            final_results = self._prepare_final_output_llm_first(
                deterministic_results, llm_results, fusion_results
            )
            
            # Update pipeline results
            pipeline_results.update(final_results)
            pipeline_results['success'] = True
            pipeline_results['execution_time'] = time.time() - start_time
            
            self.logger.info(f"Pipeline completed successfully in {pipeline_results['execution_time']:.2f}s")
            
        except Exception as e:
            self.logger.error(f"Pipeline failed with error: {str(e)}")
            pipeline_results['errors'].append(f"Pipeline execution failed: {str(e)}")
            pipeline_results['execution_time'] = time.time() - start_time
        
        return pipeline_results

    def process_pipeline(self, evidence_spans: List[EvidenceSpan], trial_context: Dict[str, Any], 
                        design_json: Optional[Dict[str, Any]] = None, pocket_context: Optional[Any] = None,
                        raw_doc_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Backward compatibility method that delegates to process().
        
        This method exists to maintain compatibility with existing test scripts
        that call process_pipeline() instead of process().
        """
        # Create mock raw_doc_text if not provided (for backward compatibility)
        if raw_doc_text is None:
            raw_doc_text = self._create_mock_raw_doc_text(evidence_spans)
        
        inputs = {
            'evidence_spans': evidence_spans,
            'trial_context': trial_context,
            'design_json': design_json or {},
            'pocket_context': pocket_context,
            'raw_doc_text': raw_doc_text
        }
        
        return self.process(inputs)

    def _create_mock_raw_doc_text(self, evidence_spans: List[EvidenceSpan]) -> str:
        """Create mock raw document text from evidence spans for backward compatibility."""
        if not evidence_spans:
            return ""
        
        # Get doc_id from first span
        doc_id = evidence_spans[0].doc_id
        
        # Create a mock document structure
        sections = {}
        for span in evidence_spans:
            section = span.section.lower()
            if section not in sections:
                sections[section] = []
            sections[section].append(span.quote)
        
        # Build mock document text
        mock_text = f"Document: {doc_id}\n\n"
        
        for section_name, quotes in sections.items():
            mock_text += f"{section_name.title()}\n"
            mock_text += "\n".join(quotes)
            mock_text += "\n\n"
        
        return mock_text

    def _process_llm_path_llm_first(self, evidence_spans: List[EvidenceSpan], 
                                   trial_context: Dict[str, Any], design_json: Dict[str, Any],
                                   pocket_context: Any, raw_doc_text: str, doc_id: str) -> Dict[str, Any]:
        """
        Process the LLM path using LLM-first, provenance-second architecture.
        
        Flow:
        1. LLMResultsDrafter: Read raw text → Draft results with verbatim quotes
        2. ProvenanceBacktracer: Find spans for LLM draft results
        3. ResultsFinalizer: Merge with deterministic results (if any)
        """
        llm_results = {
            'success': False,
            'method_card': None,
            'results_factsheet': None,
            'claims': None,
            'contradicting_claims': None,
            'errors': [],
            'execution_time': 0.0
        }
        
        start_time = time.time()
        
        try:
            # Step 3a: LLM Results Drafter
            if 'llm_results_drafter' in self.llm_workers and raw_doc_text:
                self.logger.info("Step 3a: Running LLM Results Drafter")
                drafter_result = self.llm_workers['llm_results_drafter'].process({
                    'raw_doc_text': raw_doc_text,
                    'doc_id': doc_id,
                    'trial_context': trial_context
                })
                
                if drafter_result.success:
                    llm_results_draft = drafter_result.output.get('results_draft')
                    llm_results['results_draft'] = llm_results_draft
                    llm_results['raw_doc_text'] = raw_doc_text  # Store for provenance backtracing
                else:
                    llm_results['errors'].append(f"LLM Results Drafter failed: {drafter_result.error_message}")
            
            # Step 3b: Provenance Backtracer
            if 'provenance_backtracer' in self.llm_workers and llm_results.get('results_draft'):
                self.logger.info("Step 3b: Running Provenance Backtracer")
                backtracer_result = self.llm_workers['provenance_backtracer'].process({
                    'llm_extraction_draft': llm_results['results_draft'],
                    'raw_doc_text': raw_doc_text,
                    'evidence_spans': evidence_spans
                })
                
                if backtracer_result.success:
                    llm_results['results_draft'] = backtracer_result.output.get('llm_extraction_draft')
                else:
                    llm_results['errors'].append(f"Provenance Backtracer failed: {backtracer_result.error_message}")
            
            # Step 3c: Method Auditor (unchanged)
            if 'method_auditor' in self.llm_workers:
                self.logger.info("Step 3c: Running Method Auditor")
                method_result = self.llm_workers['method_auditor'].process({
                    'evidence_spans': [s for s in evidence_spans if s.section.lower() in ['methods', 'protocol', 'sap']],
                    'design_json': design_json or {},
                    'pocket_context': pocket_context
                })
                
                if method_result.success:
                    llm_results['method_card'] = method_result.output.get('method_card')
                else:
                    llm_results['errors'].append(f"Method Auditor failed: {method_result.error_message}")
            
            # Step 3d: Denominator Resolver
            denominators = None
            if 'denominator_resolver' in self.llm_workers:
                self.logger.info("Step 3d: Running Denominator Resolver")
                denominator_result = self.llm_workers['denominator_resolver'].process({
                    'evidence_spans': evidence_spans
                })
                
                if denominator_result.success:
                    denominators = denominator_result.output.get('denominators')
                    llm_results['denominators'] = denominators
                else:
                    llm_results['errors'].append(f"Denominator Resolver failed: {denominator_result.error_message}")
            
            # Step 3e: Claimizer
            if 'claimizer' in self.llm_workers:
                self.logger.info("Step 3e: Running Claimizer")
                claim_result = self.llm_workers['claimizer'].process({
                    'evidence_spans': evidence_spans
                })
                
                if claim_result.success:
                    llm_results['claims'] = claim_result.output.get('claims')
                else:
                    llm_results['errors'].append(f"Claimizer failed: {claim_result.error_message}")
            
            # Step 3f: Counter Evidence Miner
            if 'counter_evidence_miner' in self.llm_workers:
                self.logger.info("Step 3f: Running Counter Evidence Miner")
                counter_result = self.llm_workers['counter_evidence_miner'].process({
                    'corpus_spans': evidence_spans,
                    'gate_families': ['G1_signal', 'G2_mechanism_delivery', 'G3_design'],
                    'existing_claims': llm_results.get('claims', [])
                })
                
                if counter_result.success:
                    llm_results['contradicting_claims'] = counter_result.output.get('contradicting_claims')
                else:
                    llm_results['errors'].append(f"Counter Evidence Miner failed: {counter_result.error_message}")
            
            # Step 3g: Mechanistic Dose Researcher
            if 'mechanistic_dose_researcher' in self.llm_workers:
                self.logger.info("Step 3g: Running Mechanistic Dose Researcher")
                mechanistic_result = self.llm_workers['mechanistic_dose_researcher'].process({
                    'trial_context': trial_context,
                    'evidence_spans': evidence_spans,
                    'pocket_context': pocket_context,
                    'design_json': design_json or {}
                })
                
                if mechanistic_result.success:
                    llm_results['mechanistic_dose_card'] = mechanistic_result.output.get('mechanistic_dose_card')
                    llm_results['mechanistic_metadata'] = {
                        'processed_spans': mechanistic_result.output.get('processed_spans', 0),
                        'total_citations': mechanistic_result.output.get('total_citations', 0),
                        'confidence': mechanistic_result.metadata.get('confidence', 'Unknown'),
                        'red_flags_count': mechanistic_result.metadata.get('red_flags_count', 0)
                    }
                else:
                    llm_results['errors'].append(f"Mechanistic Dose Researcher failed: {mechanistic_result.error_message}")
            
            # Check if we have the minimum required outputs
            if llm_results.get('results_draft') or llm_results.get('method_card'):
                llm_results['success'] = True
            else:
                llm_results['errors'].append("Missing required outputs from LLM path")
            
            llm_results['execution_time'] = time.time() - start_time
            
        except Exception as e:
            llm_results['errors'].append(f"LLM path processing failed: {str(e)}")
            llm_results['execution_time'] = time.time() - start_time
        
        return llm_results

    def _perform_late_fusion_llm_first(self, deterministic_results: Dict[str, Any],
                                      llm_results: Dict[str, Any], evidence_spans: List[EvidenceSpan],
                                      doc_id: str) -> Dict[str, Any]:
        """
        Perform late fusion using LLM-first architecture.
        
        Uses ResultsFinalizer to merge deterministic and LLM results.
        """
        fusion_results = {
            'success': False,
            'results_factsheet': None,
            'method_card': None,
            'ambiguity_ledger': {},
            'errors': [],
            'execution_time': 0.0
        }
        
        start_time = time.time()
        
        try:
            # Use Results Finalizer to merge results
            if 'results_finalizer' in self.llm_workers:
                self.logger.info("Running Results Finalizer")
                
                finalizer_inputs = {
                    'doc_id': doc_id,
                    'denominators': llm_results.get('denominators', {})
                }
                
                # Add deterministic results if available
                if deterministic_results.get('results_factsheet'):
                    finalizer_inputs['deterministic_results'] = deterministic_results['results_factsheet']
                
                # Add LLM results if available (after provenance backtracing)
                if llm_results.get('results_draft'):
                    # First run provenance backtracer if available
                    if 'provenance_backtracer' in self.llm_workers:
                        self.logger.info("Step 3b: Running Provenance Backtracer")
                        
                        # Create LLMExtractionDraft from LLMResultsDraft
                        from ..models.llm_extraction_draft import LLMExtractionDraft
                        llm_extraction_draft = LLMExtractionDraft(
                            doc_id=doc_id,
                            results_draft=llm_results['results_draft']
                        )
                        
                        backtracer_inputs = {
                            'llm_extraction_draft': llm_extraction_draft,
                            'raw_doc_text': llm_results.get('raw_doc_text', ''),
                            'doc_id': doc_id
                        }
                        backtracer_result = self.llm_workers['provenance_backtracer'].process(backtracer_inputs)
                        
                        if backtracer_result.success:
                            # Extract the results draft from the extraction draft
                            backtraced_extraction_draft = backtracer_result.output.get('llm_extraction_draft')
                            if backtraced_extraction_draft and backtraced_extraction_draft.results_draft:
                                finalizer_inputs['llm_results_draft'] = backtraced_extraction_draft.results_draft
                            else:
                                finalizer_inputs['llm_results_draft'] = llm_results['results_draft']
                        else:
                            self.logger.warning(f"Provenance backtracing failed: {backtracer_result.error_message}")
                            # Still pass the original draft, but it won't have spans
                            finalizer_inputs['llm_results_draft'] = llm_results['results_draft']
                    else:
                        finalizer_inputs['llm_results_draft'] = llm_results['results_draft']
                
                finalizer_result = self.llm_workers['results_finalizer'].process(finalizer_inputs)
                
                if finalizer_result.success:
                    fusion_results['results_factsheet'] = finalizer_result.output.get('results_factsheet')
                    fusion_results['ambiguity_ledger'] = finalizer_result.output.get('ambiguity_ledger', {})
                    fusion_results['success'] = True
                else:
                    fusion_results['errors'].append(f"Results Finalizer failed: {finalizer_result.error_message}")
            
            # For method card, prefer LLM if available, otherwise use deterministic
            if llm_results.get('method_card'):
                fusion_results['method_card'] = llm_results['method_card']
            elif deterministic_results.get('method_card'):
                fusion_results['method_card'] = deterministic_results['method_card']
            
            fusion_results['execution_time'] = time.time() - start_time
            
        except Exception as e:
            fusion_results['errors'].append(f"Late fusion failed: {str(e)}")
            fusion_results['execution_time'] = time.time() - start_time
        
        return fusion_results

    def _prepare_final_output_llm_first(self, deterministic_results: Dict[str, Any],
                                       llm_results: Dict[str, Any], fusion_results: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare final output for LLM-first architecture."""
        final_results = {
            'method_card': fusion_results.get('method_card'),
            'results_factsheet': fusion_results.get('results_factsheet'),
            'claims': llm_results.get('claims'),
            'contradicting_claims': llm_results.get('contradicting_claims'),
            'ambiguity_ledger': fusion_results.get('ambiguity_ledger', {})
        }
        
        return final_results

    def _validate_spans(self, evidence_spans: List[EvidenceSpan]) -> Dict[str, Any]:
        """Validate evidence spans against span-specific rules only."""
        validation_result = {
            'is_valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Span-specific validation only (global validator expects artifacts, not spans)
            span_errors = self._validate_span_specific_rules(evidence_spans)
            if span_errors:
                validation_result['warnings'].extend(span_errors)
            
            validation_result['is_valid'] = True
            
        except Exception as e:
            validation_result['errors'].append(f"Span validation failed: {str(e)}")
        
        return validation_result
    
    def _validate_span_specific_rules(self, evidence_spans: List[EvidenceSpan]) -> List[str]:
        """Validate spans against specific rules."""
        warnings = []
        
        # Check for minimum span requirements
        if len(evidence_spans) < 16:
            warnings.append(f"Insufficient spans: {len(evidence_spans)} < 16 minimum required")
        
        # Check section coverage
        sections = [span.section.lower() for span in evidence_spans]
        methods_count = sections.count('methods')
        results_count = sections.count('results')
        
        if methods_count < 8:
            warnings.append(f"Insufficient Methods spans: {methods_count} < 8 minimum required")
        
        if results_count < 8:
            warnings.append(f"Insufficient Results spans: {results_count} < 8 minimum required")
        
        # Check for concept coverage (8 buckets from Study Card Overhaul)
        concept_coverage = self._check_concept_coverage(evidence_spans)
        missing_concepts = [concept for concept, covered in concept_coverage.items() if not covered]
        
        if missing_concepts:
            warnings.append(f"Missing concept coverage: {', '.join(missing_concepts)}")
        
        return warnings
    
    def _check_concept_coverage(self, evidence_spans: List[EvidenceSpan]) -> Dict[str, bool]:
        """Check coverage of the 8 required concepts."""
        concepts = {
            'blinding_status': False,
            'site_center_info': False,
            'endpoints_statement': False,
            'assessment_cadence': False,
            'response_criteria': False,
            'statistics_plan': False,
            'treatment_dosing': False,
            'results_numeric': False
        }
        
        for span in evidence_spans:
            text_lower = span.quote.lower()
            
            # Check each concept
            if any(word in text_lower for word in ['blind', 'open', 'mask']):
                concepts['blinding_status'] = True
            
            if any(word in text_lower for word in ['site', 'center', 'region', 'country']):
                concepts['site_center_info'] = True
            
            if any(word in text_lower for word in ['endpoint', 'primary', 'secondary']):
                concepts['endpoints_statement'] = True
            
            if any(word in text_lower for word in ['assessment', 'evaluation', 'follow']):
                concepts['assessment_cadence'] = True
            
            if any(word in text_lower for word in ['recist', 'ca-125', 'response', 'criteria']):
                concepts['response_criteria'] = True
            
            if any(word in text_lower for word in ['kaplan', 'gehan', 'statistical', 'alpha']):
                concepts['statistics_plan'] = True
            
            if any(word in text_lower for word in ['dose', 'treatment', 'regimen', 'administration']):
                concepts['treatment_dosing'] = True
            
            if any(word in text_lower for word in ['median', 'response', 'rate', 'survival']):
                concepts['results_numeric'] = True
        
        return concepts
    
    def _process_deterministic_path(
        self, 
        evidence_spans: List[EvidenceSpan],
        trial_context: Dict[str, Any],
        design_json: Dict[str, Any],
        pocket_context: Any
    ) -> Dict[str, Any]:
        """Process the deterministic path with rule-based workers."""
        deterministic_results = {
            'success': False,
            'method_card': None,
            'results_factsheet': None,
            'gate_validations': None,
            'gate_assessments': None,
            'warnings': [],
            'errors': [],
            'execution_time': 0.0
        }
        
        start_time = time.time()
        
        try:
            # Deterministic Method Auditor
            if 'method_auditor' in self.deterministic_workers:
                self.logger.info("Running Deterministic Method Auditor")
                method_result = self.deterministic_workers['method_auditor'].process({
                    'evidence_spans': [s for s in evidence_spans if s.section.lower() in ['methods', 'protocol', 'sap']],
                    'trial_context': trial_context
                })
                
                if method_result.success:
                    deterministic_results['method_card'] = method_result.output.get('method_card')
                else:
                    deterministic_results['errors'].append(f"Deterministic Method Auditor failed: {method_result.error_message}")
            
            # Deterministic Denominator Resolver
            denominators = None
            if 'denominator_resolver' in self.deterministic_workers:
                self.logger.info("Running Deterministic Denominator Resolver")
                denominator_result = self.deterministic_workers['denominator_resolver'].process({
                    'evidence_spans': evidence_spans
                })
                
                if denominator_result.success:
                    denominators = denominator_result.output.get('denominators')
                    deterministic_results['denominators'] = denominators
                else:
                    deterministic_results['errors'].append(f"Deterministic Denominator Resolver failed: {denominator_result.error_message}")
            
            # Deterministic Results Distiller
            if 'results_distiller' in self.deterministic_workers:
                self.logger.info("Running Deterministic Results Distiller")
                results_result = self.deterministic_workers['results_distiller'].process({
                    'evidence_spans': [s for s in evidence_spans if s.section.lower() in ['results', 'abstract', 'table']],
                    'trial_context': trial_context,
                    'denominators': denominators
                })
                
                if results_result.success:
                    deterministic_results['results_factsheet'] = results_result.output.get('results_factsheet')
                else:
                    deterministic_results['errors'].append(f"Deterministic Results Distiller failed: {results_result.error_message}")
            
            # Gate Validator
            if 'gate_validator' in self.deterministic_workers:
                self.logger.info("Running Gate Validator")
                # This would validate any gate candidates if they exist
                # For now, just note that the worker is available
                deterministic_results['gate_validations'] = "Gate validation worker available"
            
            # Gate Assessor
            if 'gate_assessor' in self.deterministic_workers:
                self.logger.info("Running Gate Assessor")
                # This would assess gates if they exist
                # For now, just note that the worker is available
                deterministic_results['gate_assessments'] = "Gate assessment worker available"
            
            # Check if we have the minimum required outputs
            if deterministic_results['method_card'] and deterministic_results['results_factsheet']:
                deterministic_results['success'] = True
            else:
                deterministic_results['warnings'].append("Missing required outputs from deterministic path")
            
            deterministic_results['execution_time'] = time.time() - start_time
            
        except Exception as e:
            deterministic_results['errors'].append(f"Deterministic path processing failed: {str(e)}")
            deterministic_results['execution_time'] = time.time() - start_time
        
        return deterministic_results
    
    def _apply_late_fusion_rules(self, artifacts: List[Any]) -> List[Any]:
        """Apply late fusion rules to combine and enhance artifacts."""
        fused_artifacts = []
        
        # Group artifacts by type
        method_cards = [a for a in artifacts if hasattr(a, 'estimand')]
        results_factsheets = [a for a in artifacts if hasattr(a, 'metrics')]
        claims = [a for a in artifacts if hasattr(a, 'proposition')]
        
        # Apply fusion rules
        for method_card in method_cards:
            # Enhance method card with claims
            enhanced_method_card = self._enhance_method_card(method_card, claims)
            fused_artifacts.append(enhanced_method_card)
        
        for factsheet in results_factsheets:
            # Enhance factsheet with claims
            enhanced_factsheet = self._enhance_results_factsheet(factsheet, claims)
            fused_artifacts.append(enhanced_factsheet)
        
        # Add standalone claims
        fused_artifacts.extend(claims)
        
        return fused_artifacts
    
    def _enhance_method_card(self, method_card: MethodCard, claims: List[Claim]) -> MethodCard:
        """Enhance method card with relevant claims."""
        # Find claims that support method card assertions
        supporting_claims = [
            claim for claim in claims 
            if claim.type == 'design_fact' and claim.stance == 'supports'
        ]
        
        # Add claim references to method card (keep provenance_anchors for span IDs only)
        if supporting_claims:
            # Add supporting claim IDs as a separate field
            if not hasattr(method_card, 'supporting_claim_ids'):
                method_card.supporting_claim_ids = []
            method_card.supporting_claim_ids.extend([claim.claim_id for claim in supporting_claims])
        
        return method_card
    
    def _enhance_results_factsheet(self, factsheet: ResultsFactsheet, claims: List[Claim]) -> ResultsFactsheet:
        """Enhance results factsheet with relevant claims."""
        # Find claims that support results
        supporting_claims = [
            claim for claim in claims 
            if claim.type == 'effect_size' and claim.stance == 'supports'
        ]
        
        # Add claim references to factsheet
        for metric in factsheet.results:
            # Find relevant claims for this metric
            relevant_claims = [
                claim for claim in supporting_claims
                if claim.endpoint and claim.endpoint.lower() in str(metric).lower()
            ]
            
            if relevant_claims:
                metric['claim_ids'] = [claim.claim_id for claim in relevant_claims]
        
        return factsheet
    
    def _prepare_final_output(
        self, 
        llm_results: Dict[str, Any],
        deterministic_results: Dict[str, Any],
        fusion_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare the final output with all results."""
        return {
            'llm_path': llm_results,
            'deterministic_path': deterministic_results,
            'late_fusion': fusion_results,
            'summary': {
                'total_artifacts': len(fusion_results.get('fused_artifacts', [])),
                'method_cards': len([a for a in fusion_results.get('fused_artifacts', []) if hasattr(a, 'estimand')]),
                'results_factsheets': len([a for a in fusion_results.get('fused_artifacts', []) if hasattr(a, 'results')]),
                'claims': len([a for a in fusion_results.get('fused_artifacts', []) if hasattr(a, 'proposition')])
            }
        }
    
    def _persist_pre_fusion_artifacts(
        self, 
        llm_claims: List[Any], 
        llm_facts: List[Any], 
        deterministic_claims: List[Any], 
        deterministic_facts: List[Any],
        llm_results: Dict[str, Any],
        deterministic_results: Dict[str, Any]
    ):
        """Persist claims and facts before fusion validation."""
        import json
        from pathlib import Path
        import os
        
        try:
            # Create output directory if it doesn't exist
            output_dir = Path("test_outputs/pmc2978916_debug")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Persist LLM claims
            if llm_claims:
                claims_file = output_dir / 'claims_llm.jsonl'
                with open(claims_file, 'w') as f:
                    for claim in llm_claims:
                        if hasattr(claim, '__dict__'):
                            f.write(json.dumps(claim.__dict__, default=str) + '\n')
                        else:
                            f.write(json.dumps(claim, default=str) + '\n')
                self.logger.info(f"Persisted {len(llm_claims)} LLM claims to {claims_file}")
            
            # Persist LLM facts
            if llm_facts:
                facts_file = output_dir / 'facts_llm.jsonl'
                with open(facts_file, 'w') as f:
                    for fact in llm_facts:
                        if hasattr(fact, '__dict__'):
                            f.write(json.dumps(fact.__dict__, default=str) + '\n')
                        else:
                            f.write(json.dumps(fact, default=str) + '\n')
                self.logger.info(f"Persisted {len(llm_facts)} LLM facts to {facts_file}")
            
            # Persist deterministic claims
            if deterministic_claims:
                claims_file = output_dir / 'claims_deterministic.jsonl'
                with open(claims_file, 'w') as f:
                    for claim in deterministic_claims:
                        if hasattr(claim, '__dict__'):
                            f.write(json.dumps(claim.__dict__, default=str) + '\n')
                        else:
                            f.write(json.dumps(claim, default=str) + '\n')
                self.logger.info(f"Persisted {len(deterministic_claims)} deterministic claims to {claims_file}")
            
            # Persist deterministic facts
            if deterministic_facts:
                facts_file = output_dir / 'facts_det.jsonl'
                with open(facts_file, 'w') as f:
                    for fact in deterministic_facts:
                        if hasattr(fact, '__dict__'):
                            f.write(json.dumps(fact.__dict__, default=str) + '\n')
                        else:
                            f.write(json.dumps(fact, default=str) + '\n')
                self.logger.info(f"Persisted {len(deterministic_facts)} deterministic facts to {facts_file}")
            
            # Also persist method cards and results factsheets if available
            if llm_results.get('method_card'):
                method_file = output_dir / 'method_card_llm.json'
                with open(method_file, 'w') as f:
                    json.dump(llm_results['method_card'].__dict__, f, default=str, indent=2)
                self.logger.info(f"Persisted LLM method card to {method_file}")
            
            if llm_results.get('results_factsheet'):
                results_file = output_dir / 'results_factsheet_llm.json'
                with open(results_file, 'w') as f:
                    json.dump(llm_results['results_factsheet'].__dict__, f, default=str, indent=2)
                self.logger.info(f"Persisted LLM results factsheet to {results_file}")
            
            if deterministic_results.get('method_card'):
                method_file = output_dir / 'method_card_deterministic.json'
                with open(method_file, 'w') as f:
                    json.dump(deterministic_results['method_card'].__dict__, f, default=str, indent=2)
                self.logger.info(f"Persisted deterministic method card to {method_file}")
            
            if deterministic_results.get('results_factsheet'):
                results_file = output_dir / 'results_factsheet_deterministic.json'
                with open(results_file, 'w') as f:
                    json.dump(deterministic_results['results_factsheet'].__dict__, f, default=str, indent=2)
                self.logger.info(f"Persisted deterministic results factsheet to {results_file}")
                
        except Exception as e:
            self.logger.error(f"Failed to persist pre-fusion artifacts: {str(e)}")
    
    def _write_failure_report(
        self, 
        errors: List[str], 
        llm_results: Dict[str, Any], 
        deterministic_results: Dict[str, Any]
    ):
        """Write a failure report when fusion fails."""
        import json
        from pathlib import Path
        from datetime import datetime
        
        try:
            # Create output directory if it doesn't exist
            output_dir = Path("test_outputs/pmc2978916_debug")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create failure report
            failure_report = {
                'timestamp': datetime.now().isoformat(),
                'fusion_failed': True,
                'errors': errors,
                'llm_path_status': {
                    'success': llm_results.get('success', False),
                    'method_card_produced': llm_results.get('method_card') is not None,
                    'results_factsheet_produced': llm_results.get('results_factsheet') is not None,
                    'claims_count': len(llm_results.get('claims', [])),
                    'facts_count': len(llm_results.get('facts', []))
                },
                'deterministic_path_status': {
                    'success': deterministic_results.get('success', False),
                    'method_card_produced': deterministic_results.get('method_card') is not None,
                    'results_factsheet_produced': deterministic_results.get('results_factsheet') is not None,
                    'claims_count': len(deterministic_results.get('claims', [])),
                    'facts_count': len(deterministic_results.get('facts', []))
                },
                'recommendations': [
                    "Check pre-fusion artifacts in claims_*.jsonl and facts_*.jsonl files",
                    "Review LLM and deterministic path outputs separately",
                    "Verify evidence spans contain required concepts",
                    "Check for missing must-hit spans in the document"
                ]
            }
            
            # Write failure report
            failure_file = output_dir / 'failure_report.json'
            with open(failure_file, 'w') as f:
                json.dump(failure_report, f, indent=2, default=str)
            
            self.logger.info(f"Failure report written to {failure_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to write failure report: {str(e)}")
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get the current status of the pipeline."""
        return {
            'llm_path_enabled': self.enable_llm_path,
            'deterministic_path_enabled': self.enable_deterministic_path,
            'late_fusion_enabled': self.enable_late_fusion,
            'llm_workers': list(self.llm_workers.keys()),
            'deterministic_workers': list(self.deterministic_workers.keys())
        }
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update the pipeline configuration."""
        self.config.update(new_config)
        
        # Update flags
        self.enable_llm_path = self.config.get('enable_llm_path', True)
        self.enable_deterministic_path = self.config.get('enable_deterministic_path', True)
        self.enable_late_fusion = self.config.get('enable_late_fusion', True)
        
        # Reinitialize workers if needed
        if new_config.get('reinitialize_workers', False):
            self._initialize_workers()
        
        self.logger.info(f"Configuration updated: {new_config}")
    
    def fuse(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fuse LLM and deterministic results with ambiguity tracking.
        
        Args:
            inputs: Dict containing:
                - llm_method_card: MethodCard from LLM path
                - llm_results_factsheet: ResultsFactsheet from LLM path
                - deterministic_method_card: MethodCard from deterministic path
                - deterministic_results_factsheet: ResultsFactsheet from deterministic path
                - evidence_spans: List[EvidenceSpan] - All evidence spans
                
        Returns:
            Dict containing fused artifacts and ambiguity ledger
        """
        try:
            start_time = time.time()
            
            llm_method_card = inputs.get('llm_method_card')
            llm_results_factsheet = inputs.get('llm_results_factsheet')
            deterministic_method_card = inputs.get('deterministic_method_card')
            deterministic_results_factsheet = inputs.get('deterministic_results_factsheet')
            evidence_spans = inputs.get('evidence_spans', [])
            
            # Create ambiguity ledger
            ambiguity_ledger = {
                'results': [],
                'method': [],
                'fusion_decisions': [],
                'path_failures': []
            }
            
            # Create span index for section lookup
            span_index = {span.span_id: {'section': span.section} for span in evidence_spans}
            
            # Fuse MethodCard
            fused_method_card = self._fuse_method_cards(
                llm_method_card, deterministic_method_card, ambiguity_ledger, span_index
            )
            
            # Fuse ResultsFactsheet
            fused_results_factsheet = self._fuse_results_factsheets(
                llm_results_factsheet, deterministic_results_factsheet, ambiguity_ledger, evidence_spans
            )
            
            # Validate fused artifacts
            all_artifacts = []
            if fused_method_card:
                all_artifacts.append(fused_method_card)
            if fused_results_factsheet:
                all_artifacts.append(fused_results_factsheet)
            
            if all_artifacts:
                is_valid, errors = validate_all_artifacts(all_artifacts)
                if not is_valid:
                    return {
                        'success': False,
                        'error_message': f"Fused artifacts validation failed: {errors}",
                        'fused_artifacts': [],
                        'ambiguity_ledger': ambiguity_ledger
                    }
            
            execution_time = time.time() - start_time
            
            return {
                'success': True,
                'method_card': fused_method_card,
                'results_factsheet': fused_results_factsheet,
                'ambiguity_ledger': ambiguity_ledger,
                'execution_time': execution_time
            }
            
        except Exception as e:
            return {
                'success': False,
                'error_message': f"Late fusion failed: {str(e)}",
                'fused_artifacts': [],
                'ambiguity_ledger': {}
            }
    
    def _fuse_method_cards(self, llm_card: Optional[MethodCard], 
                          deterministic_card: Optional[MethodCard],
                          ambiguity_ledger: Dict[str, Any], span_index: Optional[Dict] = None) -> Optional[MethodCard]:
        """Fuse LLM and deterministic method cards with field-specific rules."""
        if not llm_card and not deterministic_card:
            return None
        
        if not llm_card:
            ambiguity_ledger['path_failures'].append('llm_method_card')
            return deterministic_card
        
        if not deterministic_card:
            ambiguity_ledger['path_failures'].append('deterministic_method_card')
            return llm_card
        
        # Field-specific fusion rules
        fused_fields = {}
        
        # Survival method fusion
        survival_winner = self._fuse_survival_method(
            llm_card.survival_method, deterministic_card.survival_method,
            llm_card, deterministic_card, ambiguity_ledger
        )
        fused_fields['survival_method'] = survival_winner
        
        # Interim looks fusion
        interim_winner = self._fuse_interim_looks(
            llm_card.interim_looks, deterministic_card.interim_looks,
            llm_card, deterministic_card, ambiguity_ledger
        )
        fused_fields['interim_looks'] = interim_winner
        
        # Ascertainment fusion
        ascertainment_winner = self._fuse_ascertainment(
            llm_card.ascertainment, deterministic_card.ascertainment,
            llm_card, deterministic_card, ambiguity_ledger
        )
        fused_fields['ascertainment'] = ascertainment_winner
        
        # Analysis denominators fusion
        llm_response_n = getattr(llm_card.analysis_denominators, 'response_n', None) if hasattr(llm_card, 'analysis_denominators') else None
        det_response_n = getattr(deterministic_card.analysis_denominators, 'response_n', None) if hasattr(deterministic_card, 'analysis_denominators') else None
        response_n_winner = self._fuse_denominator(
            llm_response_n, det_response_n,
            'response_n', llm_card, deterministic_card, ambiguity_ledger
        )
        
        llm_ttp_os_n = getattr(llm_card.analysis_denominators, 'ttp_os_n', None) if hasattr(llm_card, 'analysis_denominators') else None
        det_ttp_os_n = getattr(deterministic_card.analysis_denominators, 'ttp_os_n', None) if hasattr(deterministic_card, 'analysis_denominators') else None
        ttp_os_n_winner = self._fuse_denominator(
            llm_ttp_os_n, det_ttp_os_n,
            'ttp_os_n', llm_card, deterministic_card, ambiguity_ledger
        )
        
        # Store fused denominators in analysis_denominators structure
        fused_fields['analysis_denominators'] = {
            'response_n': response_n_winner,
            'ttp_os_n': ttp_os_n_winner
        }
        
        # Site geography fusion (Methods-only constraint)
        site_winner = self._fuse_site_geography(
            llm_card.site_geography, deterministic_card.site_geography,
            llm_card, deterministic_card, ambiguity_ledger, span_index
        )
        fused_fields['site_geography'] = site_winner
        
        # Study phase fusion - deterministic overrides LLM if both present
        study_phase_winner = self._fuse_study_phase(
            getattr(llm_card, 'study_phase', None), 
            getattr(deterministic_card, 'study_phase', None),
            llm_card, deterministic_card, ambiguity_ledger
        )
        fused_fields['study_phase'] = study_phase_winner
        
        # Combine span IDs
        all_span_ids = list(set(llm_card.span_ids + deterministic_card.span_ids))
        
        # Handle doc_id conflicts - if inputs disagree or missing, use run doc_id and log warning
        doc_id = None
        llm_doc_id = getattr(llm_card, 'doc_id', None)
        det_doc_id = getattr(deterministic_card, 'doc_id', None)
        
        if llm_doc_id and det_doc_id:
            if llm_doc_id != det_doc_id:
                # Log warning about doc_id mismatch
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"doc_id mismatch in MethodCard fusion: LLM={llm_doc_id}, Det={det_doc_id}. Using run doc_id.")
                # Use run doc_id from evidence spans
                if evidence_spans and len(evidence_spans) > 0:
                    doc_id = evidence_spans[0].doc_id
                else:
                    # Fallback to LLM doc_id
                    doc_id = llm_doc_id
            else:
                # Both agree
                doc_id = llm_doc_id
        elif llm_doc_id:
            doc_id = llm_doc_id
        elif det_doc_id:
            doc_id = det_doc_id
        else:
            # Neither has doc_id, try to get from evidence spans
            if evidence_spans and len(evidence_spans) > 0:
                doc_id = evidence_spans[0].doc_id
            else:
                raise ValueError("Cannot create fused MethodCard without a valid doc_id")
        
        # Create fused MethodCard
        fused_card = MethodCard(
            doc_id=doc_id,
            survival_method=fused_fields['survival_method'],
            interim_looks=fused_fields['interim_looks'],
            ascertainment=fused_fields['ascertainment'],
            analysis_denominators=fused_fields['analysis_denominators'],
            site_geography=fused_fields['site_geography'],
            study_phase=fused_fields['study_phase'],
            span_ids=all_span_ids,
            confidence_score=0.90,  # High confidence for fused result
            source_path="fused"
        )
        
        return fused_card
    
    def _fuse_survival_method(self, llm_value, det_value, llm_card, det_card, ambiguity_ledger):
        """Fuse survival method with precedence: KM > inferred_KM > not_reported."""
        if llm_value == det_value:
            return llm_value
        
        # Precedence order
        precedence = ['KM', 'INFERRED_KM', 'NOT_REPORTED']
        
        llm_rank = precedence.index(llm_value) if llm_value in precedence else len(precedence)
        det_rank = precedence.index(det_value) if det_value in precedence else len(precedence)
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': 'survival_method',
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids}
            ],
            'winner': 'llm' if llm_rank < det_rank else 'deterministic',
            'reason': f'precedence: {llm_value} vs {det_value}'
        })
        
        return llm_value if llm_rank < det_rank else det_value
    
    def _fuse_interim_looks(self, llm_value, det_value, llm_card, det_card, ambiguity_ledger):
        """Fuse interim looks as int count - choose the one with stronger evidence."""
        if llm_value == det_value:
            return llm_value
        
        # Treat as integers - prefer non-None values, then prefer larger counts
        if llm_value is None and det_value is not None:
            winner = 'deterministic'
        elif det_value is None and llm_value is not None:
            winner = 'llm'
        elif llm_value is not None and det_value is not None:
            # Both have values, prefer the one with more span evidence
            llm_span_count = len(llm_card.span_ids)
            det_span_count = len(det_card.span_ids)
            if llm_span_count > det_span_count:
                winner = 'llm'
            elif det_span_count > llm_span_count:
                winner = 'deterministic'
            else:
                # Equal span evidence, prefer larger interim looks count
                winner = 'llm' if llm_value >= det_value else 'deterministic'
        else:
            # Both None
            winner = 'llm'
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': 'interim_looks',
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids}
            ],
            'winner': winner,
            'reason': f'interim_looks count fusion: {llm_value} vs {det_value}'
        })
        
        return llm_value if winner == 'llm' else det_value
    
    def _fuse_ascertainment(self, llm_value, det_value, llm_card, det_card, ambiguity_ledger):
        """Fuse ascertainment strings - compare ascertainment types only (cadence is separate field)."""
        if llm_value == det_value:
            return llm_value
        
        # Precedence order for ascertainment types only
        precedence = ['RECIST', 'NOT_REPORTED']
        
        llm_rank = precedence.index(llm_value) if llm_value in precedence else len(precedence)
        det_rank = precedence.index(det_value) if det_value in precedence else len(precedence)
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': 'ascertainment',
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids}
            ],
            'winner': 'llm' if llm_rank < det_rank else 'deterministic',
            'reason': f'ascertainment type precedence: {llm_value} vs {det_value}'
        })
        
        return llm_value if llm_rank < det_rank else det_value
    
    def _fuse_denominator(self, llm_value, det_value, field_name, llm_card, det_card, ambiguity_ledger):
        """Fuse denominators preferring non-None values."""
        if llm_value == det_value:
            return llm_value
        
        # Prefer non-None values
        if llm_value is None and det_value is not None:
            winner = 'deterministic'
        elif det_value is None and llm_value is not None:
            winner = 'llm'
        else:
            # Both have values, prefer the one with more span evidence
            llm_span_count = len(llm_card.span_ids)
            det_span_count = len(det_card.span_ids)
            winner = 'llm' if llm_span_count >= det_span_count else 'deterministic'
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': field_name,
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids}
            ],
            'winner': winner,
            'reason': f'denominator fusion: {llm_value} vs {det_value}'
        })
        
        return llm_value if winner == 'llm' else det_value
    
    def _fuse_site_geography(self, llm_value, det_value, llm_card, det_card, ambiguity_ledger, span_index=None):
        """Fuse site geography with Methods-only constraint using proper span section lookup."""
        if llm_value == det_value:
            return llm_value
        
        # Check if either has Methods section spans using proper span-index lookup
        llm_has_methods = False
        det_has_methods = False
        
        if span_index:
            # Use span-index to check sections
            llm_has_methods = any(
                span_index.get(span_id, {}).get('section', '').lower() in ['methods', 'protocol', 'sap']
                for span_id in llm_card.span_ids
            )
            det_has_methods = any(
                span_index.get(span_id, {}).get('section', '').lower() in ['methods', 'protocol', 'sap']
                for span_id in det_card.span_ids
            )
        else:
            # Fallback: assume no Methods evidence if no span index provided
            llm_has_methods = False
            det_has_methods = False
        
        # Prefer the one with Methods section evidence
        if llm_has_methods and not det_has_methods:
            winner = 'llm'
        elif det_has_methods and not llm_has_methods:
            winner = 'deterministic'
        else:
            # Both or neither have Methods evidence, use precedence
            precedence = ['MULTICENTER', 'SINGLE_CENTER', 'NOT_REPORTED']
            llm_rank = precedence.index(llm_value) if llm_value in precedence else len(precedence)
            det_rank = precedence.index(det_value) if det_value in precedence else len(precedence)
            winner = 'llm' if llm_rank < det_rank else 'deterministic'
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': 'site_geography',
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids, 'has_methods': llm_has_methods},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids, 'has_methods': det_has_methods}
            ],
            'winner': winner,
            'reason': f'site geography fusion: {llm_value} vs {det_value}, methods evidence: llm={llm_has_methods}, det={det_has_methods}'
        })
        
        return llm_value if winner == 'llm' else det_value
    
    def _fuse_results_factsheets(self, llm_factsheet: Optional[ResultsFactsheet],
                                deterministic_factsheet: Optional[ResultsFactsheet],
                                ambiguity_ledger: Dict[str, Any],
                                evidence_spans: Optional[List[EvidenceSpan]] = None) -> Optional[ResultsFactsheet]:
        """Fuse LLM and deterministic results factsheets with precedence rules."""
        if not llm_factsheet and not deterministic_factsheet:
            return None
        
        if not llm_factsheet:
            ambiguity_ledger['path_failures'].append('llm_results_factsheet')
            return deterministic_factsheet
        
        if not deterministic_factsheet:
            ambiguity_ledger['path_failures'].append('deterministic_results_factsheet')
            return llm_factsheet
        
        # Create metric key mapping for fusion
        llm_metrics = {self._get_metric_key(m): m for m in llm_factsheet.results}
        det_metrics = {self._get_metric_key(m): m for m in deterministic_factsheet.results}
        
        # Get all unique metric keys
        all_keys = set(llm_metrics.keys()) | set(det_metrics.keys())
        
        fused_metrics = []
        
        for key in all_keys:
            llm_metric = llm_metrics.get(key)
            det_metric = det_metrics.get(key)
            
            if llm_metric and det_metric:
                # Both paths have this metric - fuse them
                fused_metric = self._fuse_metric(llm_metric, det_metric, ambiguity_ledger)
                fused_metrics.append(fused_metric)
            elif llm_metric:
                # Only LLM has this metric
                fused_metrics.append(llm_metric)
            else:
                # Only deterministic has this metric
                fused_metrics.append(det_metric)
        
        # Combine span IDs
        all_span_ids = list(set(llm_factsheet.span_ids + deterministic_factsheet.span_ids))
        
        # Handle doc_id conflicts - if inputs disagree or missing, use run doc_id and log warning
        doc_id = None
        llm_doc_id = getattr(llm_factsheet, 'doc_id', None)
        det_doc_id = getattr(deterministic_factsheet, 'doc_id', None)
        
        if llm_doc_id and det_doc_id:
            if llm_doc_id != det_doc_id:
                # Log warning about doc_id mismatch
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"doc_id mismatch in fusion: LLM={llm_doc_id}, Det={det_doc_id}. Using run doc_id.")
                # Use run doc_id from evidence spans
                if evidence_spans and len(evidence_spans) > 0:
                    doc_id = evidence_spans[0].doc_id
                else:
                    # Fallback to LLM doc_id
                    doc_id = llm_doc_id
            else:
                # Both agree
                doc_id = llm_doc_id
        elif llm_doc_id:
            doc_id = llm_doc_id
        elif det_doc_id:
            doc_id = det_doc_id
        else:
            # Neither has doc_id, try to get from evidence spans
            if evidence_spans and len(evidence_spans) > 0:
                doc_id = evidence_spans[0].doc_id
            else:
                raise ValueError("Cannot create fused ResultsFactsheet without a valid doc_id")
        
        # Create fused ResultsFactsheet
        fused_factsheet = ResultsFactsheet(
            results=fused_metrics,
            span_ids=all_span_ids,
            doc_id=doc_id
        )
        
        return fused_factsheet
    
    def _get_metric_key(self, metric: Dict[str, Any]) -> str:
        """Create a unique key for a metric based on metric, timepoint, and analysis set."""
        return f"{metric.get('metric', '')}_{metric.get('timepoint', '')}_{metric.get('analysis_set', '')}"
    
    def _fuse_metric(self, llm_metric: Dict[str, Any], det_metric: Dict[str, Any], 
                    ambiguity_ledger: Dict[str, Any]) -> Dict[str, Any]:
        """Fuse a single metric using precedence rules."""
        metric_key = self._get_metric_key(llm_metric)
        
        # Check if values are within tolerance
        llm_value = llm_metric.get('value')
        det_value = det_metric.get('value')
        
        if llm_value is not None and det_value is not None:
            tolerance = abs(llm_value) * self.epsilon_pct
            values_agree = abs(llm_value - det_value) <= tolerance
        else:
            values_agree = llm_value == det_value
        
        if values_agree:
            # Values agree within tolerance - use precedence rules
            winner = self._apply_metric_precedence(llm_metric, det_metric)
        else:
            # Values disagree - use confidence scores
            llm_confidence = llm_metric.get('confidence', 0.5)
            det_confidence = det_metric.get('confidence', 0.5)
            winner = 'llm' if llm_confidence >= det_confidence else 'deterministic'
        
        # Record in ambiguity ledger
        ambiguity_ledger['results'].append({
            'metric': llm_metric.get('metric'),
            'key': metric_key,
            'candidates': [
                {
                    'path': 'llm',
                    'value': llm_value,
                    'n': llm_metric.get('n'),
                    'anchoring': llm_metric.get('anchoring', 'unknown'),
                    'span_ids': llm_metric.get('span_ids', []),
                    'confidence': llm_metric.get('confidence', 0.5)
                },
                {
                    'path': 'deterministic',
                    'value': det_value,
                    'n': det_metric.get('n'),
                    'anchoring': det_metric.get('anchoring', 'unknown'),
                    'span_ids': det_metric.get('span_ids', []),
                    'confidence': det_metric.get('confidence', 0.5)
                }
            ],
            'winner': winner,
            'reason': f'values agree: {values_agree}, winner: {winner}'
        })
        
        return llm_metric if winner == 'llm' else det_metric
    
    def _apply_metric_precedence(self, llm_metric: Dict[str, Any], det_metric: Dict[str, Any]) -> str:
        """Apply precedence rules to choose between metrics using configured precedence."""
        # Use configured denom_precedence for anchoring precedence
        anchoring_precedence = {}
        for i, anchor_type in enumerate(self.denom_precedence):
            anchoring_precedence[anchor_type] = len(self.denom_precedence) - i
        anchoring_precedence['unknown'] = 0
        
        llm_anchoring = llm_metric.get('anchoring', 'unknown')
        det_anchoring = det_metric.get('anchoring', 'unknown')
        
        llm_anchoring_score = anchoring_precedence.get(llm_anchoring, 0)
        det_anchoring_score = anchoring_precedence.get(det_anchoring, 0)
        
        if llm_anchoring_score > det_anchoring_score:
            return 'llm'
        elif det_anchoring_score > llm_anchoring_score:
            return 'deterministic'
        
        # Anchoring scores are equal, check denominator quality
        llm_n = llm_metric.get('n')
        det_n = det_metric.get('n')
        
        if llm_n is not None and det_n is None:
            return 'llm'
        elif det_n is not None and llm_n is None:
            return 'deterministic'
        elif llm_n is not None and det_n is not None:
            # Both have denominators, prefer larger n (when both legitimate)
            if llm_n > det_n:
                return 'llm'
            elif det_n > llm_n:
                return 'deterministic'
        
        # All else equal, use confidence scores
        llm_confidence = llm_metric.get('confidence', 0.5)
        det_confidence = det_metric.get('confidence', 0.5)
        
        return 'llm' if llm_confidence >= det_confidence else 'deterministic'
    
    def _fuse_study_phase(self, llm_value, det_value, llm_card, det_card, ambiguity_ledger):
        """Fuse study phase with deterministic override if both present."""
        if llm_value == det_value:
            return llm_value
        
        # If deterministic has a value and LLM has a value, deterministic overrides
        if det_value is not None and det_value != 'not_reported':
            winner = 'deterministic'
            reason = 'deterministic override for study phase'
        elif llm_value is not None and llm_value != 'not_reported':
            winner = 'llm'
            reason = 'only LLM has valid study phase'
        else:
            # Both None or both 'not_reported'
            winner = 'llm'
            reason = 'default to LLM when both paths have no valid study phase'
        
        # Record in ambiguity ledger
        ambiguity_ledger['method'].append({
            'field': 'study_phase',
            'candidates': [
                {'path': 'llm', 'value': llm_value, 'span_ids': llm_card.span_ids},
                {'path': 'deterministic', 'value': det_value, 'span_ids': det_card.span_ids}
            ],
            'winner': winner,
            'reason': reason
        })
        
        return det_value if winner == 'deterministic' else llm_value
