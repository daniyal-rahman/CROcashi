"""
U1+ stage worker for PUBMED_U1 tasks.

Handles unified discovery and abstract processing for trials.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .client import PubMedClient
from .mapper import PubMedMapper
from .db_service import PubMedDBService
from .queue_service import TaskQueueService
from .stage_u1 import StageU1Processor, StageU1Result
from .trial_query_builder import TrialQueryBuilder
from ...extract.abstract_features import AbstractFeatureExtractor
from ...score.simple_rs_scorer import SimpleRSScorer

logger = logging.getLogger(__name__)


@dataclass
class U1WorkerResult:
    """Result from U1 worker execution."""
    task_id: int
    trial_id: int
    success: bool
    documents_discovered: int = 0
    documents_processed: int = 0
    abstracts_fetched: int = 0
    documents_scored: int = 0
    documents_selected: int = 0
    oa_tasks_enqueued: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None


class U1Worker:
    """Worker for processing PUBMED_U1 tasks."""
    
    def __init__(
        self,
        client: PubMedClient,
        mapper: PubMedMapper,
        queue_service: TaskQueueService,
        config: Optional[Dict] = None
    ):
        """
        Initialize U1 worker.
        
        Args:
            client: PubMed client instance
            mapper: Response mapper instance
            queue_service: Task queue service instance
            config: Configuration dictionary
        """
        self.client = client
        self.mapper = mapper
        self.queue_service = queue_service
        self.config = config or {}
        
        # Initialize database service
        self.db_service = PubMedDBService()
        
        # Initialize components for U1+ processing
        self.feature_extractor = AbstractFeatureExtractor()
        self.rs_scorer = SimpleRSScorer()
        self.query_builder = TrialQueryBuilder()
        
        # Initialize U1+ processor
        self.u1_processor = StageU1Processor(
            client=self.client,
            mapper=self.mapper,
            feature_extractor=self.feature_extractor,
            rs_scorer=self.rs_scorer,
            query_builder=self.query_builder,
            config=self.config
        )
        
        # U1 settings
        self.batch_size = self.config.get('batch_size', 5)
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 30)
        
        self.logger = logger
    
    async def process_u1_task(self, task_data: Dict[str, Any]) -> U1WorkerResult:
        """
        Process a single PUBMED_U1 task.
        
        Args:
            task_data: Task data from queue
            
        Returns:
            U1WorkerResult with processing results
        """
        start_time = datetime.now(timezone.utc)
        task_id = task_data['id']
        trial_id = task_data['trial_id']
        payload = task_data.get('payload', {})
        
        self.logger.info(f"Starting U1 task {task_id} for trial {trial_id}")
        
        try:
            # Extract task parameters
            nct_id = payload.get('nct_id')
            asset_aliases = payload.get('asset_aliases', [])
            indication_terms = payload.get('indication_terms', [])
            max_results = payload.get('max_results', 150)
            
            # Validate required parameters
            if not asset_aliases or not indication_terms:
                raise ValueError("Asset aliases and indication terms are required for U1 processing")
            
            # Execute U1+ stage (discovery + processing mode)
            u1_result = await self.u1_processor.execute_stage_u1(
                trial_id=trial_id,
                trial_asset=asset_aliases[0],  # Primary asset name
                trial_indication=indication_terms[0],  # Primary indication
                trial_nct=nct_id,
                asset_aliases=asset_aliases,
                indication_terms=indication_terms,
                max_results=max_results
            )
            
            if not u1_result.success:
                raise Exception(f"U1 stage failed: {u1_result.error_message}")
            
            # Calculate priority for OA tasks based on U1 results
            oa_priority = self._calculate_oa_priority(trial_id, u1_result)
            
            # Enqueue OA task if there are documents with adequate scores
            oa_tasks_enqueued = 0
            if u1_result.documents_selected > 0:
                oa_success = self.queue_service.enqueue_task(
                    task_type='PUBMED_OA',
                    task_key=f'trial:{trial_id}:OA',
                    priority=oa_priority,
                    payload={
                        'trial_id': trial_id,
                        'nct_id': nct_id,
                        'asset_aliases': asset_aliases,
                        'indication_terms': indication_terms,
                        'u1_documents_selected': u1_result.documents_selected,
                        'u1_documents_scored': u1_result.documents_scored
                    },
                    trial_id=trial_id
                )
                if oa_success:
                    oa_tasks_enqueued = 1
                    self.logger.info(f"Enqueued OA task for trial {trial_id}")
                else:
                    self.logger.warning(f"Failed to enqueue OA task for trial {trial_id}")
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            self.logger.info(f"Completed U1 task {task_id}: {u1_result.documents_processed} processed, "
                           f"{u1_result.documents_selected} selected")
            
            return U1WorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=True,
                documents_discovered=u1_result.documents_discovered,
                documents_processed=u1_result.documents_processed,
                abstracts_fetched=u1_result.abstracts_fetched,
                documents_scored=u1_result.documents_scored,
                documents_selected=u1_result.documents_selected,
                oa_tasks_enqueued=oa_tasks_enqueued,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"U1 task {task_id} failed: {str(e)}"
            self.logger.error(error_msg)
            
            return U1WorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=False,
                execution_time=execution_time,
                error_message=error_msg
            )
    
    def _calculate_oa_priority(self, trial_id: int, u1_result: StageU1Result) -> float:
        """
        Calculate OA task priority based on U1 results.
        
        Args:
            trial_id: Trial identifier
            u1_result: Results from U1 processing
            
        Returns:
            Priority score (0.0 to 1.0)
        """
        base_priority = 0.6  # Medium priority
        
        # Boost priority based on number of selected documents
        if u1_result.documents_selected > 10:
            base_priority += 0.2
        elif u1_result.documents_selected > 5:
            base_priority += 0.1
        
        # Boost priority based on selection ratio
        if u1_result.documents_processed > 0:
            selection_ratio = u1_result.documents_selected / u1_result.documents_processed
            if selection_ratio > 0.5:
                base_priority += 0.1
        
        return min(base_priority, 1.0)
    
    async def run_worker(self, max_tasks: Optional[int] = None):
        """
        Run the U1 worker continuously.
        
        Args:
            max_tasks: Maximum number of tasks to process (None for unlimited)
        """
        self.logger.info("Starting U1 worker")
        tasks_processed = 0
        
        while True:
            try:
                # Clean up expired leases
                self.queue_service.cleanup_expired_leases()
                
                # Lease next task
                task_data = self.queue_service.lease_next(['PUBMED_U1'])
                if not task_data:
                    self.logger.debug("No PUBMED_U1 tasks available, waiting...")
                    await asyncio.sleep(10)
                    continue
                
                # Process task
                result = await self.process_u1_task(task_data)
                
                if result.success:
                    self.queue_service.complete_task(task_data['id'])
                    self.logger.info(f"Completed U1 task {task_data['id']} for trial {result.trial_id}")
                else:
                    self.queue_service.fail_task(task_data['id'], result.error_message or "Unknown error")
                    self.logger.error(f"Failed U1 task {task_data['id']}: {result.error_message}")
                
                tasks_processed += 1
                
                # Check if we've reached max tasks
                if max_tasks and tasks_processed >= max_tasks:
                    self.logger.info(f"Reached max tasks limit ({max_tasks}), stopping worker")
                    break
                
            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, stopping worker")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in U1 worker: {e}")
                await asyncio.sleep(5)
        
        self.logger.info(f"U1 worker stopped after processing {tasks_processed} tasks")


async def main():
    """Main entry point for running the U1 worker."""
    import argparse
    import os
    import yaml
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PubMed U1+ Worker')
    parser.add_argument('--env', default='dev', help='Environment (dev/test/prod)')
    parser.add_argument('--max-tasks', type=int, help='Maximum tasks to process')
    parser.add_argument('--config', help='Config file path')
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config_path = args.config or f'config/{args.env}.yaml'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    
    # Initialize components
    client_config = config.get('pubmed', {}).get('client_config', {})
    client = PubMedClient(client_config)
    mapper = PubMedMapper()
    queue_service = TaskQueueService(worker_id=f"u1_worker_{args.env}")
    
    # Create and run worker
    worker = U1Worker(
        client=client,
        mapper=mapper,
        queue_service=queue_service,
        config=config.get('pubmed', {})
    )
    
    await worker.run_worker(max_tasks=args.max_tasks)


if __name__ == '__main__':
    asyncio.run(main())
