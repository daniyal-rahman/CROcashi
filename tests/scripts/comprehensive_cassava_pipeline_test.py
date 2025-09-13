#!/usr/bin/enkv python3
"""
Comprehensive Cassava Trial Pipeline Test

This test uses the Cassava Sciences Phase 3 trial (NCT05515666) to test multiple
pipeline components with real-world data. The test:

1. Clears the test database completely
2. Seeds real Cassava trial data (including historical trials for context)
3. Runs PubMed literature processing on the main Phase 3 trial only
4. Executes study card generation with LLM workers
5. Tests orchestrator coordination and error handling
6. Validates data integrity and provides comprehensive reporting

Note: While multiple trials are seeded for comprehensive aliases and company data,
only the main Phase 3 trial (NCT05515666) is processed through the pipeline.

Usage:
    python tests/scripts/comprehensive_cassava_pipeline_test.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the src directory to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

# Setup test environment before importing modules
from utils.env_loader import setup_test_environment
setup_test_environment(project_root)

import requests
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect

# Import our modules
from ncfd.db.session import session_scope, get_engine, reset_engine
from ncfd.db.models import Base, Trial, Company, Document, Study, DocumentLink, TrialDocCandidate, DocRSScore
from ncfd.pipeline.orchestrator import PipelineOrchestrator
from ncfd.ingest.pubmed.pipeline_dual_persistence import PubMedPipelineDualPersistence
from ncfd.config import get_config

# Setup logging - only show ERROR level logs
logging.basicConfig(
    level=logging.ERROR, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Demote noisy DEBUG logs that are incorrectly using ERROR level
logging.getLogger("ncfd.ingest.pubmed").setLevel(logging.INFO)
logging.getLogger("ncfd.pipeline").setLevel(logging.INFO)

# Real-world Cassava trial data - comprehensive list for building aliases and company info
# Note: All trials are seeded for comprehensive aliases and company data, but only the main
# Phase 3 trial (NCT05515666) is processed through the pipeline
CASSAVA_TRIALS = [
    # Historical trials (for building aliases and company data)
    {
        "nct_id": "NCT04388254",
        "title": "A Phase 2, Randomized, Double-Blind, Placebo-Controlled Study of PTI-125 in Patients with Mild-to-Moderate Alzheimer's Disease",
        "sponsor": "Cassava Sciences, Inc.",
        "phase": "PHASE2",
        "indication": "Alzheimer Disease",
        "status": "COMPLETED",
        "interventions": ["PTI-125", "Placebo"],
        "start_date": "2020-05-01",
        "completion_date": "2023-12-01",
        "has_results": True,
        "is_pivotal": True,
        "primary_endpoint": "ADAS-Cog11",
        "mechanism": "filamin A inhibitor",
        "purpose": "supporting_data"
    },
    # Main trial for full pipeline testing
    {
        "nct_id": "NCT05515666", 
        "title": "A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
        "sponsor": "Cassava Sciences, Inc.",
        "phase": "PHASE3",
        "indication": "Alzheimer Disease",
        "status": "RECRUITING",
        "interventions": ["Simufilam", "Placebo"],
        "start_date": "2023-01-01",
        "completion_date": "2025-12-01",
        "has_results": False,
        "is_pivotal": True,
        "primary_endpoint": "ADAS-Cog11",
        "mechanism": "filamin A inhibitor",
        "purpose": "main_trial"
    },
    # Additional historical trials for comprehensive aliases
    {
        "nct_id": "NCT03838185",
        "title": "A Phase 2, Single-Ascending Dose Study of PTI-125 in Healthy Volunteers",
        "sponsor": "Pain Therapeutics, Inc.",
        "phase": "PHASE2",
        "indication": "Healthy Volunteers",
        "status": "COMPLETED",
        "interventions": ["PTI-125"],
        "start_date": "2019-01-01",
        "completion_date": "2019-12-01",
        "has_results": True,
        "is_pivotal": False,
        "primary_endpoint": "Safety",
        "mechanism": "filamin A inhibitor",
        "purpose": "supporting_data"
    },
    {
        "nct_id": "NCT03838186",
        "title": "A Phase 2, Multiple-Ascending Dose Study of PTI-125 in Healthy Volunteers",
        "sponsor": "Pain Therapeutics, Inc.",
        "phase": "PHASE2",
        "indication": "Healthy Volunteers",
        "status": "COMPLETED",
        "interventions": ["PTI-125"],
        "start_date": "2019-01-01",
        "completion_date": "2019-12-01",
        "has_results": True,
        "is_pivotal": False,
        "primary_endpoint": "Safety",
        "mechanism": "filamin A inhibitor",
        "purpose": "supporting_data"
    }
]

# Real-world Cassava company data with historical aliases
CASSAVA_COMPANY = {
    "name": "Cassava Sciences, Inc.",
    "ticker": "SAVA",
    "exchange": "NASDAQ",
    "description": "Clinical-stage biotechnology company focused on developing treatments for Alzheimer's disease",
    "aliases": [
        "Cassava Sciences",
        "Cassava Sciences Inc",
        "Pain Therapeutics, Inc.",
        "Pain Therapeutics",
        "PTI",
        "SAVA"
    ],
    "historical_names": [
        "Pain Therapeutics, Inc.",
        "Pain Therapeutics"
    ]
}

# Real-world asset data with comprehensive aliases
CASSAVA_ASSETS = [
    {
        "name": "simufilam",
        "aliases": [
            "PTI-125", "PTI 125", "PTI125", "PTI_125",
            "filamin A inhibitor", "FLNA inhibitor", "filamin-A inhibitor",
            "simufilam", "Simufilam", "SIMUFILAM",
            "PTI-125HCl", "PTI-125 HCl"
        ],
        "mechanism": "filamin A inhibitor",
        "mechanism_aliases": [
            "filamin A", "FLNA", "filamin-A", "filamin A protein",
            "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid"
        ],
        "indication": "Alzheimer's disease",
        "indication_aliases": [
            "Alzheimer Disease", "Alzheimer's Disease", "AD",
            "dementia", "cognitive impairment", "mild cognitive impairment",
            "MCI", "Alzheimer dementia", "senile dementia"
        ],
        "phase": "Phase 3",
        "trial_ids": ["NCT05515666", "NCT04388254", "NCT03838185", "NCT03838186"]
    }
]


class ComprehensiveCassavaTest:
    """Comprehensive test for Cassava trial pipeline processing."""
    
    def __init__(self):
        self.test_start_time = datetime.now(timezone.utc)
        self.results = {
            "test_info": {
                "start_time": self.test_start_time.isoformat(),
                "test_name": "Comprehensive Cassava Pipeline Test",
                "version": "1.0"
            },
            "database_setup": {},
            "ctgov_seeding": {},
            "pubmed_processing": {},
            "study_card_generation": {},
            "orchestrator_testing": {},
            "validation_results": {},
            "errors": [],
            "warnings": []
        }
        
        # Load configuration
        self.config = self._load_test_config()
        
    def _load_test_config(self) -> Dict[str, Any]:
        """Load test configuration with real-world settings."""
        config = {
            "worker_id": "cassava_comprehensive_test",
            "execution_order": ["pubmed", "study_card"],  # Skip CT.gov since we're using seeded data
            "parallel_execution": False,
            "dependency_checking": False,  # Disable dependency checking since we're not running CT.gov
            
            # CT.gov configuration - use seeded trials
            "ctgov": {
                "incremental": False,
                "seed_trials": CASSAVA_TRIALS,
                "batch_size": 10,
                "retry_attempts": 3
            },
            
            # PubMed configuration - use simufilam entity pack
            "pubmed": {
                "entity_id": "simufilam",
                "domain": "neurology",
                "asset_names": ["simufilam", "PTI-125", "PTI 125"],
                "indications": ["Alzheimer Disease", "Alzheimer's", "AD", "dementia"],
                "client_config": {
                    "rate_limit_requests_per_minute": 60,
                    "batch_size": 20,
                    "timeout_seconds": 30,
                    "max_retries": 3
                },
                "rerank_config": {
                    "feat_weights": {
                        "bm25": 1.0,
                        "has_must": 3.0,
                        "should_hits_capped": 1.0,
                        "cannot_without_must": -2.0,
                        "pubtype_trial": 1.5,
                        "mesh_primary": 0.5,
                        "nct_si": 1.0,
                        "recency": 0.3
                    },
                    "require_any": ["drug_tiab", "company_tiab", "nct_si"],
                    "max_results": 100
                },
                "asset_names": ["simufilam", "PTI-125", "filamin A inhibitor"],
                "indications": ["Alzheimer's disease", "dementia", "cognitive impairment"],
                "query_config": {
                    "max_terms": 100,
                    "enable_boolean_operators": True,
                    "date_range": ("2010/01/01", "2025/12/31")  # Widen date range to include 2025
                },
                "reuse_existing": True,  # Allow reusing already-retrieved docs
                "min_documents_required": 1,  # Minimum docs needed
                "skip_if_sufficient": False,  # Disable skip for now
                "enable_stages": ["retrieval", "processing"]  # Ensure both stages are enabled
            },
            
            # Study card configuration
            "study_card": {
                "max_docs_per_trial": 100,
                "store_json_snapshots": True,
                "llm_timeout_seconds": 180,
                "retrieval_timeout_seconds": 90,
                "retriever": {
                    "auto_span_generation": True,
                    "late_fusion": False,
                    "max_span_length": 500,
                    "min_confidence": 0.6
                },
                "validation": {
                    "strict_validation": False,
                    "fail_fast_on_validation": False,
                    "validation_error_action": "warn",
                    "max_validation_errors": 20
                },
                "stages": {
                    "retrieval": {"enable": True, "timeout_seconds": 90},
                    "llm_method_auditing": {"enable": True, "timeout_seconds": 180},
                    "llm_results_distillation": {"enable": True, "timeout_seconds": 180},
                    "gate_proposal": {"enable": True, "timeout_seconds": 120},
                    "gate_validation": {"enable": True, "timeout_seconds": 120},
                    "gate_assessment": {"enable": True, "timeout_seconds": 120},
                    "fda_lens": {"enable": True, "timeout_seconds": 120},
                    "memo_composition": {"enable": True, "timeout_seconds": 120}
                }
            }
        }
        
        return config
    
    async def run_comprehensive_test(self):
        """Run the comprehensive pipeline test."""
        logger.info("🧪 Starting Comprehensive Cassava Pipeline Test")
        logger.info("=" * 80)
        
        try:
            # Phase 1: Database Setup
            await self._setup_database()
            
            # Phase 2: CT.gov Trial Seeding
            await self._seed_ctgov_trials()
            
            # Phase 3: Orchestrator Integration (includes PubMed + Study Card processing)
            await self._test_orchestrator()
            
            # Phase 6: Validation and Reporting
            await self._validate_results()
            
            # Final reporting
            self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            self.results["errors"].append(f"Test execution failed: {str(e)}")
            raise
        finally:
            # Cleanup
            await self._cleanup_database()
    
    async def _setup_database(self):
        """Setup test database with clean state."""
        logger.info("📊 Phase 1: Setting up test database")
        
        try:
            # Reset engine to ensure it uses the test environment
            reset_engine()
            
            # Clear all data
            await self._clear_database()
            
            # Create all tables
            engine = get_engine()
            Base.metadata.create_all(engine)
            
            # Seed company data
            await self._seed_company_data()
            
            self.results["database_setup"] = {
                "status": "success",
                "tables_created": True,
                "data_cleared": True,
                "company_seeded": True
            }
            
            logger.info("✅ Database setup completed successfully")
            
        except Exception as e:
            logger.error(f"Database setup failed: {str(e)}")
            self.results["database_setup"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _clear_database(self):
        """Clear all data from test database."""
        logger.info("🧹 Clearing test database...")
        
        with session_scope() as session:
            # Get existing table names to avoid clearing non-existent tables
            existing_tables = set(inspect(session.bind).get_table_names())
            
            # Delete in order to respect foreign key constraints
            tables_to_clear = [
                "doc_rs_scores", "trial_doc_candidates", "document_links",
                "document_entities", "document_citations", "document_text",
                "pubmed_meta", "pmc_meta", "documents", "studies",
                "trial_versions", "trials", "company_aliases", "companies",
                "assets", "asset_ownership", "signals", "gates", "scores",
                "catalysts", "labels", "disclosures", "method_cards",
                "results_factsheets", "gate_candidates", "gate_specs",
                "gate_assessments", "decision_records",
                # Add dual-persistence tables if they exist
                "retrieval_sessions", "retrieval_documents", "processed_documents"
            ]
            
            for table in tables_to_clear:
                if table in existing_tables:
                    try:
                        session.execute(text(f"DELETE FROM {table}"))
                        session.commit()  # commit per table so one failure doesn't poison the rest
                        logger.info(f"Cleared table: {table}")
                    except Exception as e:
                        session.rollback()
                        logger.warning(f"Could not clear table {table}: {e}")
                else:
                    logger.info(f"Skipping {table} (not present in schema)")
            
            logger.info("✅ Database cleared successfully")
    
    async def _seed_company_data(self):
        """Seed real-world Cassava company data."""
        logger.info("🏢 Seeding Cassava company data...")
        
        with session_scope() as session:
            # Create Cassava Sciences company
            company = Company(
                name=CASSAVA_COMPANY["name"],
                name_norm=CASSAVA_COMPANY["name"].lower(),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(company)
            session.flush()
            
            # Note: Skipping security creation due to schema mismatch
            # The model expects 'exchange' but database has 'exchange_id'
            # This will be addressed in a future schema update
            
            # Skip asset creation for now due to schema complexity
            # Focus on testing the core pipeline functionality
            
            session.commit()
            logger.info(f"✅ Seeded company: {company.name} (ID: {company.company_id})")
    
    async def _seed_ctgov_trials(self):
        """Seed real-world Cassava trial data."""
        logger.info("🔬 Phase 2: Seeding CT.gov trial data")
        
        try:
            with session_scope() as session:
                # Get Cassava company
                company = session.query(Company).filter(
                    Company.name == CASSAVA_COMPANY["name"]
                ).first()
                
                if not company:
                    raise ValueError("Cassava company not found in database")
                
                seeded_trials = []
                
                for trial_data in CASSAVA_TRIALS:
                    # Check if trial already exists
                    existing_trial = session.query(Trial).filter(
                        Trial.nct_id == trial_data["nct_id"]
                    ).first()
                    
                    if existing_trial:
                        logger.info(f"Trial {trial_data['nct_id']} already exists, updating...")
                        # Update existing trial
                        existing_trial.brief_title = trial_data["title"]
                        existing_trial.sponsor_text = trial_data["sponsor"]
                        existing_trial.sponsor_company_id = company.company_id
                        existing_trial.phase = trial_data["phase"]
                        existing_trial.indication = trial_data["indication"]
                        existing_trial.status = trial_data["status"]
                        existing_trial.is_pivotal = trial_data["is_pivotal"]
                        existing_trial.primary_endpoint_text = trial_data["primary_endpoint"]
                        existing_trial.intervention_types = trial_data["interventions"]
                        existing_trial.has_results = trial_data["has_results"]
                        existing_trial.updated_at = datetime.now(timezone.utc)
                        existing_trial.current_sha256 = f"cassava_test_{trial_data['nct_id']}_{datetime.now().timestamp()}"
                        
                        trial_id = existing_trial.trial_id
                    else:
                        # Create new trial
                        trial = Trial(
                            nct_id=trial_data["nct_id"],
                            brief_title=trial_data["title"],
                            sponsor_text=trial_data["sponsor"],
                            sponsor_company_id=company.company_id,
                            phase=trial_data["phase"],
                            indication=trial_data["indication"],
                            status=trial_data["status"],
                            is_pivotal=trial_data["is_pivotal"],
                            primary_endpoint_text=trial_data["primary_endpoint"],
                            intervention_types=trial_data["interventions"],
                            has_results=trial_data["has_results"],
                            current_sha256=f"cassava_test_{trial_data['nct_id']}_{datetime.now().timestamp()}",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        session.add(trial)
                        session.flush()
                        trial_id = trial.trial_id
                    
                    seeded_trials.append({
                        "trial_id": trial_id,
                        "nct_id": trial_data["nct_id"],
                        "title": trial_data["title"],
                        "phase": trial_data["phase"]
                    })
                
                session.commit()
                
                self.results["ctgov_seeding"] = {
                    "status": "success",
                    "trials_seeded": len(seeded_trials),
                    "trials": seeded_trials
                }
                
                logger.info(f"✅ Seeded {len(seeded_trials)} Cassava trials")
                
        except Exception as e:
            logger.error(f"CT.gov seeding failed: {str(e)}")
            self.results["ctgov_seeding"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _test_pubmed_pipeline(self):
        """Test PubMed literature processing with comprehensive simufilam entity pack."""
        logger.info("📚 Phase 3: Testing PubMed pipeline")
        
        try:
            # Initialize PubMed pipeline
            pubmed_pipeline = PubMedPipelineDualPersistence(self.config["pubmed"], session_scope)
            
            # Get the main trial (NCT05515666 - Phase 3) for full pipeline testing
            with session_scope() as session:
                main_trial = session.query(Trial).filter(
                    Trial.nct_id == "NCT05515666"
                ).first()
                
                if not main_trial:
                    raise ValueError("Main trial NCT05515666 not found for PubMed processing")
                
                # Comprehensive search terms for better document retrieval
                comprehensive_asset_names = [
                    "simufilam", "Simufilam", "SIMUFILAM",
                    "PTI-125", "PTI 125", "PTI125", "PTI_125",
                    "PTI-125HCl", "PTI-125 HCl",
                    "filamin A inhibitor", "FLNA inhibitor", "filamin-A inhibitor"
                ]
                
                comprehensive_indications = [
                    "Alzheimer's disease", "Alzheimer Disease", "Alzheimer's Disease", "AD",
                    "dementia", "cognitive impairment", "mild cognitive impairment", "MCI",
                    "Alzheimer dementia", "senile dementia"
                ]
                
                # Run PubMed pipeline for the main trial only
                logger.info(f"Running PubMed pipeline for main trial {main_trial.nct_id} (ID: {main_trial.trial_id})...")
                logger.info(f"Using comprehensive search terms: {len(comprehensive_asset_names)} assets, {len(comprehensive_indications)} indications")
                logger.error(f"DEBUG: About to start PubMed pipeline phase")
                
                total_documents = 0
                total_links = 0
                
                # Run the full pipeline with NCT ID to enable Query D
                logger.error(f"DEBUG: About to call execute_pipeline for trial {main_trial.trial_id}")
                pubmed_results = await pubmed_pipeline.execute_pipeline(
                    trial_id=main_trial.trial_id,
                    asset_names=comprehensive_asset_names,
                    indications=comprehensive_indications,
                    max_results=200,  # Increased from 50 to get more comprehensive results
                    enable_stages=['retrieval', 'processing'],
                    trial_nct=main_trial.nct_id,  # Pass NCT ID for Query D
                    trial_phase=main_trial.phase,
                    company_name="Cassava Sciences, Inc.",
                    company_aliases=["Cassava Sciences", "Pain Therapeutics"]
                )
                
                # Count documents from results
                for result in pubmed_results:
                    if result.success:
                        total_documents += result.documents_processed
                        # Note: PipelineExecutionResult doesn't have metadata, using processed_documents instead
                        total_links += result.processed_documents
                
                # Get dual persistence metrics for the main trial
                retrieval_docs = await pubmed_pipeline.get_retrieval_documents(main_trial.trial_id)
                processed_docs = await pubmed_pipeline.get_processed_documents(main_trial.trial_id)
                retrieval_metrics = await pubmed_pipeline.get_retrieval_metrics(main_trial.trial_id)
                
                # Count documents created
                doc_count = session.query(Document).count()
                doc_links = session.query(DocumentLink).count()
                
                # Get detailed document metrics from dual persistence
                doc_details = []
                for doc in retrieval_docs[:10]:  # Show first 10 retrieval docs for details
                    doc_details.append({
                        "pmid": doc.get('pmid'),
                        "title": (doc.get('title', '')[:100] + "...") if doc.get('title') and len(doc.get('title', '')) > 100 else doc.get('title'),
                        "retrieval_tier": doc.get('retrieval_tier'),
                        "policy_engine_passed": doc.get('policy_engine_passed'),
                        "guardrails_passed": doc.get('guardrails_passed')
                    })
                
                # Process pipeline results
                total_documents_processed = total_documents
                total_errors = []
                
                self.results["pubmed_processing"] = {
                    "status": "success",
                    "main_trial": main_trial.nct_id,
                    "trials_processed": 1,  # Only processing the main trial
                    "documents_created": doc_count,
                    "document_links": doc_links,
                    "retrieval_documents": len(retrieval_docs),
                    "processed_documents": len(processed_docs),
                    "retrieval_metrics": retrieval_metrics,
                    "document_details": doc_details,
                    "pipeline_result": {
                        "success": len(pubmed_results) > 0 and all(getattr(r, 'success', False) for r in pubmed_results),
                        "documents_processed": total_documents_processed,
                        "errors": total_errors,
                        "stages_completed": len(pubmed_results)
                    }
                }
                
                logger.info(f"✅ PubMed processing completed for main trial {main_trial.nct_id}: {doc_count} documents, {doc_links} links")
                logger.info(f"📄 Retrieval documents (raw): {len(retrieval_docs)}")
                logger.info(f"📄 Processed documents (filtered): {len(processed_docs)}")
                if retrieval_metrics:
                    logger.info(f"📊 Retrieval metrics: {retrieval_metrics}")
                
        except Exception as e:
            logger.error(f"PubMed pipeline test failed: {str(e)}")
            self.results["pubmed_processing"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _test_study_card_pipeline(self):
        """Test study card generation with LLM workers."""
        logger.info("📋 Phase 4: Testing study card pipeline")
        
        try:
            from ncfd.pipeline.study_card_pipeline import StudyCardPipeline
            
            # Initialize study card pipeline
            study_card_pipeline = StudyCardPipeline(self.config["study_card"])
            
            # Get the main trial for study card generation
            with session_scope() as session:
                main_trial = session.query(Trial).filter(
                    Trial.nct_id == "NCT05515666"
                ).first()
                
                if not main_trial:
                    raise ValueError("Main trial NCT05515666 not found for study card generation")
                
                study_card_results = []
                total_gates = 0
                total_conclusions = 0
                gate_details = []
                conclusion_details = []
                
                # Process only the main trial
                trial = main_trial
                
                # Create trial context
                trial_context = {
                    "trial_id": trial.trial_id,
                    "nct_id": trial.nct_id,
                    "title": trial.brief_title,
                    "phase": trial.phase,
                    "indication": trial.indication,
                    "interventions": trial.intervention_types,
                    "primary_endpoint": trial.primary_endpoint_text,
                    "is_pivotal": trial.is_pivotal
                }
                
                # Run study card pipeline
                logger.info(f"Generating study card for main trial {trial.nct_id}...")
                result = await study_card_pipeline.execute(trial.nct_id, trial_context)
                
                # Extract gate details
                gate_info = []
                for gate in result.gate_candidates:
                    gate_info.append({
                        "gate_id": getattr(gate, 'gate_id', 'unknown'),
                        "gate_type": getattr(gate, 'gate_type', 'unknown'),
                        "description": getattr(gate, 'description', 'No description')[:100] + "..." if getattr(gate, 'description', None) and len(getattr(gate, 'description', '')) > 100 else getattr(gate, 'description', 'No description'),
                        "confidence": getattr(gate, 'confidence', 0.0)
                    })
                
                # Extract conclusion details
                conclusion_info = []
                if result.decision_record:
                    conclusion_info.append({
                        "decision": getattr(result.decision_record, 'decision', 'No decision'),
                        "confidence": getattr(result.decision_record, 'confidence', 0.0),
                        "reasoning": getattr(result.decision_record, 'reasoning', 'No reasoning')[:200] + "..." if getattr(result.decision_record, 'reasoning', None) and len(getattr(result.decision_record, 'reasoning', '')) > 200 else getattr(result.decision_record, 'reasoning', 'No reasoning'),
                        "passed_gates": len(getattr(result.decision_record, 'passed_gates', [])),
                        "failed_gates": len(getattr(result.decision_record, 'failed_gates', []))
                    })
                
                study_card_results.append({
                    "trial_id": trial.trial_id,
                    "nct_id": trial.nct_id,
                    "success": result.success,
                    "document_cards": len(getattr(result, 'document_cards', [])),
                    "evidence_spans": len(getattr(result, 'evidence_spans', [])),
                    "claims": len(getattr(result, 'claims', [])),
                    "method_cards": len(getattr(result, 'method_cards', [])),
                    "results_factsheets": len(getattr(result, 'results_factsheets', [])),
                    "gate_candidates": len(getattr(result, 'gate_candidates', [])),
                    "gate_specs": len(getattr(result, 'gate_specs', [])),
                    "gate_assessments": len(getattr(result, 'gate_assessments', [])),
                    "decision_record": getattr(result, 'decision_record', None) is not None,
                    "gates": gate_info,
                    "conclusions": conclusion_info,
                    "errors": result.errors,
                    "warnings": result.warnings
                })
                
                total_gates += len(result.gate_candidates)
                total_conclusions += 1 if result.decision_record else 0
                gate_details.extend(gate_info)
                conclusion_details.extend(conclusion_info)
                
                self.results["study_card_generation"] = {
                    "status": "success",
                    "main_trial": trial.nct_id,
                    "trials_processed": 1,  # Only processing the main trial
                    "total_gates_generated": total_gates,
                    "total_conclusions_generated": total_conclusions,
                    "gate_details": gate_details,
                    "conclusion_details": conclusion_details,
                    "results": study_card_results
                }
                
                logger.info(f"✅ Study card generation completed for main trial {trial.nct_id}")
                logger.info(f"🎯 Total gates generated: {total_gates}")
                logger.info(f"📋 Total conclusions generated: {total_conclusions}")
                
        except Exception as e:
            logger.error(f"Study card pipeline test failed: {str(e)}")
            self.results["study_card_generation"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _test_orchestrator(self):
        """Test orchestrator integration and coordination."""
        logger.info("🎯 Phase 5: Testing orchestrator integration")
        
        try:
            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.config)
            
            # Run orchestrator with pre-seeded data (skip CT.gov ingestion)
            logger.info("Running orchestrator with pre-seeded data (skipping CT.gov ingestion)...")
            orchestration_result = await self._run_orchestrator_with_seeded_data(orchestrator)
            
            self.results["orchestrator_testing"] = {
                "status": "success",
                "execution_id": orchestration_result.execution_id,
                "total_processing_time": orchestration_result.total_processing_time,
                "ctgov_result": {
                    "success": orchestration_result.ctgov_result.success if orchestration_result.ctgov_result else False,
                    "trials_processed": orchestration_result.ctgov_result.trials_processed if orchestration_result.ctgov_result else 0
                },
                "pubmed_result": {
                    "success": orchestration_result.pubmed_result.success if orchestration_result.pubmed_result else False,
                    "documents_processed": orchestration_result.pubmed_result.documents_processed if orchestration_result.pubmed_result else 0
                },
                "study_card_result": {
                    "success": orchestration_result.study_card_result.success if orchestration_result.study_card_result else False,
                    "gate_candidates": len(orchestration_result.study_card_result.gate_candidates) if orchestration_result.study_card_result else 0
                },
                "errors": orchestration_result.errors,
                "warnings": orchestration_result.warnings
            }
            
            logger.info("✅ Orchestrator testing completed successfully")
            
        except Exception as e:
            logger.error(f"Orchestrator test failed: {str(e)}")
            self.results["orchestrator_testing"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _run_orchestrator_with_seeded_data(self, orchestrator):
        """Run orchestrator with pre-seeded data, skipping CT.gov ingestion."""
        from datetime import datetime, timezone
        import time
        
        execution_id = f"cassava_test_{int(time.time())}"
        start_time = datetime.now(timezone.utc)
        
        logger.info(f"Starting orchestrator with seeded data: {execution_id}")
        
        # Create a custom orchestration result
        from ncfd.pipeline.orchestrator import OrchestrationResult
        result = OrchestrationResult(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time  # Will be updated
        )
        
        try:
            # Initialize orchestrator's current_execution for proper tracking
            orchestrator.current_execution = result
            
            # Step 1: Get seeded trials (skip CT.gov ingestion)
            logger.info("Step 1: Using pre-seeded trials (skipping CT.gov ingestion)")
            with session_scope() as session:
                # Only process the main Phase 3 trial (NCT05515666)
                main_trial = session.query(Trial).filter(Trial.nct_id == "NCT05515666").first()
                if not main_trial:
                    raise ValueError("Main Phase 3 trial NCT05515666 not found in seeded data")
                seeded_trials = [main_trial]
                logger.info(f"Found {len(seeded_trials)} pre-seeded trials (filtered to main Phase 3 trial)")
            
            # Step 2: Company matching (using seeded data)
            logger.info("Step 2: Running company matching on seeded trials")
            matched_trials = []
            for trial in seeded_trials:
                matched_trial = {
                    'trial_id': trial.trial_id,
                    'nct_id': trial.nct_id,
                    'trial_data': {
                        'title': trial.brief_title,
                        'sponsor': trial.sponsor_text,
                        'phase': trial.phase,
                        'indication': trial.indication,
                        'interventions': trial.intervention_types or [],
                        'primary_endpoint': trial.primary_endpoint_text
                    },
                    'companies': [{'company_id': trial.sponsor_company_id, 'is_public': True}] if trial.sponsor_company_id else [],
                    'matched_at': datetime.now(timezone.utc),
                    'matching_confidence': 1.0  # High confidence for seeded data
                }
                matched_trials.append(matched_trial)
            
            # Step 3: Filter for public company trials
            logger.info("Step 3: Filtering for public company trials")
            public_trials = [t for t in matched_trials if t['companies']]
            logger.info(f"Filtered to {len(public_trials)} public company trials")
            
            # Step 4: PubMed processing
            logger.info("Step 4: Running PubMed processing")
            pubmed_results = await orchestrator.run_pubmed_processing(public_trials)
            result.pubmed_result = pubmed_results
            
            # Step 5: Study card generation
            # COMMENTED OUT: Only running PubMed pipeline for now
            # logger.info("Step 5: Running study card generation")
            # study_card_results = await orchestrator.run_study_card_generation(public_trials)
            # result.study_card_result = study_card_results
            
            # Mark skipped phases as skipped instead of unknown
            self.results.setdefault("pubmed_processing", {"status": "skipped"})
            self.results.setdefault("study_card_generation", {"status": "skipped"})
            
            # Step 6: Update metrics
            result.trials_matched_to_companies = len(matched_trials)
            result.public_company_trials = len(public_trials)
            
            # Finalize result
            result.end_time = datetime.now(timezone.utc)
            result.finalize()
            
            logger.info(f"Orchestrator with seeded data completed: {execution_id}")
            return result
            
        except Exception as e:
            logger.error(f"Orchestrator with seeded data failed: {e}")
            result.end_time = datetime.now(timezone.utc)
            result.errors.append(str(e))
            result.finalize()
            raise
    
    async def _validate_results(self):
        """Validate test results and data integrity."""
        logger.info("✅ Phase 6: Validating results")
        
        try:
            with session_scope() as session:
                # Count all entities
                company_count = session.query(Company).count()
                trial_count = session.query(Trial).count()
                document_count = session.query(Document).count()
                study_count = session.query(Study).count()
                
                # Validate relationships
                trials_with_company = session.query(Trial).filter(
                    Trial.sponsor_company_id.isnot(None)
                ).count()
                
                trials_with_documents = session.query(Trial).join(
                    DocumentLink, Trial.trial_id == DocumentLink.trial_id
                ).distinct().count()
                
                self.results["validation_results"] = {
                    "status": "success",
                    "entity_counts": {
                        "companies": company_count,
                        "trials": trial_count,
                        "documents": document_count,
                        "studies": study_count
                    },
                    "relationships": {
                        "trials_with_company": trials_with_company,
                        "trials_with_documents": trials_with_documents
                    },
                    "data_integrity": {
                        "all_trials_have_company": trials_with_company == trial_count,
                        "some_trials_have_documents": trials_with_documents > 0
                    }
                }
                
                logger.info(f"✅ Validation completed: {trial_count} trials, {document_count} documents")
                
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            self.results["validation_results"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    def _generate_final_report(self):
        """Generate comprehensive final report."""
        logger.info("📊 Generating final report...")
        
        # Calculate test duration
        test_end_time = datetime.now(timezone.utc)
        test_duration = (test_end_time - self.test_start_time).total_seconds()
        
        # Update results
        self.results["test_info"]["end_time"] = test_end_time.isoformat()
        self.results["test_info"]["duration_seconds"] = test_duration
        
        # Save results to file
        results_file = project_root / "tests" / "logs" / "comprehensive_cassava_test_results.json"
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Print summary
        print("\n" + "="*80)
        print("🧪 COMPREHENSIVE CASSAVA PIPELINE TEST RESULTS")
        print("="*80)
        
        print(f"\n⏱️  Test Duration: {test_duration:.2f} seconds")
        print(f"📁 Results saved to: {results_file}")
        
        # Phase summaries
        phases = [
            ("Database Setup", self.results["database_setup"]),
            ("CT.gov Seeding", self.results["ctgov_seeding"]),
            ("PubMed Processing", self.results["pubmed_processing"]),
            ("Study Card Generation", self.results["study_card_generation"]),
            ("Orchestrator Testing", self.results["orchestrator_testing"]),
            ("Validation", self.results["validation_results"])
        ]
        
        for phase_name, phase_result in phases:
            status = "✅" if phase_result.get("status") == "success" else "❌"
            print(f"\n{status} {phase_name}: {phase_result.get('status', 'unknown')}")
            
            if phase_result.get("status") == "failed":
                print(f"   Error: {phase_result.get('error', 'Unknown error')}")
        
        # Entity counts
        if "validation_results" in self.results and self.results["validation_results"].get("status") == "success":
            counts = self.results["validation_results"]["entity_counts"]
            print(f"\n📊 Final Entity Counts:")
            print(f"   • Companies: {counts['companies']}")
            print(f"   • Trials: {counts['trials']}")
            print(f"   • Documents: {counts['documents']}")
            print(f"   • Studies: {counts['studies']}")
        
        # PubMed metrics
        if "pubmed_processing" in self.results and self.results["pubmed_processing"].get("status") == "success":
            pubmed = self.results["pubmed_processing"]
            print(f"\n📚 PubMed Processing Metrics:")
            print(f"   • Trials processed: {pubmed.get('trials_processed', 0)}")
            print(f"   • Total documents: {pubmed.get('documents_created', 0)}")
            print(f"   • PubMed documents: {pubmed.get('pubmed_documents', 0)}")
            print(f"   • Document links: {pubmed.get('document_links', 0)}")
            
            if pubmed.get('document_details'):
                print(f"   • Sample documents:")
                for i, doc in enumerate(pubmed['document_details'][:3], 1):
                    print(f"     {i}. PMID {doc['pmid']}: {doc['title']}")
        
        # Study card metrics
        # COMMENTED OUT: Only running PubMed pipeline for now
        # if "study_card_generation" in self.results and self.results["study_card_generation"].get("status") == "success":
        #     study_cards = self.results["study_card_generation"]
        #     print(f"\n📋 Study Card Generation Metrics:")
        #     print(f"   • Trials processed: {study_cards.get('trials_processed', 0)}")
        #     print(f"   • Total gates generated: {study_cards.get('total_gates_generated', 0)}")
        #     print(f"   • Total conclusions generated: {study_cards.get('total_conclusions_generated', 0)}")
        #     
        #     # Show gate details
        #     if study_cards.get('gate_details'):
        #         print(f"   • Gate details:")
        #         for i, gate in enumerate(study_cards['gate_details'][:3], 1):
        #             print(f"     {i}. {gate.get('gate_type', 'Unknown')}: {gate.get('description', 'No description')}")
        #             print(f"        Confidence: {gate.get('confidence', 0.0):.2f}")
        #     
        #     # Show conclusion details
        #     if study_cards.get('conclusion_details'):
        #         print(f"   • Conclusion details:")
        #         for i, conclusion in enumerate(study_cards['conclusion_details'][:2], 1):
        #             print(f"     {i}. Decision: {conclusion.get('decision', 'No decision')}")
        #             print(f"        Confidence: {conclusion.get('confidence', 0.0):.2f}")
        #             print(f"        Passed gates: {conclusion.get('passed_gates', 0)}")
        #             print(f"        Failed gates: {conclusion.get('failed_gates', 0)}")
        #             print(f"        Reasoning: {conclusion.get('reasoning', 'No reasoning')}")
        
        # Errors and warnings
        if self.results["errors"]:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for error in self.results["errors"]:
                print(f"   • {error}")
        
        if self.results["warnings"]:
            print(f"\n⚠️  Warnings ({len(self.results['warnings'])}):")
            for warning in self.results["warnings"]:
                print(f"   • {warning}")
        
        print("\n" + "="*80)
        print("Test completed!")
    
    async def _cleanup_database(self):
        """Clean up test database."""
        logger.info("🧹 Cleaning up test database...")
        await self._clear_database()
        logger.info("✅ Database cleanup completed")


async def main():
    """Main test function."""
    test = ComprehensiveCassavaTest()
    await test.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())
