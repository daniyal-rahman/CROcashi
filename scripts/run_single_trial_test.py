#!/usr/bin/env python3
"""
Single Trial Test Runner

A comprehensive script to run the complete single-trial test flow:
1. Inject the Cassava trial
2. Start workers (optional)
3. Monitor progress
4. Verify results

This implements the test topology you outlined for isolating a single trial
while keeping all real downstream processing intact.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

from ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator
from ncfd.ingest.pubmed.queue_service import TaskQueueService


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/single_trial_test_runner.log')
        ]
    )


def load_config(config_path: str) -> Dict[str, Any]:
    """Load test configuration."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def inject_cassava_trial(orchestrator: UnifiedPipelineOrchestrator, config: Dict[str, Any]) -> int:
    """Inject the Cassava trial using the orchestrator's injection method."""
    seed_trials = config.get('ctgov', {}).get('seed_trials', [])
    
    if not seed_trials:
        raise ValueError("No seed trials configured")
    
    # Use the first (and typically only) seed trial
    trial_config = seed_trials[0]
    
    print(f"🧪 Injecting trial: {trial_config['nct_id']}")
    
    trial_id = orchestrator.inject_ctgov_trial_for_test(
        nct_id=trial_config['nct_id'],
        company_name=trial_config['company_name'],
        asset_aliases=trial_config['asset_aliases'],
        indication_terms=trial_config['indication_terms'],
        extra_trial_fields=trial_config.get('extra_trial_fields', {})
    )
    
    print(f"✅ Trial injected successfully with ID: {trial_id}")
    return trial_id


def check_task_progress(queue_service: TaskQueueService, trial_id: int) -> Dict[str, Any]:
    """Check the progress of tasks for the trial."""
    from ncfd.db.session import session_scope
    from sqlalchemy import text
    
    with session_scope() as session:
        # Get task status summary
        task_query = text("""
            SELECT task_type, status, COUNT(*) as count
            FROM tasks 
            WHERE trial_id = :trial_id
            GROUP BY task_type, status
            ORDER BY task_type, status
        """)
        
        task_results = session.execute(task_query, {'trial_id': trial_id}).fetchall()
        
        # Get document processing summary
        doc_query = text("""
            SELECT 
                COUNT(DISTINCT d.pmid) as total_documents,
                COUNT(DISTINCT CASE WHEN dt.abstract_text IS NOT NULL THEN d.pmid END) as abstracts_processed,
                COUNT(DISTINCT CASE WHEN dt.fulltext_text IS NOT NULL THEN d.pmid END) as fulltext_processed,
                COUNT(DISTINCT rs.doc_id) as rs_scores_generated
            FROM trial_doc_candidates c
            LEFT JOIN documents d ON d.doc_id = c.doc_id
            LEFT JOIN document_text dt ON dt.doc_id = d.doc_id
            LEFT JOIN doc_rs_scores rs ON rs.trial_id = c.trial_id AND rs.doc_id = d.doc_id
            WHERE c.trial_id = :trial_id
        """)
        
        doc_results = session.execute(doc_query, {'trial_id': trial_id}).fetchone()
        
        return {
            'tasks': [dict(row._mapping) for row in task_results],
            'documents': dict(doc_results._mapping) if doc_results else {}
        }


def wait_for_completion(queue_service: TaskQueueService, trial_id: int, 
                       timeout_seconds: int = 1800) -> bool:
    """Wait for all tasks to complete, with progress monitoring."""
    start_time = time.time()
    last_status = None
    
    print(f"⏳ Monitoring task progress (timeout: {timeout_seconds}s)...")
    
    while time.time() - start_time < timeout_seconds:
        progress = check_task_progress(queue_service, trial_id)
        
        # Check if all tasks are complete
        active_tasks = [
            task for task in progress['tasks'] 
            if task['status'] in ['queued', 'leased']
        ]
        
        if not active_tasks:
            print("✅ All tasks completed!")
            return True
        
        # Print progress if it changed
        current_status = str(progress)
        if current_status != last_status:
            print(f"📊 Progress: {progress['tasks']}")
            if progress['documents']:
                docs = progress['documents']
                print(f"📄 Documents: {docs.get('total_documents', 0)} total, "
                     f"{docs.get('abstracts_processed', 0)} abstracts, "
                     f"{docs.get('fulltext_processed', 0)} fulltext, "
                     f"{docs.get('rs_scores_generated', 0)} scored")
            last_status = current_status
        
        time.sleep(10)  # Check every 10 seconds
    
    print(f"⚠️ Timeout reached after {timeout_seconds} seconds")
    return False


async def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description='Single Trial Test Runner')
    parser.add_argument('--config', default='config/single_trial_test.yaml',
                       help='Path to test configuration file')
    parser.add_argument('--inject-only', action='store_true',
                       help='Only inject the trial, don\'t wait for completion')
    parser.add_argument('--verify-only', action='store_true',
                       help='Only verify existing test results')
    parser.add_argument('--timeout', type=int, default=1800,
                       help='Timeout in seconds for task completion')
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Validate environment
    required_env_vars = ['DATABASE_URL']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)
    
    try:
        # Load configuration
        config = load_config(args.config)
        logger.info(f"Loaded configuration from {args.config}")
        
        # Initialize orchestrator
        orchestrator = UnifiedPipelineOrchestrator(config)
        queue_service = TaskQueueService(worker_id="test_runner")
        
        if args.verify_only:
            # Just run verification
            print("🔍 Running verification only...")
            os.system("python scripts/verify_single_trial_test.py")
            return
        
        print("🚀 Starting Single Trial Test")
        print("=" * 50)
        
        # Step 1: Inject the trial
        trial_id = inject_cassava_trial(orchestrator, config)
        
        if args.inject_only:
            print("✅ Trial injection complete. Start workers manually to continue.")
            print("\nTo start workers:")
            print("python workers/pubmed_u1_worker.py --env test")
            print("python workers/pubmed_oa_worker.py --env test")
            print("python workers/studycard_worker.py --env test")
            print("\nTo monitor progress:")
            print(f"python scripts/verify_single_trial_test.py --nct-id {config['ctgov']['seed_trials'][0]['nct_id']}")
            return
        
        # Step 2: Wait for workers to process (if they're running)
        print(f"\n⚙️ Waiting for workers to process trial {trial_id}...")
        print("Make sure you have started the workers:")
        print("  python workers/pubmed_u1_worker.py --env test")
        print("  python workers/pubmed_oa_worker.py --env test")
        print("  python workers/studycard_worker.py --env test")
        
        # Monitor progress
        completed = wait_for_completion(queue_service, trial_id, args.timeout)
        
        if completed:
            print("\n🎉 Single trial test completed successfully!")
        else:
            print("\n⚠️ Test did not complete within timeout")
        
        # Step 3: Run verification
        print("\n🔍 Running final verification...")
        nct_id = config['ctgov']['seed_trials'][0]['nct_id']
        os.system(f"python scripts/verify_single_trial_test.py --nct-id {nct_id}")
        
        print("\n📋 Test Summary:")
        print(f"Trial ID: {trial_id}")
        print(f"NCT ID: {nct_id}")
        print(f"Status: {'✅ COMPLETED' if completed else '⚠️ TIMEOUT'}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    asyncio.run(main())
