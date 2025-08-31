"""
Late Fusion Orchestrator

Implements dual-path processing by default, combining LLM and deterministic workers
with global validators for provenance, units, and section constraints.
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
from ..validators import validate_all_artifacts


class LateFusionOrchestrator:
    """
    Orchestrates dual-path processing with late fusion of LLM and deterministic results.
    
    Implements the dual-path architecture from the Study Card Overhaul:
    - LLM Path: MethodAuditor, ResultsDistiller, Claimizer, CounterEvidenceMiner
    - Deterministic Path: GateValidator, GateAssessor
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
        
        # Dual-path configuration
        self.enable_llm_path = self.config.get('enable_llm_path', True)
        self.enable_deterministic_path = self.config.get('enable_deterministic_path', True)
        self.enable_late_fusion = self.config.get('enable_late_fusion', True)
        
        # Worker instances
        self.llm_workers = {}
        self.deterministic_workers = {}
        
        # Initialize workers based on configuration
        self._initialize_workers()
        
    def _initialize_workers(self):
        """Initialize worker instances based on configuration."""
        if self.enable_llm_path:
            try:
                # Dynamic imports to avoid SQLAlchemy conflicts
                from ..workers.llm.method_auditor import MethodAuditor
                from ..workers.llm.results_distiller import ResultsDistiller
                from ..workers.llm.claimizer import Claimizer
                from ..workers.llm.counter_evidence_miner import CounterEvidenceMiner
                
                self.llm_workers = {
                    'method_auditor': MethodAuditor(),
                    'results_distiller': ResultsDistiller(),
                    'claimizer': Claimizer(),
                    'counter_evidence_miner': CounterEvidenceMiner()
                }
                self.logger.info("LLM path workers initialized")
            except ImportError as e:
                self.logger.warning(f"Could not initialize LLM workers: {e}")
                self.llm_workers = {}
        
        if self.enable_deterministic_path:
            try:
                # Dynamic imports to avoid SQLAlchemy conflicts
                from ..workers.deterministic.gate_validator import GateValidator
                from ..workers.deterministic.gate_assessor import GateAssessor
                
                self.deterministic_workers = {
                    'gate_validator': GateValidator(),
                    'gate_assessor': GateAssessor()
                }
                self.logger.info("Deterministic path workers initialized")
            except ImportError as e:
                self.logger.warning(f"Could not initialize deterministic workers: {e}")
                self.deterministic_workers = {}
    
    def process_pipeline(
        self, 
        evidence_spans: List[EvidenceSpan],
        trial_context: Dict[str, Any],
        design_json: Optional[Dict[str, Any]] = None,
        pocket_context: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Run the complete dual-path pipeline with late fusion.
        
        Args:
            evidence_spans: List of evidence spans to process
            trial_context: Trial context information
            design_json: Optional design JSON for MethodAuditor
            pocket_context: Optional pocket context card
            
        Returns:
            Dictionary containing all pipeline outputs
        """
        start_time = time.time()
        self.logger.info("Starting dual-path pipeline processing")
        
        pipeline_results = {
            'success': False,
            'pipeline_config': {
                'enable_llm_path': self.enable_llm_path,
                'enable_deterministic_path': self.enable_deterministic_path,
                'enable_late_fusion': self.enable_late_fusion
            },
            'execution_time': 0.0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Step 1: Span validation and preprocessing
            self.logger.info("Step 1: Validating and preprocessing evidence spans")
            validation_result = self._validate_spans(evidence_spans)
            if not validation_result['is_valid']:
                pipeline_results['errors'].extend(validation_result['errors'])
                return pipeline_results
            
            # Step 2: LLM Path Processing
            llm_results = {}
            if self.enable_llm_path:
                self.logger.info("Step 2: Processing LLM path")
                llm_results = self._process_llm_path(
                    evidence_spans, trial_context, design_json, pocket_context
                )
                if not llm_results['success']:
                    pipeline_results['errors'].extend(llm_results['errors'])
                    return pipeline_results
            
            # Step 3: Deterministic Path Processing
            deterministic_results = {}
            if self.enable_deterministic_path:
                self.logger.info("Step 3: Processing deterministic path")
                deterministic_results = self._process_deterministic_path(
                    evidence_spans, trial_context, llm_results
                )
                if not deterministic_results['success']:
                    pipeline_results['warnings'].extend(deterministic_results['warnings'])
            
            # Step 4: Late Fusion and Global Validation
            fusion_results = {}
            if self.enable_late_fusion:
                self.logger.info("Step 4: Late fusion and global validation")
                fusion_results = self._perform_late_fusion(
                    llm_results, deterministic_results, evidence_spans
                )
                if not fusion_results['success']:
                    pipeline_results['errors'].extend(fusion_results['errors'])
                    return pipeline_results
            
            # Step 5: Final validation and output preparation
            self.logger.info("Step 5: Final validation and output preparation")
            final_results = self._prepare_final_output(
                llm_results, deterministic_results, fusion_results
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
    
    def _validate_spans(self, evidence_spans: List[EvidenceSpan]) -> Dict[str, Any]:
        """Validate evidence spans against global rules."""
        validation_result = {
            'is_valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Global validation
            is_valid, errors = validate_all_artifacts(evidence_spans)
            
            if not is_valid:
                validation_result['errors'].extend(errors)
                return validation_result
            
            # Span-specific validation
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
    
    def _process_llm_path(
        self, 
        evidence_spans: List[EvidenceSpan],
        trial_context: Dict[str, Any],
        design_json: Optional[Dict[str, Any]],
        pocket_context: Optional[Any]
    ) -> Dict[str, Any]:
        """Process the LLM path with all LLM workers."""
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
            # Method Auditor
            if 'method_auditor' in self.llm_workers:
                self.logger.info("Running Method Auditor")
                method_result = self.llm_workers['method_auditor'].process({
                    'evidence_spans': [s for s in evidence_spans if s.section.lower() in ['methods', 'protocol', 'sap']],
                    'design_json': design_json or {},
                    'pocket_context': pocket_context
                })
                
                if method_result.success:
                    llm_results['method_card'] = method_result.output.get('method_card')
                else:
                    llm_results['errors'].append(f"Method Auditor failed: {method_result.error_message}")
            
            # Results Distiller
            if 'results_distiller' in self.llm_workers:
                self.logger.info("Running Results Distiller")
                results_result = self.llm_workers['results_distiller'].process({
                    'evidence_spans': [s for s in evidence_spans if s.section.lower() in ['results', 'abstract', 'table']],
                    'trial_context': trial_context
                })
                
                if results_result.success:
                    llm_results['results_factsheet'] = results_result.output.get('results_factsheet')
                else:
                    llm_results['errors'].append(f"Results Distiller failed: {results_result.error_message}")
            
            # Claimizer
            if 'claimizer' in self.llm_workers:
                self.logger.info("Running Claimizer")
                claim_result = self.llm_workers['claimizer'].process({
                    'evidence_spans': evidence_spans
                })
                
                if claim_result.success:
                    llm_results['claims'] = claim_result.output.get('claims')
                else:
                    llm_results['errors'].append(f"Claimizer failed: {claim_result.error_message}")
            
            # Counter Evidence Miner
            if 'counter_evidence_miner' in self.llm_workers:
                self.logger.info("Running Counter Evidence Miner")
                counter_result = self.llm_workers['counter_evidence_miner'].process({
                    'corpus_spans': evidence_spans,
                    'gate_families': ['G1_signal', 'G2_mechanism_delivery', 'G3_design'],
                    'existing_claims': llm_results.get('claims', [])
                })
                
                if counter_result.success:
                    llm_results['contradicting_claims'] = counter_result.output.get('contradicting_claims')
                else:
                    llm_results['errors'].append(f"Counter Evidence Miner failed: {counter_result.error_message}")
            
            # Check if we have the minimum required outputs
            if llm_results['method_card'] and llm_results['results_factsheet']:
                llm_results['success'] = True
            else:
                llm_results['errors'].append("Missing required outputs from LLM path")
            
            llm_results['execution_time'] = time.time() - start_time
            
        except Exception as e:
            llm_results['errors'].append(f"LLM path processing failed: {str(e)}")
            llm_results['execution_time'] = time.time() - start_time
        
        return llm_results
    
    def _process_deterministic_path(
        self, 
        evidence_spans: List[EvidenceSpan],
        trial_context: Dict[str, Any],
        llm_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process the deterministic path with rule-based workers."""
        deterministic_results = {
            'success': False,
            'gate_validations': None,
            'gate_assessments': None,
            'warnings': [],
            'execution_time': 0.0
        }
        
        start_time = time.time()
        
        try:
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
            
            deterministic_results['success'] = True
            deterministic_results['execution_time'] = time.time() - start_time
            
        except Exception as e:
            deterministic_results['warnings'].append(f"Deterministic path processing failed: {str(e)}")
            deterministic_results['execution_time'] = time.time() - start_time
        
        return deterministic_results
    
    def _perform_late_fusion(
        self, 
        llm_results: Dict[str, Any],
        deterministic_results: Dict[str, Any],
        evidence_spans: List[EvidenceSpan]
    ) -> Dict[str, Any]:
        """Perform late fusion of LLM and deterministic results with global validation."""
        fusion_results = {
            'success': False,
            'fused_artifacts': [],
            'validation_results': {},
            'errors': [],
            'execution_time': 0.0
        }
        
        start_time = time.time()
        
        try:
            # Collect all artifacts for fusion
            all_artifacts = []
            
            if llm_results.get('method_card'):
                all_artifacts.append(llm_results['method_card'])
            
            if llm_results.get('results_factsheet'):
                if isinstance(llm_results['results_factsheet'], list):
                    all_artifacts.extend(llm_results['results_factsheet'])
                else:
                    all_artifacts.append(llm_results['results_factsheet'])
            
            if llm_results.get('claims'):
                all_artifacts.extend(llm_results['claims'])
            
            if llm_results.get('contradicting_claims'):
                for family_claims in llm_results['contradicting_claims'].values():
                    all_artifacts.extend(family_claims)
            
            # Global validation of all artifacts
            self.logger.info(f"Validating {len(all_artifacts)} artifacts with global validator")
            is_valid, errors = validate_all_artifacts(all_artifacts)
            
            if not is_valid:
                fusion_results['errors'].extend(errors)
                return fusion_results
            
            # Apply late fusion rules
            fused_artifacts = self._apply_late_fusion_rules(all_artifacts)
            
            # Validate fused artifacts
            is_valid_fused, fusion_errors = validate_all_artifacts(fused_artifacts)
            
            if not is_valid_fused:
                fusion_results['errors'].extend(fusion_errors)
                return fusion_results
            
            fusion_results['fused_artifacts'] = fused_artifacts
            fusion_results['success'] = True
            fusion_results['execution_time'] = time.time() - start_time
            
            self.logger.info(f"Late fusion completed successfully with {len(fused_artifacts)} artifacts")
            
        except Exception as e:
            fusion_results['errors'].append(f"Late fusion failed: {str(e)}")
            fusion_results['execution_time'] = time.time() - start_time
        
        return fusion_results
    
    def _apply_late_fusion_rules(self, artifacts: List[Any]) -> List[Any]:
        """Apply late fusion rules to combine and enhance artifacts."""
        fused_artifacts = []
        
        # Group artifacts by type
        method_cards = [a for a in artifacts if hasattr(a, 'estimand')]
        results_factsheets = [a for a in artifacts if hasattr(a, 'results')]
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
        
        # Add claim references to method card
        if supporting_claims:
            method_card.provenance_anchors.extend([claim.claim_id for claim in supporting_claims])
        
        return method_card
    
    def _enhance_results_factsheet(self, factsheet: ResultsFactsheet, claims: List[Claim]) -> ResultsFactsheet:
        """Enhance results factsheet with relevant claims."""
        # Find claims that support results
        supporting_claims = [
            claim for claim in claims 
            if claim.type == 'effect_size' and claim.stance == 'supports'
        ]
        
        # Add claim references to factsheet
        for result in factsheet.results:
            # Find relevant claims for this result
            relevant_claims = [
                claim for claim in supporting_claims
                if claim.endpoint and claim.endpoint.lower() in str(result).lower()
            ]
            
            if relevant_claims:
                result['claim_ids'] = [claim.claim_id for claim in relevant_claims]
        
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
