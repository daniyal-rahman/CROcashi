# src/ncfd/pipeline/study_card_pipeline.py
"""
Study Card Pipeline

Main pipeline for study card processing and evaluation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from ..extract.workers import (
    Retriever, MethodAuditor, ResultsDistiller, GateProposer,
    GateValidator, GateAssessor, FdaLens, MemoComposer,
    DeterministicMethodAuditor, DeterministicResultsDistiller
)
from ..extract.models import (
    DocumentCard, EvidenceSpan, Claim, MethodCard, ResultsFactsheet,
    PocketContextCard, GateCandidate, GateSpec, GateAssessment, DecisionRecord
)
from ..extract.validators import GlobalValidator
from ..extract.orchestrate import LateFusionOrchestrator
from ..extract.validators.section_constraints import enforce_section_constraints
from ..extract.normalization import get_metric_registry

logger = logging.getLogger(__name__)


@dataclass
class StudyCardPipelineResult:
    """Result of study card pipeline execution."""
    trial_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
    # Pipeline outputs
    document_cards: List[DocumentCard] = field(default_factory=list)
    evidence_spans: List[EvidenceSpan] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    method_card: Optional[MethodCard] = None
    results_factsheet: Optional[ResultsFactsheet] = None
    gate_candidates: List[GateCandidate] = field(default_factory=list)
    gate_specs: List[GateSpec] = field(default_factory=list)
    gate_assessments: List[GateAssessment] = field(default_factory=list)
    decision_record: Optional[DecisionRecord] = None
    
    # Dual-path and fusion outputs
    ambiguity_ledger: Dict[str, Any] = field(default_factory=dict)
    llm_artifacts: Dict[str, Any] = field(default_factory=dict)
    deterministic_artifacts: Dict[str, Any] = field(default_factory=dict)
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StudyCardPipeline:
    """Main pipeline for study card processing and evaluation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the study card pipeline.
        
        Args:
            config: Configuration dictionary with validation settings
        """
        self.config = config or {}
        self.retriever = Retriever()
        
        # LLM Path Workers
        self.llm_method_auditor = MethodAuditor()
        self.llm_results_distiller = ResultsDistiller()
        
        # Deterministic Path Workers
        self.deterministic_method_auditor = DeterministicMethodAuditor()
        self.deterministic_results_distiller = DeterministicResultsDistiller()
        
        # Late Fusion Orchestrator
        self.late_fusion_orchestrator = LateFusionOrchestrator()
        
        # Other workers
        self.gate_proposer = GateProposer()
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        self.fda_lens = FdaLens()
        self.memo_composer = MemoComposer()
        
        # Validation configuration
        validation_config = self.config.get('validation', {})
        self.strict_validation = validation_config.get('strict_validation', True)
        self.fail_fast_on_validation = validation_config.get('fail_fast_on_validation', True)
        self.validation_error_action = validation_config.get('validation_error_action', 'fail')
        self.max_validation_errors = validation_config.get('max_validation_errors', 10)
        
        # Specific validation rules
        self.hard_fail_on_provenance = validation_config.get('hard_fail_on_provenance', True)
        self.hard_fail_on_units = validation_config.get('hard_fail_on_units', True)
        self.hard_fail_on_denominators = validation_config.get('hard_fail_on_denominators', True)
        self.hard_fail_on_sections = validation_config.get('hard_fail_on_sections', True)
        
        logger.info(f"StudyCardPipeline initialized with strict_validation={self.strict_validation}")
    
    def _handle_validation_errors(self, result: StudyCardPipelineResult, 
                                artifact_type: str, errors: List[str]) -> bool:
        """
        Handle validation errors according to configuration.
        
        Args:
            result: Pipeline result object
            artifact_type: Type of artifact being validated
            errors: List of validation errors
            
        Returns:
            True if validation passed (no errors or warnings only), False if hard fail
        """
        if not errors:
            return True
            
        # Determine if these are hard-fail errors based on content
        hard_fail_errors = []
        warning_errors = []
        
        for error in errors:
            # Check if error is related to hard-fail categories
            is_hard_fail = (
                self.hard_fail_on_provenance and any(keyword in error.lower() for keyword in 
                    ['provenance', 'span_ids', 'input_hash', 'missing input_hash', 'no span references'])
                or self.hard_fail_on_units and any(keyword in error.lower() for keyword in 
                    ['units', 'invalid units'])
                or self.hard_fail_on_denominators and any(keyword in error.lower() for keyword in 
                    ['denominator', 'n cannot be default', 'pending_denominator'])
                or self.hard_fail_on_sections and any(keyword in error.lower() for keyword in 
                    ['section', 'missing required field'])
            )
            
            if is_hard_fail:
                hard_fail_errors.append(error)
            else:
                warning_errors.append(error)
        
        # Handle hard-fail errors
        if hard_fail_errors and self.strict_validation:
            result.errors.extend([f"{artifact_type} validation: {error}" for error in hard_fail_errors])
            if self.fail_fast_on_validation:
                return False
        
        # Handle warning errors
        if warning_errors:
            result.warnings.extend([f"{artifact_type} validation: {error}" for error in warning_errors])
        
        # Check if we've exceeded max validation errors
        if len(result.errors) >= self.max_validation_errors:
            result.errors.append(f"Exceeded maximum validation errors ({self.max_validation_errors})")
            return False
        
        return True
    
    def execute(self, trial_id: str, trial_context: Dict[str, Any]) -> StudyCardPipelineResult:
        """Execute the complete study card pipeline."""
        start_time = datetime.utcnow()
        result = StudyCardPipelineResult(
            trial_id=trial_id,
            success=False,
            start_time=start_time,
            end_time=start_time
        )
        
        try:
            logger.info(f"Starting study card pipeline for trial {trial_id}")
            
            # Stage 1: Document retrieval and triage
            logger.info("Stage 1: Document retrieval and triage")
            retrieval_result = self._execute_retrieval(trial_context)
            if not retrieval_result.success:
                result.errors.append(f"Retrieval failed: {retrieval_result.error_message}")
                return result
            
            result.document_cards = retrieval_result.output.get("document_cards", [])
            result.evidence_spans = retrieval_result.output.get("evidence_spans", [])
            
            # Stage 2: Dual-path Method Auditing
            logger.info("Stage 2: Dual-path Method Auditing")
            
            # LLM Path
            llm_method_result = self._execute_llm_method_auditing(trial_context, result.evidence_spans)
            if not llm_method_result.success:
                result.errors.append(f"LLM Method auditing failed: {llm_method_result.error_message}")
                return result
            
            # Deterministic Path
            deterministic_method_result = self._execute_deterministic_method_auditing(trial_context, result.evidence_spans)
            if not deterministic_method_result.success:
                result.errors.append(f"Deterministic Method auditing failed: {deterministic_method_result.error_message}")
                return result
            
            # Stage 3: Dual-path Results Distillation
            logger.info("Stage 3: Dual-path Results Distillation")
            
            # LLM Path
            llm_results_result = self._execute_llm_results_distillation(result.evidence_spans)
            if not llm_results_result.success:
                result.errors.append(f"LLM Results distillation failed: {llm_results_result.error_message}")
                return result
            
            # Deterministic Path
            deterministic_results_result = self._execute_deterministic_results_distillation(result.evidence_spans)
            if not deterministic_results_result.success:
                result.errors.append(f"Deterministic Results distillation failed: {deterministic_results_result.error_message}")
                return result
            
            # Stage 4: Late Fusion
            logger.info("Stage 4: Late Fusion")
            fusion_result = self._execute_late_fusion(
                llm_method_result.output,
                llm_results_result.output,
                deterministic_method_result.output,
                deterministic_results_result.output,
                result.evidence_spans
            )
            if not fusion_result.success:
                result.errors.append(f"Late fusion failed: {fusion_result.error_message}")
                return result
            
            # Use fused artifacts for downstream processing
            result.method_card = fusion_result.output['method_card']
            result.results_factsheet = fusion_result.output['results_factsheet']
            result.ambiguity_ledger = fusion_result.output.get('ambiguity_ledger', {})
            result.llm_artifacts = {
                'method_card': llm_method_result.output,
                'results_factsheet': llm_results_result.output
            }
            result.deterministic_artifacts = {
                'method_card': deterministic_method_result.output,
                'results_factsheet': deterministic_results_result.output
            }
            
            # Validate fused artifacts
            if result.method_card:
                is_valid, errors = GlobalValidator.validate_artifact(result.method_card, "MethodCard")
                if not self._handle_validation_errors(result, "MethodCard", errors):
                    return result
                
                # Validate MethodCard section constraints
                section_ok, section_errors = enforce_section_constraints(
                    method_card=result.method_card,
                    results_factsheet=None,
                    evidence_spans=result.evidence_spans
                )
                if not section_ok:
                    result.errors.extend([f"MethodCard section constraint: {e}" for e in section_errors])
                    return result
            
            if result.results_factsheet:
                is_valid, errors = GlobalValidator.validate_artifact(result.results_factsheet, "ResultsFactsheet")
                if not self._handle_validation_errors(result, "ResultsFactsheet", errors):
                    return result
                
                # Validate ResultsFactsheet section constraints
                section_ok, section_errors = enforce_section_constraints(
                    method_card=result.method_card,
                    results_factsheet=result.results_factsheet,
                    evidence_spans=result.evidence_spans
                )
                if not section_ok:
                    result.errors.extend([f"ResultsFactsheet section constraint: {e}" for e in section_errors])
                    return result
            
            # Stage 3.5: ResultsFactsheet normalization (guaranteed)
            logger.info("Stage 3.5: ResultsFactsheet normalization")
            normalization_result = self._execute_results_normalization(result.results_factsheet)
            if not normalization_result.success:
                result.errors.append(f"Results normalization failed: {normalization_result.error_message}")
                return result
            
            # Update results_factsheet with normalized data
            result.results_factsheet = normalization_result.output
            
            # Stage 5: Claim generation
            logger.info("Stage 5: Claim generation")
            claims_result = self._execute_claim_generation(result.evidence_spans)
            if not claims_result.success:
                result.errors.append(f"Claim generation failed: {claims_result.error_message}")
                return result
            
            result.claims = claims_result.output
            
            # Validate Claims provenance
            if result.claims:
                for claim in result.claims:
                    is_valid, errors = GlobalValidator.validate_artifact(claim, "Claim")
                    if not self._handle_validation_errors(result, "Claim", errors):
                        return result
            
            # Stage 6: Gate proposal
            logger.info("Stage 6: Gate proposal")
            gates_result = self._execute_gate_proposal(
                result.method_card, result.results_factsheet, result.claims, trial_context
            )
            if not gates_result.success:
                result.errors.append(f"Gate proposal failed: {gates_result.error_message}")
                return result
            
            result.gate_candidates = gates_result.output
            
            # Stage 7: Gate validation
            logger.info("Stage 7: Gate validation")
            validation_result = self._execute_gate_validation(result.gate_candidates, result.claims)
            if not validation_result.success:
                result.errors.append(f"Gate validation failed: {validation_result.error_message}")
                return result
            
            result.gate_specs = validation_result.output["validated_gates"]
            
            # Stage 7: Gate assessment
            logger.info("Stage 7: Gate assessment")
            assessment_result = self._execute_gate_assessment(result.gate_specs, result.claims)
            if not assessment_result.success:
                result.errors.append(f"Gate assessment failed: {assessment_result.error_message}")
                return result
            
            result.gate_assessments = assessment_result.output
            
            # Stage 8: Decision record creation
            logger.info("Stage 8: Decision record creation")
            decision_result = self._create_decision_record(
                trial_id, result.gate_assessments, result.claims
            )
            result.decision_record = decision_result
            
            # Stage 9: FDA lens analysis (optional)
            logger.info("Stage 9: FDA lens analysis")
            fda_result = self._execute_fda_lens(
                result.method_card, result.gate_assessments, result.decision_record
            )
            if fda_result.success:
                # Add FDA insights to decision record
                fda_gates = fda_result.output
                for gate in fda_gates:
                    result.decision_record.add_note(f"FDA recommendation: {gate.proposition}")
            
            # Stage 10: Memo composition (optional)
            logger.info("Stage 10: Memo composition")
            memo_result = self._execute_memo_composition(
                result.gate_assessments, result.decision_record, trial_context
            )
            if memo_result.success:
                memo = memo_result.output
                result.decision_record.add_link("memo", memo)
            
            # Mark pipeline as successful
            result.success = True
            result.end_time = datetime.utcnow()
            
            # Recalculate processing time after setting end_time
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            
            # Final comprehensive validation
            if not self._validate_all_artifacts(result):
                result.success = False
                logger.error(f"Study card pipeline failed validation for trial {trial_id}")
                return result
            
            logger.info(f"Study card pipeline completed successfully for trial {trial_id}")
            
        except Exception as e:
            result.end_time = datetime.utcnow()
            result.errors.append(f"Pipeline execution failed: {str(e)}")
            
            # Recalculate processing time after setting end_time
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            
            logger.error(f"Study card pipeline failed for trial {trial_id}: {str(e)}")
        
        return result
    
    def _validate_all_artifacts(self, result: StudyCardPipelineResult) -> bool:
        """
        Validate all artifacts comprehensively.
        
        Args:
            result: Pipeline result object
            
        Returns:
            True if all validations pass, False if any hard failures
        """
        # Validate MethodCard
        if result.method_card:
            is_valid, errors = GlobalValidator.validate_artifact(result.method_card, "MethodCard")
            if not self._handle_validation_errors(result, "MethodCard", errors):
                return False
        
        # Validate ResultsFactsheet
        if result.results_factsheet:
            is_valid, errors = GlobalValidator.validate_artifact(result.results_factsheet, "ResultsFactsheet")
            if not self._handle_validation_errors(result, "ResultsFactsheet", errors):
                return False
        
        # Validate Claims
        if result.claims:
            for i, claim in enumerate(result.claims):
                is_valid, errors = GlobalValidator.validate_artifact(claim, f"Claim[{i}]")
                if not self._handle_validation_errors(result, f"Claim[{i}]", errors):
                    return False
        
        # Run comprehensive validation if all individual validations pass
        if result.method_card and result.results_factsheet and result.claims:
            try:
                violations = GlobalValidator.validate_comprehensive_system(
                    result.results_factsheet, result.claims, result.method_card, result.evidence_spans
                )
                if violations:
                    # Check if any violations are critical (start with "CRITICAL:")
                    critical_violations = [v for v in violations if v.startswith("CRITICAL:")]
                    if critical_violations and self.strict_validation:
                        result.errors.extend([f"Comprehensive validation: {v}" for v in critical_violations])
                        return False
                    else:
                        result.warnings.extend([f"Comprehensive validation: {v}" for v in violations])
            except Exception as e:
                if self.strict_validation:
                    result.errors.append(f"Comprehensive validation failed: {str(e)}")
                    return False
                else:
                    result.warnings.append(f"Comprehensive validation failed: {str(e)}")
        
        return True
    
    def _execute_retrieval(self, trial_context: Dict[str, Any]) -> Any:
        """Execute document retrieval stage."""
        inputs = {
            "trial_context": trial_context,
            "date_window": trial_context.get("date_window", "2020-2024")
        }
        return self.retriever.execute(inputs)
    
    def _execute_method_auditing(self, trial_context: Dict[str, Any], 
                                evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute method auditing stage."""
        # Filter spans for methods/protocol/SAP
        method_spans = [span for span in evidence_spans if span.section.lower() in ["methods", "protocol", "sap"]]
        
        inputs = {
            "design_json": trial_context.get("design", {}),
            "method_spans": method_spans,
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.method_auditor.execute(inputs)
    
    def _execute_results_distillation(self, evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute results distillation stage."""
        # Filter spans for results/abstract/tables
        results_spans = [span for span in evidence_spans if span.section.lower() in ["results", "abstract", "table"]]
        
        inputs = {
            "results_spans": results_spans
        }
        return self.results_distiller.execute(inputs)
    
    def _execute_results_normalization(self, results_factsheet: ResultsFactsheet) -> Any:
        """Execute results normalization stage."""
        from ncfd.extract.normalization import get_metric_registry
        
        if not results_factsheet or not results_factsheet.rows:
            # No results to normalize
            return type('obj', (object,), {
                'success': True,
                'output': results_factsheet,
                'error_message': None
            })()
        
        metric_registry = get_metric_registry()
        normalized_rows = []
        normalization_errors = []
        
        # Normalize each row
        for i, row in enumerate(results_factsheet.rows):
            try:
                # Convert row to dict for normalization
                row_dict = {
                    "metric": row.metric,
                    "value": row.value,
                    "unit": row.unit,
                    "n": row.n,
                    "span_ids": row.span_ids,
                    "confidence": getattr(row, 'confidence', 0.8),
                    "method": getattr(row, 'method', None),
                    "range_min": getattr(row, 'range_min', None),
                    "range_max": getattr(row, 'range_max', None),
                    "breakdown": getattr(row, 'breakdown', None),
                    "pending_denominator": getattr(row, 'pending_denominator', None)
                }
                
                # Normalize the row
                success, errors = metric_registry.normalize_metric_row(row_dict)
                
                if not success:
                    # Treat normalization failures as hard errors
                    error_msg = f"Row {i+1} normalization failed: {'; '.join(errors)}"
                    normalization_errors.append(error_msg)
                    logger.error(error_msg)
                    continue
                
                # Update the row with normalized values
                if "value_normalized" in row_dict:
                    row.value_normalized = row_dict["value_normalized"]
                    row.unit_normalized = row_dict["unit_normalized"]
                    row.normalization_factor = row_dict.get("normalization_factor")
                
                normalized_rows.append(row)
                
            except Exception as e:
                error_msg = f"Row {i+1} normalization error: {str(e)}"
                normalization_errors.append(error_msg)
                logger.error(error_msg)
                continue
        
        # Check if we have any normalization errors
        if normalization_errors:
            return type('obj', (object,), {
                'success': False,
                'output': None,
                'error_message': f"Normalization failed for {len(normalization_errors)} rows: {'; '.join(normalization_errors)}"
            })()
        
        # Update the factsheet with normalized rows
        results_factsheet.rows = normalized_rows
        
        return type('obj', (object,), {
            'success': True,
            'output': results_factsheet,
            'error_message': None
        })()
    
    def _execute_claim_generation(self, evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute claim generation stage."""
        # This would be implemented by a ClaimGenerator worker
        # For now, return empty claims
        return type('obj', (object,), {
            'success': True,
            'output': [],
            'error_message': None
        })()
    
    def _execute_gate_proposal(self, method_card: MethodCard, 
                              results_factsheet: ResultsFactsheet,
                              claims: List[Claim], 
                              trial_context: Dict[str, Any]) -> Any:
        """Execute gate proposal stage."""
        inputs = {
            "method_card": method_card,
            "results_factsheet": results_factsheet,
            "claims": claims,
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.gate_proposer.execute(inputs)
    
    def _execute_gate_validation(self, gate_candidates: List[GateCandidate], 
                                claims: List[Claim]) -> Any:
        """Execute gate validation stage."""
        inputs = {
            "gate_candidates": gate_candidates,
            "claims": claims
        }
        return self.gate_validator.execute(inputs)
    
    def _execute_gate_assessment(self, gate_specs: List[GateSpec], 
                                claims: List[Claim]) -> Any:
        """Execute gate assessment stage."""
        inputs = {
            "gate_specs": gate_specs,
            "claims": claims
        }
        return self.gate_assessor.execute(inputs)
    
    def _create_decision_record(self, trial_id: str, 
                               gate_assessments: List[GateAssessment],
                               claims: List[Claim]) -> DecisionRecord:
        """Create the final decision record."""
        decision_record = DecisionRecord(trial_id=trial_id)
        
        # Add gate assessments
        for assessment in gate_assessments:
            decision_record.add_gate_assessment(
                gate_id=assessment.gate_id,
                status=assessment.status,
                p_gate=assessment.p_gate,
                rationale="; ".join(assessment.rationale)
            )
        
        # Calculate overall success probability
        overall_success = decision_record.calculate_overall_success()
        if overall_success is not None:
            decision_record.set_posterior_success(overall_success)
        
        # Determine decision
        if all(assessment.is_pass for assessment in gate_assessments):
            decision_record.set_decision("APPROVE", "All gates passed")
        elif any(assessment.is_fail for assessment in gate_assessments):
            decision_record.set_decision("REJECT", "One or more gates failed")
        else:
            decision_record.set_decision("UNCERTAIN", "Insufficient information to determine")
        
        return decision_record
    
    def _execute_fda_lens(self, method_card: MethodCard,
                          gate_assessments: List[GateAssessment],
                          decision_record: DecisionRecord) -> Any:
        """Execute FDA lens analysis stage."""
        inputs = {
            "method_card": method_card,
            "gate_assessments": gate_assessments,
            "coverage_gaps": decision_record.coverage_gaps
        }
        return self.fda_lens.execute(inputs)
    
    def _execute_memo_composition(self, gate_assessments: List[GateAssessment],
                                 decision_record: DecisionRecord,
                                 trial_context: Dict[str, Any]) -> Any:
        """Execute memo composition stage."""
        inputs = {
            "gate_assessments": gate_assessments,
            "decision_record": decision_record,
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.memo_composer.execute(inputs)
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "retriever": self.retriever.get_stats(),
            "llm_method_auditor": self.llm_method_auditor.get_stats(),
            "deterministic_method_auditor": self.deterministic_method_auditor.get_stats(),
            "llm_results_distiller": self.llm_results_distiller.get_stats(),
            "deterministic_results_distiller": self.deterministic_results_distiller.get_stats(),
            "late_fusion_orchestrator": self.late_fusion_orchestrator.get_pipeline_status(),
            "gate_proposer": self.gate_proposer.get_stats(),
            "gate_validator": self.gate_validator.get_stats(),
            "gate_assessor": self.gate_assessor.get_stats(),
            "fda_lens": self.fda_lens.get_stats(),
            "memo_composer": self.memo_composer.get_stats()
        }
    
    def _execute_llm_method_auditing(self, trial_context: Dict[str, Any], 
                                    evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute LLM method auditing stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "design_json": trial_context.get("design_json", {}),
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.llm_method_auditor.execute(inputs)
    
    def _execute_deterministic_method_auditing(self, trial_context: Dict[str, Any], 
                                             evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute deterministic method auditing stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "design_json": trial_context.get("design_json", {}),
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.deterministic_method_auditor.execute(inputs)
    
    def _execute_llm_results_distillation(self, evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute LLM results distillation stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "trial_context": {}
        }
        return self.llm_results_distiller.execute(inputs)
    
    def _execute_deterministic_results_distillation(self, evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute deterministic results distillation stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "trial_context": {}
        }
        return self.deterministic_results_distiller.execute(inputs)
    
    def _execute_late_fusion(self, llm_method_card: Optional[MethodCard],
                           llm_results_factsheet: Optional[ResultsFactsheet],
                           deterministic_method_card: Optional[MethodCard],
                           deterministic_results_factsheet: Optional[ResultsFactsheet],
                           evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute late fusion stage."""
        inputs = {
            "llm_method_card": llm_method_card,
            "llm_results_factsheet": llm_results_factsheet,
            "deterministic_method_card": deterministic_method_card,
            "deterministic_results_factsheet": deterministic_results_factsheet,
            "evidence_spans": evidence_spans
        }
        return self.late_fusion_orchestrator.fuse(inputs)
