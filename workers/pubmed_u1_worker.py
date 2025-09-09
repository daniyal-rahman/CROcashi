#!/usr/bin/env python3
"""
PubMed U1+ Worker

Entry point for running the U1+ worker that processes PUBMED_U1 tasks.
Handles discovery, abstract processing, and R/S scoring.
"""

import asyncio
import argparse
import logging
import os
import sys
import yaml
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

from ncfd.ingest.pubmed.client import PubMedClient
from ncfd.ingest.pubmed.mapper import PubMedMapper
from ncfd.ingest.pubmed.queue_service import TaskQueueService
from ncfd.ingest.pubmed.u1_worker import U1Worker


def setup_logging(env: str):
    """Setup logging configuration."""
    level = logging.DEBUG if env == 'dev' else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/u1_worker_{env}.log')
        ]
    )


def load_config(env: str, config_path: str = None) -> dict:
    """Load configuration for the worker."""
    if config_path:
        config_file = config_path
    else:
        config_file = f'config/{env}.yaml'
    
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    else:
        print(f"Warning: Config file {config_file} not found, using defaults")
        return {}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='PubMed U1+ Worker')
    parser.add_argument('--env', default='test', choices=['dev', 'test', 'prod'],
                       help='Environment to run in')
    parser.add_argument('--max-tasks', type=int, 
                       help='Maximum number of tasks to process (for testing)')
    parser.add_argument('--config', help='Custom config file path')
    parser.add_argument('--worker-id', help='Custom worker ID')
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.env)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting PubMed U1+ Worker (env: {args.env})")
    
    # Load configuration
    config = load_config(args.env, args.config)
    
    # Validate required environment variables
    required_env_vars = ['DATABASE_URL']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)
    
    # Initialize components
    try:
        # PubMed client configuration
        client_config = config.get('pubmed', {}).get('client_config', {})
        client = PubMedClient(client_config)
        
        # Response mapper
        mapper = PubMedMapper()
        
        # Task queue service
        worker_id = args.worker_id or f"u1_worker_{args.env}_{os.getpid()}"
        queue_service = TaskQueueService(worker_id=worker_id)
        
        # Create worker
        worker = U1Worker(
            client=client,
            mapper=mapper,
            queue_service=queue_service,
            config=config.get('pubmed', {})
        )
        
        logger.info(f"Initialized U1 worker with ID: {worker_id}")
        
        # Run worker
        await worker.run_worker(max_tasks=args.max_tasks)
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info("U1 worker shutdown complete")


if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    asyncio.run(main())
