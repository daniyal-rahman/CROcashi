#!/usr/bin/env python3
"""
Test script to isolate and fix the pipeline reporting issue.
The pipeline runs Stage B and LLM evaluation but reports "No LLM evaluations" and "No documents evaluated in Stage B".
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ncfd.pipeline.literature_orchestrator import LiteratureOrchestrator
from ncfd.db.session import get_session
from ncfd.db.models import Trial, Document, DocumentUtility, TrialEvaluation
from ncfd.ingest.literature_scoring import ScoringConfig

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PipelineReportingTester:
    def __init__(self):
        self.test_trial_nct = "NCT05111574"
        
    def run_pipeline_reporting_test(self):
        """Test the pipeline and examine where the reporting breaks down."""
        print("🔍 PIPELINE REPORTING TEST")
        print("=" * 50)
        
        results = []
        
        # Test 1: Check current database state
        results.append(self.test_current_database_state())
        
        # Test 2: Run pipeline and capture intermediate results
        results.append(self.test_pipeline_execution())
        
        # Test 3: Examine final database state
        results.append(self.test_final_database_state())
        
        # Test 4: Analyze reporting logic
        results.append(self.test_reporting_logic())
        
        return results
    
    def test_current_database_state(self):
        """Check what's currently in the database."""
        print("\n📊 Test 1: Current Database State")
        print("-" * 30)
        
        try:
            with get_session() as session:
                # Check trials
                trials = session.query(Trial).filter(Trial.nct_id == self.test_trial_nct).all()
                print(f"Trials with NCT {self.test_trial_nct}: {len(trials)}")
                
                # Check document utilities
                if trials:
                    trial_id = trials[0].id
                    utilities = session.query(DocumentUtility).filter(DocumentUtility.trial_id == trial_id).all()
                    print(f"Document utilities for trial {trial_id}: {len(utilities)}")
                    
                    # Check U0 scores
                    u0_scores = [u.u0_score for u in utilities if u.u0_score is not None]
                    print(f"U0 scores: {len(u0_scores)} non-null, range: {min(u0_scores) if u0_scores else 'N/A'} - {max(u0_scores) if u0_scores else 'N/A'}")
                    
                    # Check U1 scores
                    u1_scores = [u.u1_score for u in utilities if u.u1_score is not None]
                    print(f"U1 scores: {len(u1_scores)} non-null")
                    
                    # Check stages
                    stages = [u.stage for u in utilities if u.stage is not None]
                    print(f"Stages: {len(stages)} non-null, unique: {set(stages) if stages else 'N/A'}")
                    
                    return {"test": "Current Database State", "status": "PASS", "details": f"Found {len(utilities)} utilities"}
                else:
                    return {"test": "Current Database State", "status": "FAIL", "details": "No trials found"}
                    
        except Exception as e:
            return {"test": "Current Database State", "status": "ERROR", "details": str(e)}
    
    def test_pipeline_execution(self):
        """Run the pipeline and capture intermediate results."""
        print("\n🚀 Test 2: Pipeline Execution")
        print("-" * 30)
        
        try:
            with get_session() as session:
                # Initialize orchestrator with session
                orchestrator = LiteratureOrchestrator(db_session=session)
                
                # Run pipeline
                print("Running pipeline...")
                result = orchestrator.run_pipeline(self.test_trial_nct)
                
                print(f"Pipeline result: {result}")
                
                # Check if result has the expected structure
                if hasattr(result, 'status'):
                    print(f"Status: {result.status}")
                if hasattr(result, 'trials_processed'):
                    print(f"Trials processed: {result.trials_processed}")
                if hasattr(result, 'documents_scored'):
                    print(f"Documents scored: {result.documents_scored}")
                if hasattr(result, 'documents_evaluated'):
                    print(f"Documents evaluated: {result.documents_evaluated}")
                if hasattr(result, 'llm_evaluations'):
                    print(f"LLM evaluations: {result.llm_evaluations}")
                
                return {"test": "Pipeline Execution", "status": "PASS", "details": "Pipeline executed successfully"}
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            return {"test": "Pipeline Execution", "status": "ERROR", "details": str(e)}
    
    def test_final_database_state(self):
        """Check what changed in the database after pipeline run."""
        print("\n📊 Test 3: Final Database State")
        print("-" * 30)
        
        try:
            with get_session() as session:
                # Check trials
                trials = session.query(Trial).filter(Trial.nct_id == self.test_trial_nct).all()
                if not trials:
                    return {"test": "Final Database State", "status": "FAIL", "details": "No trials found"}
                
                trial_id = trials[0].id
                
                # Check document utilities
                utilities = session.query(DocumentUtility).filter(DocumentUtility.trial_id == trial_id).all()
                print(f"Document utilities: {len(utilities)}")
                
                # Check U0 scores
                u0_scores = [u.u0_score for u in utilities if u.u0_score is not None]
                print(f"U0 scores: {len(u0_scores)} non-null")
                
                # Check U1 scores
                u1_scores = [u.u1_score for u in utilities if u.u1_score is not None]
                print(f"U1 scores: {len(u1_scores)} non-null")
                
                # Check stages
                stages = [u.stage for u in utilities if u.stage is not None]
                print(f"Stages: {len(stages)} non-null, unique: {set(stages) if stages else 'N/A'}")
                
                # Check trial evaluations
                evaluations = session.query(TrialEvaluation).filter(TrialEvaluation.trial_id == trial_id).all()
                print(f"Trial evaluations: {len(evaluations)}")
                
                if evaluations:
                    for eval in evaluations:
                        print(f"  Evaluation {eval.id}: p_short={eval.p_short_posterior}, decision={eval.stop_decision}")
                
                return {"test": "Final Database State", "status": "PASS", "details": f"Found {len(utilities)} utilities, {len(evaluations)} evaluations"}
                
        except Exception as e:
            return {"test": "Final Database State", "status": "ERROR", "details": str(e)}
    
    def test_reporting_logic(self):
        """Analyze the reporting logic to find the bug."""
        print("\n🔍 Test 4: Reporting Logic Analysis")
        print("-" * 30)
        
        try:
            with get_session() as session:
                # Check if there's a mismatch between what's stored and what's reported
                trials = session.query(Trial).filter(Trial.nct_id == self.test_trial_nct).all()
                if not trials:
                    return {"test": "Reporting Logic Analysis", "status": "FAIL", "details": "No trials found"}
                
                trial_id = trials[0].id
                
                # Count documents by stage
                stage_0 = session.query(DocumentUtility).filter(
                    DocumentUtility.trial_id == trial_id,
                    DocumentUtility.stage == 0
                ).count()
                
                stage_1 = session.query(DocumentUtility).filter(
                    DocumentUtility.trial_id == trial_id,
                    DocumentUtility.stage == 1
                ).count()
                
                stage_2 = session.query(DocumentUtility).filter(
                    DocumentUtility.trial_id == trial_id,
                    DocumentUtility.stage == 2
                ).count()
                
                print(f"Documents by stage:")
                print(f"  Stage 0 (metadata): {stage_0}")
                print(f"  Stage 1 (abstract): {stage_1}")
                print(f"  Stage 2 (fulltext): {stage_2}")
                
                # Check if U1 scores exist
                u1_count = session.query(DocumentUtility).filter(
                    DocumentUtility.trial_id == trial_id,
                    DocumentUtility.u1_score.isnot(None)
                ).count()
                
                print(f"Documents with U1 scores: {u1_count}")
                
                # Check trial evaluations
                eval_count = session.query(TrialEvaluation).filter(
                    TrialEvaluation.trial_id == trial_id
                ).count()
                
                print(f"Trial evaluations: {eval_count}")
                
                return {"test": "Reporting Logic Analysis", "status": "PASS", "details": f"Stage breakdown: 0={stage_0}, 1={stage_1}, 2={stage_2}, U1={u1_count}, evals={eval_count}"}
                
        except Exception as e:
            return {"test": "Reporting Logic Analysis", "status": "ERROR", "details": str(e)}
    
    def print_results(self, results):
        """Print test results."""
        print("\n" + "=" * 50)
        print("📋 TEST RESULTS SUMMARY")
        print("=" * 50)
        
        passed = 0
        failed = 0
        errors = 0
        
        for result in results:
            status = result["status"]
            if status == "PASS":
                passed += 1
                print(f"✅ {result['test']}: {result['details']}")
            elif status == "FAIL":
                failed += 1
                print(f"❌ {result['test']}: {result['details']}")
            else:
                errors += 1
                print(f"⚠️  {result['test']}: {result['details']}")
        
        print(f"\n📊 SUMMARY: {passed} passed, {failed} failed, {errors} errors")
        
        if failed == 0 and errors == 0:
            print("🎉 All tests passed!")
        else:
            print("🔧 Some tests need attention.")

if __name__ == "__main__":
    tester = PipelineReportingTester()
    results = tester.run_pipeline_reporting_test()
    tester.print_results(results)
