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
    GateValidator, GateAssessor, FdaLens, MemoComposer
)
from ..extract.models import (
    DocumentCard, EvidenceSpan, Claim, MethodCard, ResultsFactsheet,
    PocketContextCard, GateCandidate, GateSpec, GateAssessment, DecisionRecord
)

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
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate processing time."""
        self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()


class StudyCardPipeline:
    """Main pipeline for study card processing and evaluation."""
    
    def __init__(self):
        """Initialize the study card pipeline."""
        self.retriever = Retriever()
        self.method_auditor = MethodAuditor()
        self.results_distiller = ResultsDistiller()
        self.gate_proposer = GateProposer()
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        self.fda_lens = FdaLens()
        self.memo_composer = MemoComposer()
        
        logger.info("StudyCardPipeline initialized")
    
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
            
            # Stage 2: Method auditing
            logger.info("Stage 2: Method auditing")
            method_result = self._execute_method_auditing(trial_context, result.evidence_spans)
            if not method_result.success:
                result.errors.append(f"Method auditing failed: {method_result.error_message}")
                return result
            
            result.method_card = method_result.output
            
            # Stage 3: Results distillation
            logger.info("Stage 3: Results distillation")
            results_result = self._execute_results_distillation(result.evidence_spans)
            if not results_result.success:
                result.errors.append(f"Results distillation failed: {results_result.error_message}")
                return result
            
            result.results_factsheet = results_result.output
            
            # Stage 4: Claim generation
            logger.info("Stage 4: Claim generation")
            claims_result = self._execute_claim_generation(result.evidence_spans)
            if not claims_result.success:
                result.errors.append(f"Claim generation failed: {claims_result.error_message}")
                return result
            
            result.claims = claims_result.output
            
            # Stage 5: Gate proposal
            logger.info("Stage 5: Gate proposal")
            gates_result = self._execute_gate_proposal(
                result.method_card, result.results_factsheet, result.claims, trial_context
            )
            if not gates_result.success:
                result.errors.append(f"Gate proposal failed: {gates_result.error_message}")
                return result
            
            result.gate_candidates = gates_result.output
            
            # Stage 6: Gate validation
            logger.info("Stage 6: Gate validation")
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
            
            logger.info(f"Study card pipeline completed successfully for trial {trial_id}")
            
        except Exception as e:
            result.end_time = datetime.utcnow()
            result.errors.append(f"Pipeline execution failed: {str(e)}")
            logger.error(f"Study card pipeline failed for trial {trial_id}: {str(e)}")
        
        return result
    
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
            "method_auditor": self.method_auditor.get_stats(),
            "results_distiller": self.results_distiller.get_stats(),
            "gate_proposer": self.gate_proposer.get_stats(),
            "gate_validator": self.gate_validator.get_stats(),
            "gate_assessor": self.gate_assessor.get_stats(),
            "fda_lens": self.fda_lens.get_stats(),
            "memo_composer": self.memo_composer.get_stats()
        }
