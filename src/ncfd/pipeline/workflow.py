"""
Complete workflow for trial failure detection system.

This module orchestrates the entire pipeline including document ingestion,
study card processing, change tracking, signal evaluation, gate analysis,
and scoring to provide end-to-end trial failure detection.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import uuid

from ..db.models import Trial, TrialVersion, Study, Signal, Gate, Score
from ..db.session import get_session
from ..signals import evaluate_all_signals, get_fired_signals
from ..signals.gates import evaluate_gates, SignalEvidence
from ..scoring import AdvancedScoringEngine
from .ingestion import DocumentIngestionPipeline, ingest_document, batch_ingest_documents
from .tracking import TrialVersionTracker, track_trial_changes, detect_material_changes
from .processing import StudyCardProcessor, process_study_card, extract_trial_metadata


@dataclass
class WorkflowResult:
    """Result of a complete workflow execution."""
    success: bool
    trial_id: Optional[str] = None
    run_id: Optional[str] = None
    ingestion_result: Optional[Any] = None
    processing_result: Optional[Any] = None
    tracking_result: Optional[Any] = None
    signal_results: Optional[Dict[str, Any]] = None
    gate_results: Optional[Dict[str, Any]] = None
    scoring_result: Optional[Any] = None
    total_processing_time: float = 0.0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BatchWorkflowResult:
    """Result of batch workflow execution."""
    total_trials: int
    successful_trials: int
    failed_trials: int
    individual_results: List[WorkflowResult]
    summary_statistics: Dict[str, Any]
    processing_time: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class FailureReport:
    """Comprehensive failure detection report."""
    report_id: str
    generated_at: datetime
    trial_id: str
    risk_assessment: str  # "H", "M", "L"
    signals_fired: List[str]
    gates_fired: List[str]
    failure_probability: float
    key_risk_factors: List[str]
    recommendations: List[str]
    change_history: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class FailureDetectionWorkflow:
    """Complete end-to-end trial failure detection workflow."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the failure detection workflow.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.ingestion_pipeline = DocumentIngestionPipeline(
            config=self.config.get("ingestion", {})
        )
        self.tracking_system = TrialVersionTracker(
            config=self.config.get("tracking", {})
        )
        self.processing_system = StudyCardProcessor(
            config=self.config.get("processing", {})
        )
        self.scoring_engine = AdvancedScoringEngine(
            config=self.config.get("scoring", {})
        )
        
        # Workflow configuration
        self.auto_track_changes = self.config.get("auto_track_changes", True)
        self.auto_evaluate_signals = self.config.get("auto_evaluate_signals", True)
        self.auto_evaluate_gates = self.config.get("auto_evaluate_gates", True)
        self.auto_score_trials = self.config.get("auto_score_trials", True)
        self.generate_reports = self.config.get("generate_reports", True)
        
    def run_failure_detection(self, 
                             document_path: Union[str, Path],
                             trial_metadata: Optional[Dict[str, Any]] = None,
                             run_id: Optional[str] = None) -> WorkflowResult:
        """
        Run complete failure detection workflow for a single document.
        
        Args:
            document_path: Path to the document file
            trial_metadata: Additional trial metadata
            run_id: Run identifier for tracking
            
        Returns:
            WorkflowResult with complete analysis
        """
        start_time = datetime.now()
        
        if not run_id:
            run_id = f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        try:
            self.logger.info(f"Starting failure detection workflow for {document_path}")
            
            # Step 1: Document Ingestion
            self.logger.info("Step 1: Document Ingestion")
            ingestion_result = self.ingestion_pipeline.ingest_document(
                document_path, trial_metadata, run_id
            )
            
            if not ingestion_result.success:
                return WorkflowResult(
                    success=False,
                    run_id=run_id,
                    error_message=f"Ingestion failed: {ingestion_result.error_message}",
                    total_processing_time=(datetime.now() - start_time).total_seconds()
                )
            
            trial_id = ingestion_result.trial_id
            study_card = ingestion_result.study_card
            
            # Step 2: Study Card Processing
            self.logger.info("Step 2: Study Card Processing")
            processing_result = self.processing_system.process_study_card(
                study_card, trial_metadata, run_id
            )
            
            if not processing_result.success:
                return WorkflowResult(
                    success=False,
                    trial_id=trial_id,
                    run_id=run_id,
                    error_message=f"Processing failed: {processing_result.error_message}",
                    total_processing_time=(datetime.now() - start_time).total_seconds()
                )
            
            processed_study_card = processing_result.processed_study_card
            
            # Step 3: Change Tracking (if enabled)
            tracking_result = None
            if self.auto_track_changes:
                self.logger.info("Step 3: Change Tracking")
                try:
                    tracking_result = self.tracking_system.track_trial_changes(
                        trial_id, processed_study_card, run_id
                    )
                    self.logger.info(f"Change tracking completed: {tracking_result.material_changes} material changes")
                except Exception as e:
                    self.logger.warning(f"Change tracking failed: {e}")
            
            # Step 4: Signal Evaluation (if enabled)
            signal_results = None
            if self.auto_evaluate_signals:
                self.logger.info("Step 4: Signal Evaluation")
                try:
                    signal_results = evaluate_all_signals(processed_study_card)
                    fired_signals = get_fired_signals(signal_results)
                    self.logger.info(f"Signal evaluation completed: {len(fired_signals)} signals fired")
                    
                    # Store signals in database
                    self._store_signals(trial_id, signal_results, run_id)
                    
                except Exception as e:
                    self.logger.error(f"Signal evaluation failed: {e}")
                    signal_results = {}
            
            # Step 5: Gate Evaluation (if enabled)
            gate_results = {}
            if self.auto_evaluate_gates:
                self.logger.info("Step 5: Gate Evaluation")
                try:
                    # Convert signal results to new format for gate evaluation
                    present_signals = set()
                    evidence_by_signal = {}
                    
                    for signal_id, signal_result in signal_results.items():
                        if signal_result and signal_result.fired:
                            present_signals.add(signal_id)
                            # Create evidence spans from signal results
                            evidence = SignalEvidence(
                                S_id=signal_id,
                                evidence_span={
                                    "source_study_id": getattr(signal_result, 'source_study_id', None),
                                    "quote": getattr(signal_result, 'reason', ''),
                                    "severity": getattr(signal_result, 'severity', 'medium')
                                },
                                severity=getattr(signal_result, 'severity', 'medium')
                            )
                            evidence_by_signal[signal_id] = [evidence]
                    
                    # Evaluate gates using new system
                    gate_results = evaluate_gates(present_signals, evidence_by_signal)
                    fired_gates = [g_id for g_id, g in gate_results.items() if g.fired]
                    self.logger.info(f"Gate evaluation completed: {len(fired_gates)} gates fired")
                    
                    # Store gates in database
                    self._store_gates(trial_id, gate_results, run_id)
                    
                except Exception as e:
                    self.logger.error(f"Gate evaluation failed: {e}")
                    gate_results = {}
            
            # Step 6: Trial Scoring (if enabled)
            scoring_result = None
            if self.auto_score_trials:
                self.logger.info("Step 6: Trial Scoring")
                try:
                    # Get trial metadata for scoring
                    trial_metadata_for_scoring = processing_result.extracted_metadata
                    
                    # Use new advanced scoring system
                    scoring_result = self.scoring_engine.score_trial(
                        trial_id=trial_id,
                        run_id=run_id,
                        trial_data=trial_metadata_for_scoring,
                        gate_evals=gate_results,
                        present_signals=present_signals,
                        evidence_by_signal=evidence_by_signal
                    )
                    
                    self.logger.info(f"Trial scoring completed: {scoring_result.p_fail:.3f} failure probability")
                    
                    # Store score in database
                    self._store_score(trial_id, scoring_result, run_id)
                    
                except Exception as e:
                    self.logger.error(f"Trial scoring failed: {e}")
            
            # Step 7: Generate Failure Report (if enabled)
            failure_report = None
            if self.generate_reports and scoring_result:
                self.logger.info("Step 7: Generating Failure Report")
                try:
                    failure_report = self._generate_failure_report(
                        trial_id, signal_results, gate_results, scoring_result, tracking_result
                    )
                    self.logger.info(f"Failure report generated: {failure_report.risk_assessment} risk")
                except Exception as e:
                    self.logger.warning(f"Failure report generation failed: {e}")
            
            total_processing_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.info(f"Failure detection workflow completed successfully for trial {trial_id}")
            
            return WorkflowResult(
                success=True,
                trial_id=trial_id,
                run_id=run_id,
                ingestion_result=ingestion_result,
                processing_result=processing_result,
                tracking_result=tracking_result,
                signal_results=signal_results,
                gate_results=gate_results,
                scoring_result=scoring_result,
                total_processing_time=total_processing_time,
                metadata={
                    "failure_report": failure_report,
                    "workflow_config": {
                        "auto_track_changes": self.auto_track_changes,
                        "auto_evaluate_signals": self.auto_evaluate_signals,
                        "auto_evaluate_gates": self.auto_evaluate_gates,
                        "auto_score_trials": self.auto_score_trials,
                        "generate_reports": self.generate_reports
                    }
                }
            )
            
        except Exception as e:
            total_processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Failure detection workflow failed: {e}")
            
            return WorkflowResult(
                success=False,
                run_id=run_id,
                error_message=str(e),
                total_processing_time=total_processing_time
            )
    
    def batch_process_trials(self, 
                            document_paths: List[Union[str, Path]],
                            trial_metadata_list: Optional[List[Dict[str, Any]]] = None,
                            run_id: Optional[str] = None) -> BatchWorkflowResult:
        """
        Run failure detection workflow for multiple documents.
        
        Args:
            document_paths: List of document paths
            trial_metadata_list: List of trial metadata (optional)
            run_id: Run identifier for tracking
            
        Returns:
            BatchWorkflowResult with batch analysis
        """
        start_time = datetime.now()
        
        if not run_id:
            run_id = f"batch_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        self.logger.info(f"Starting batch failure detection for {len(document_paths)} documents")
        
        individual_results = []
        
        for i, doc_path in enumerate(document_paths):
            trial_metadata = trial_metadata_list[i] if trial_metadata_list else None
            
            self.logger.info(f"Processing document {i+1}/{len(document_paths)}: {doc_path}")
            
            result = self.run_failure_detection(doc_path, trial_metadata, run_id)
            individual_results.append(result)
            
            # Log progress
            if result.success:
                self.logger.info(f"✅ Document {i+1} processed successfully")
            else:
                self.logger.warning(f"❌ Document {i+1} failed: {result.error_message}")
        
        # Calculate summary statistics
        total_trials = len(individual_results)
        successful_trials = sum(1 for r in individual_results if r.success)
        failed_trials = total_trials - successful_trials
        
        # Aggregate statistics
        summary_statistics = self._calculate_batch_statistics(individual_results)
        
        total_processing_time = (datetime.now() - start_time).total_seconds()
        
        self.logger.info(f"Batch failure detection completed: {successful_trials}/{total_trials} successful")
        
        return BatchWorkflowResult(
            total_trials=total_trials,
            successful_trials=successful_trials,
            failed_trials=failed_trials,
            individual_results=individual_results,
            summary_statistics=summary_statistics,
            processing_time=total_processing_time,
            metadata={
                "run_id": run_id,
                "batch_size": total_trials,
                "success_rate": successful_trials / total_trials if total_trials > 0 else 0
            }
        )
    
    def generate_failure_report(self, 
                               trial_id: str,
                               signal_results: Optional[Dict[str, Any]] = None,
                               gate_results: Optional[Dict[str, Any]] = None,
                               scoring_result: Optional[Any] = None,
                               tracking_result: Optional[Any] = None) -> FailureReport:
        """
        Generate comprehensive failure detection report.
        
        Args:
            trial_id: Trial identifier
            signal_results: Signal evaluation results
            gate_results: Gate evaluation results
            scoring_result: Scoring results
            tracking_result: Change tracking results
            
        Returns:
            FailureReport with comprehensive analysis
        """
        # Determine risk assessment
        risk_assessment = "L"  # Default low risk
        
        if scoring_result and hasattr(scoring_result, 'p_fail'):
            if scoring_result.p_fail > 0.7:
                risk_assessment = "H"
            elif scoring_result.p_fail > 0.4:
                risk_assessment = "M"
        
        # Get fired signals and gates
        signals_fired = []
        if signal_results:
            signals_fired = [s_id for s_id, s in signal_results.items() if s.fired]
        
        gates_fired = []
        if gate_results:
            gates_fired = [g_id for g_id, g in gate_results.items() if g.fired]
        
        # Identify key risk factors
        key_risk_factors = []
        
        # High-risk signals
        high_risk_signals = ["S1", "S2", "S8"]  # Endpoint change, underpowered, p-value cusp
        if any(s in signals_fired for s in high_risk_signals):
            key_risk_factors.append("High-risk signals detected")
        
        # Multiple gates fired
        if len(gates_fired) >= 2:
            key_risk_factors.append("Multiple failure gates triggered")
        
        # Material changes
        if tracking_result and tracking_result.material_changes:
            key_risk_factors.append("Material protocol changes detected")
        
        # High failure probability
        if scoring_result and hasattr(scoring_result, 'p_fail') and scoring_result.p_fail > 0.6:
            key_risk_factors.append("High calculated failure probability")
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            risk_assessment, signals_fired, gates_fired, key_risk_factors
        )
        
        # Prepare change history
        change_history = None
        if tracking_result:
            change_history = {
                "has_changes": tracking_result.has_changes,
                "material_changes": tracking_result.material_changes,
                "change_score": tracking_result.change_score,
                "change_summary": tracking_result.change_summary
            }
        
        return FailureReport(
            report_id=f"report_{trial_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            generated_at=datetime.now(),
            trial_id=trial_id,
            risk_assessment=risk_assessment,
            signals_fired=signals_fired,
            gates_fired=gates_fired,
            failure_probability=scoring_result.p_fail if scoring_result else 0.0,
            key_risk_factors=key_risk_factors,
            recommendations=recommendations,
            change_history=change_history,
            metadata={
                "report_version": "1.0",
                "analysis_timestamp": datetime.now().isoformat()
            }
        )
    
    def _store_signals(self, trial_id: str, signal_results: Dict[str, Any], run_id: str) -> None:
        """Store signal results in database."""
        try:
            with get_session() as session:
                for signal_id, signal_result in signal_results.items():
                    if signal_result.fired:
                        signal = Signal(
                            trial_id=trial_id,
                            S_id=signal_id,
                            value=signal_result.value,
                            severity=signal_result.severity,
                            evidence_span=signal_result.evidence_span,
                            source_study_id=trial_id,
                            fired_at=datetime.now(),
                            metadata={
                                "run_id": run_id,
                                "reason": signal_result.reason,
                                "workflow_generated": True
                            }
                        )
                        session.add(signal)
                
                session.commit()
                self.logger.info(f"Stored {len([s for s in signal_results.values() if s.fired])} signals for trial {trial_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to store signals for trial {trial_id}: {e}")
    
    def _store_gates(self, trial_id: str, gate_results: Dict[str, Any], run_id: str) -> None:
        """Store gate results in database."""
        try:
            with get_session() as session:
                for gate_id, gate_result in gate_results.items():
                    if gate_result.fired:
                        gate = Gate(
                            trial_id=trial_id,
                            G_id=gate_id,
                            fired_bool=True,
                            supporting_S_ids=gate_result.supporting_S,
                            lr_used=gate_result.lr_used,
                            rationale_text=gate_result.rationale,
                            evaluated_at=datetime.now(),
                            metadata={
                                "run_id": run_id,
                                "workflow_generated": True,
                                "evidence_count": len(gate_result.supporting_evidence)
                            }
                        )
                        session.add(gate)
                
                session.commit()
                self.logger.info(f"Stored {len([g for g in gate_results.values() if g.fired])} gates for trial {trial_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to store gates for trial {trial_id}: {e}")
    
    def _store_score(self, trial_id: str, scoring_result: Any, run_id: str) -> None:
        """Store scoring result in database."""
        try:
            with get_session() as session:
                # Create audit trail
                audit_trail = None
                if hasattr(self.scoring_engine, 'create_audit_trail'):
                    try:
                        # Get evidence from gate results if available
                        evidence_by_signal = {}
                        if hasattr(scoring_result, 'gate_evals') and scoring_result.gate_evals:
                            for gate_eval in scoring_result.gate_evals.values():
                                if gate_eval.supporting_evidence:
                                    for evidence in gate_eval.supporting_evidence:
                                        if evidence.S_id not in evidence_by_signal:
                                            evidence_by_signal[evidence.S_id] = []
                                        evidence_by_signal[evidence.S_id].append(evidence)
                        
                        audit_trail = self.scoring_engine.create_audit_trail(
                            scoring_result, 
                            "gate_lrs.yaml@2025-08-21", 
                            evidence_by_signal
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to create audit trail: {e}")
                
                score = Score(
                    trial_id=trial_id,
                    run_id=run_id,
                    prior_pi=scoring_result.prior_pi,
                    logit_prior=scoring_result.logit_prior,
                    sum_log_lr=scoring_result.sum_log_lr,
                    logit_post=scoring_result.logit_post,
                    p_fail=scoring_result.p_fail,
                    features_frozen_at=scoring_result.features_frozen_at,
                    scored_at=datetime.now(),
                    metadata={
                        "workflow_generated": True,
                        "scoring_engine_version": "2.0",
                        "audit_trail": audit_trail,
                        "stop_rules_applied": len(scoring_result.stop_rules_applied) if hasattr(scoring_result, 'stop_rules_applied') else 0
                    }
                )
                session.add(score)
                session.commit()
                
                self.logger.info(f"Stored score for trial {trial_id}: {scoring_result.p_fail:.3f}")
                if audit_trail:
                    self.logger.info(f"Audit trail created with {len(audit_trail.get('gates', []))} gates")
                
        except Exception as e:
            self.logger.error(f"Failed to store score for trial {trial_id}: {e}")
    
    def _calculate_batch_statistics(self, individual_results: List[WorkflowResult]) -> Dict[str, Any]:
        """Calculate summary statistics for batch processing."""
        successful_results = [r for r in individual_results if r.success]
        
        if not successful_results:
            return {
                "total_processing_time": 0.0,
                "avg_processing_time": 0.0,
                "signals_fired_total": 0,
                "gates_fired_total": 0,
                "avg_failure_probability": 0.0,
                "risk_distribution": {"H": 0, "M": 0, "L": 0}
            }
        
        # Processing time statistics
        processing_times = [r.total_processing_time for r in successful_results]
        total_processing_time = sum(processing_times)
        avg_processing_time = total_processing_time / len(processing_times)
        
        # Signal and gate statistics
        signals_fired_total = sum(
            len([s for s in r.signal_results.items() if s[1].fired]) 
            for r in successful_results if r.signal_results
        )
        gates_fired_total = sum(
            len([g for g in r.gate_results.items() if g[1].fired]) 
            for r in successful_results if r.gate_results
        )
        
        # Failure probability statistics
        failure_probabilities = [
            r.scoring_result.p_fail 
            for r in successful_results 
            if r.scoring_result and hasattr(r.scoring_result, 'p_fail')
        ]
        avg_failure_probability = sum(failure_probabilities) / len(failure_probabilities) if failure_probabilities else 0.0
        
        # Risk distribution
        risk_distribution = {"H": 0, "M": 0, "L": 0}
        for prob in failure_probabilities:
            if prob > 0.7:
                risk_distribution["H"] += 1
            elif prob > 0.4:
                risk_distribution["M"] += 1
            else:
                risk_distribution["L"] += 1
        
        return {
            "total_processing_time": total_processing_time,
            "avg_processing_time": avg_processing_time,
            "signals_fired_total": signals_fired_total,
            "gates_fired_total": gates_fired_total,
            "avg_failure_probability": avg_failure_probability,
            "risk_distribution": risk_distribution,
            "successful_trials": len(successful_results)
        }
    
    def _generate_recommendations(self, 
                                 risk_assessment: str,
                                 signals_fired: List[str],
                                 gates_fired: List[str],
                                 key_risk_factors: List[str]) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # High-risk recommendations
        if risk_assessment == "H":
            recommendations.append("Immediate regulatory review recommended")
            recommendations.append("Consider trial suspension pending investigation")
            recommendations.append("Implement enhanced monitoring protocols")
        
        # Signal-specific recommendations
        if "S1" in signals_fired:
            recommendations.append("Review endpoint change justification and impact")
            recommendations.append("Assess statistical power implications")
        
        if "S2" in signals_fired:
            recommendations.append("Conduct power analysis and consider sample size increase")
            recommendations.append("Review effect size assumptions")
        
        if "S8" in signals_fired:
            recommendations.append("Investigate p-value proximity to significance threshold")
            recommendations.append("Review analysis plan and multiplicity adjustments")
        
        # Gate-specific recommendations
        if "G1" in gates_fired:
            recommendations.append("Critical: Endpoint change combined with power issues")
            recommendations.append("Requires immediate sponsor consultation")
        
        if "G2" in gates_fired:
            recommendations.append("Analysis gaming pattern detected - review methodology")
            recommendations.append("Consider independent statistical review")
        
        # General recommendations
        if len(gates_fired) >= 2:
            recommendations.append("Multiple failure gates triggered - comprehensive review needed")
        
        if len(signals_fired) >= 5:
            recommendations.append("High signal count - detailed protocol review recommended")
        
        # Risk factor recommendations
        if "Material protocol changes detected" in key_risk_factors:
            recommendations.append("Document all protocol changes and justifications")
            recommendations.append("Assess impact on trial validity")
        
        if "High calculated failure probability" in key_risk_factors:
            recommendations.append("Review trial design and assumptions")
            recommendations.append("Consider early termination criteria")
        
        # Default recommendations
        if not recommendations:
            recommendations.append("Continue monitoring with standard protocols")
            recommendations.append("Schedule regular review intervals")
        
        return recommendations


# Convenience functions
def run_failure_detection(document_path: Union[str, Path],
                         trial_metadata: Optional[Dict[str, Any]] = None,
                         run_id: Optional[str] = None) -> WorkflowResult:
    """Run complete failure detection workflow for a single document."""
    workflow = FailureDetectionWorkflow()
    return workflow.run_failure_detection(document_path, trial_metadata, run_id)


def batch_process_trials(document_paths: List[Union[str, Path]],
                        trial_metadata_list: Optional[List[Dict[str, Any]]] = None,
                        run_id: Optional[str] = None) -> BatchWorkflowResult:
    """Run failure detection workflow for multiple documents."""
    workflow = FailureDetectionWorkflow()
    return workflow.batch_process_trials(document_paths, trial_metadata_list, run_id)


def generate_failure_report(trial_id: str,
                           signal_results: Optional[Dict[str, Any]] = None,
                           gate_results: Optional[Dict[str, Any]] = None,
                           scoring_result: Optional[Any] = None,
                           tracking_result: Optional[Any] = None) -> FailureReport:
    """Generate comprehensive failure detection report."""
    workflow = FailureDetectionWorkflow()
    return workflow.generate_failure_report(
        trial_id, signal_results, gate_results, scoring_result, tracking_result
    )
