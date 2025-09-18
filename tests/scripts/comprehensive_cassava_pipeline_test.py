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
from ncfd.db.models import Base, Trial, Company, Document, Study, DocumentLink, TrialDocCandidate
from ncfd.pipeline.orchestrator import PipelineOrchestrator
from ncfd.ingest.pubmed import RetrievalProcessor, AbstractProcessor
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

def deduplicate_and_canonicalize_aliases(aliases: List[str]) -> Dict[str, List[str]]:
    """
    Deduplicate and canonicalize aliases, returning both a set for uniqueness
    and a display list for presentation.
    
    This fixes the issue where aliases like ['simufilam', 'Simufilam', 'SIMUFILAM']
    were appearing repeatedly. The function:
    1. Normalizes aliases (lowercase, strip whitespace) for deduplication
    2. Keeps the first occurrence of each normalized alias
    3. Returns both a canonical set (for uniqueness checks) and display list (for presentation)
    
    Args:
        aliases: List of alias strings (may contain duplicates)
        
    Returns:
        Dict with 'canonical_set' (Set[str]) and 'display_list' (List[str])
    """
    # Normalize aliases for deduplication (lowercase, strip whitespace)
    normalized_to_original = {}
    for alias in aliases:
        normalized = alias.strip().lower()
        if normalized and normalized not in normalized_to_original:
            normalized_to_original[normalized] = alias.strip()
    
    # Create canonical set (normalized) and display list (original)
    canonical_set = set(normalized_to_original.keys())
    display_list = list(normalized_to_original.values())
    
    return {
        'canonical_set': canonical_set,
        'display_list': display_list
    }

# Real-world asset data with comprehensive aliases
# Note: Raw aliases contain duplicates (e.g., 'simufilam', 'Simufilam', 'SIMUFILAM')
# These are deduplicated using the utility function below
_raw_cassava_aliases = [
    "PTI-125", "PTI 125", "PTI125", "PTI_125",
    "filamin A inhibitor", "FLNA inhibitor", "filamin-A inhibitor",
    "simufilam", "Simufilam", "SIMUFILAM",
    "PTI-125HCl", "PTI-125 HCl"
]

_cassava_alias_data = deduplicate_and_canonicalize_aliases(_raw_cassava_aliases)

CASSAVA_ASSETS = [
    {
        "name": "simufilam",
        "aliases": _cassava_alias_data['display_list'],
        "mechanism": "filamin A inhibitor",
        "mechanism_aliases": deduplicate_and_canonicalize_aliases([
            "filamin A", "FLNA", "filamin-A", "filamin A protein",
            "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid"
        ])['display_list'],
        "indication": "Alzheimer's disease",
        "indication_aliases": deduplicate_and_canonicalize_aliases([
            "Alzheimer Disease", "Alzheimer's Disease", "AD",
            "dementia", "cognitive impairment", "mild cognitive impairment",
            "MCI", "Alzheimer dementia", "senile dementia"
        ])['display_list'],
        "phase": "Phase 3",
        "trial_ids": ["NCT05515666", "NCT04388254", "NCT03838185", "NCT03838186"]
    }
]

# Specific Cassava papers that should be retrieved
EXPECTED_CASSAVA_PAPERS = [
    {
        "pmcid": "PMC10531384",
        "year": 2023,
        "title": "Simufilam Reverses Aberrant Receptor Interactions",
        "description": "Key simufilam mechanism paper"
    },
    {
        "pmcid": "PMC10339288", 
        "year": 2023,
        "title": "Simufilam suppresses overactive mTOR and restores its",
        "description": "Important mTOR pathway paper"
    },
    {
        "pmcid": "PMC6621293",
        "year": 2012,
        "title": "Reducing amyloid-related Alzheimer's disease pathogenesis",
        "description": "Historical amyloid pathogenesis paper"
    },
    {
        "pmcid": None,  # No PMCID available
        "year": 2017,
        "title": "PTI-125 binds and reverses an altered conformation of filamin A",
        "description": "Key filamin A binding paper (Expression of Concern in 2022)"
    },
    {
        "pmcid": None,  # No PMCID available
        "year": 2020,
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients",
        "description": "Clinical biomarker reduction paper"
    },
    {
        "pmcid": None,  # Likely available in Europe PMC
        "year": 2021,
        "title": "Effects of simufilam on CSF biomarkers in Alzheimer's",
        "description": "CSF biomarker effects paper"
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
            "execution_order": ["pubmed", "study_card", "independent_llm_analysis"],  # Include independent LLM analysis
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
                "max_documents_per_trial": 3,  # Limit to 3 documents for comprehensive testing
                "store_json_snapshots": True,
                "llm_timeout_seconds": 60,  # Reduce timeout for testing
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
                "quality_gate": {
                    "min_documents_analyzed": 0,  # Allow 0 documents for testing
                    "min_quotes": 0,  # Allow 0 quotes for testing
                    "min_evidence_spans": 0,  # Allow 0 evidence spans for testing
                    "min_confidence": 0.0,  # Lower confidence threshold for testing
                    "require_method": False,  # Don't require study card for testing
                    "require_results": False,  # Don't require results factsheet for testing
                    "require_patterns": False,  # Don't require pattern detections for testing
                    "min_llm_artifacts": 0  # Allow 0 LLM artifacts for testing
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
            },
            
            # Independent LLM Analysis configuration
            "independent_llm_analysis": {
                "enabled": True,
                "model": "gpt-4o",
                "timeout_seconds": 300,
                "parallel_execution": True,
                "max_concurrent_analyses": 3,
                "retry_attempts": 2,
                "confidence_threshold": 0.7
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
            
            # Phase 4: PubMed Pipeline Testing (detailed results)
            await self._test_pubmed_pipeline()
            
            # Phase 5: Study Card Pipeline Testing (direct test)
            await self._test_study_card_pipeline()
            
            # Phase 6: Validation and Reporting
            await self._validate_results()
            
            # Final reporting
            self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            self.results["errors"].append(f"Test execution failed: {str(e)}")
            raise
        finally:
            # Cleanup - COMMENTED OUT TO PRESERVE DATA FOR INSPECTION
            # await self._cleanup_database()
            logger.info("🧹 Database cleanup SKIPPED - data preserved for inspection")
    
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
                "trial_doc_candidates", "document_links",
                "document_entities", "document_citations",
                "pubmed_meta", "pmc_meta", "documents", "studies",
                "trial_versions", "trials", "company_aliases", "companies",
                "assets", "asset_ownership", "signals", "gates", "scores",
                "catalysts", "labels", "disclosures", "method_cards",
                "results_factsheets", "pattern_detections", "decision_records",
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
                        existing_trial.current_sha256 = f"cassava_test_{trial_data['nct_id']}_{datetime.now(timezone.utc).timestamp()}"
                        
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
                            current_sha256=f"cassava_test_{trial_data['nct_id']}_{datetime.now(timezone.utc).timestamp()}",
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
            # Initialize PubMed components
            retrieval_processor = RetrievalProcessor(self.config["pubmed"])
            abstract_processor = AbstractProcessor(self.config["pubmed"])
            
            # Get the main trial (NCT05515666 - Phase 3) for full pipeline testing
            with session_scope() as session:
                main_trial = session.query(Trial).filter(
                    Trial.nct_id == "NCT05515666"
                ).first()
                
                if not main_trial:
                    raise ValueError("Main trial NCT05515666 not found for PubMed processing")
                
                # Comprehensive search terms for better document retrieval
                raw_asset_names = [
                    "simufilam", "Simufilam", "SIMUFILAM",
                    "PTI-125", "PTI 125", "PTI125", "PTI_125",
                    "PTI-125HCl", "PTI-125 HCl",
                    "filamin A inhibitor", "FLNA inhibitor", "filamin-A inhibitor"
                ]
                
                # Deduplicate and canonicalize aliases
                asset_alias_data = deduplicate_and_canonicalize_aliases(raw_asset_names)
                comprehensive_asset_names = asset_alias_data['display_list']
                
                # Deduplicate and canonicalize indication terms
                raw_indication_terms = [
                    "Alzheimer's disease", "Alzheimer Disease", "Alzheimer's Disease", "AD",
                    "dementia", "cognitive impairment", "mild cognitive impairment", "MCI",
                    "Alzheimer dementia", "senile dementia"
                ]
                indication_alias_data = deduplicate_and_canonicalize_aliases(raw_indication_terms)
                comprehensive_indications = indication_alias_data['display_list']
                
                # Run PubMed pipeline for the main trial only
                logger.info(f"Running PubMed pipeline for main trial {main_trial.nct_id} (ID: {main_trial.trial_id})...")
                logger.info(f"Using comprehensive search terms: {len(comprehensive_asset_names)} assets, {len(comprehensive_indications)} indications")
                logger.debug(f"About to start PubMed pipeline phase")
                
                total_documents = 0
                total_links = 0
                
                # Run retrieval processing
                logger.debug(f"About to call execute_retrieval for trial {main_trial.trial_id}")
                retrieval_result = await retrieval_processor.execute_retrieval(
                    trial_id=main_trial.trial_id,
                    asset_aliases=comprehensive_asset_names,
                    indication_terms=comprehensive_indications,
                    max_results=200,  # Increased from 50 to get more comprehensive results
                    trial_nct=main_trial.nct_id,  # Pass NCT ID for Query D
                    trial_phase=main_trial.phase,
                    company_name="Cassava Sciences, Inc.",
                    company_aliases=["Cassava Sciences", "Pain Therapeutics"]
                )
                
                if not retrieval_result.success:
                    raise ValueError(f"Retrieval failed: {retrieval_result.error_message}")
                
                # Run abstract processing
                processing_result = await abstract_processor.process_documents(
                    documents=retrieval_result.documents,
                    trial_id=main_trial.trial_id,
                    trial_asset="simufilam",
                    trial_indication="Alzheimer's disease",
                    trial_nct=main_trial.nct_id
                )
                
                # Promote trial-doc candidates to document links
                logger.info("Promoting trial-doc candidates to document links...")
                promoted_count = self._promote_candidates_to_links(main_trial.trial_id, main_trial.nct_id)
                logger.info(f"Promoted {promoted_count} trial-doc candidates to document links")
                
                # Count documents from results
                total_documents = retrieval_result.documents_discovered
                total_links = processing_result.documents_processed
                
                # Get simplified persistence metrics for the main trial
                from ncfd.ingest.pubmed.db_service import PubMedDBService
                db_service = PubMedDBService()
                doc_counts = db_service.get_document_counts_by_stage(main_trial.trial_id)
                retrieval_docs_count = doc_counts['total']
                processed_docs_count = doc_counts['processed']
                
                # Count documents created
                doc_count = session.query(Document).count()
                doc_links = session.query(DocumentLink).count()
                
                # Get detailed document metrics from actual documents
                doc_details = []
                documents = session.query(Document).limit(10).all()  # Get first 10 documents for details
                for doc in documents:
                    doc_details.append({
                        "pmid": doc.pmid,
                        "title": (doc.title[:100] + "...") if doc.title and len(doc.title) > 100 else doc.title,
                        "retrieval_tier": "Unknown",  # This would need to be stored separately
                        "policy_engine_passed": False,  # This would need to be stored separately
                        "guardrails_passed": False  # This would need to be stored separately
                    })
                
                # Process pipeline results
                total_documents_processed = total_documents
                total_errors = []
                
                # Check for processing issues
                if processed_docs_count == 0 and retrieval_docs_count > 0:
                    total_errors.append("Abstract processing failed - documents retrieved but none processed")
                
                # Determine status based on actual results
                status = "success"
                if doc_count == 0:
                    status = "failed"
                    total_errors.append("No documents retrieved from PubMed")
                elif processed_docs_count == 0 and retrieval_docs_count > 0:
                    status = "failed"
                    total_errors.append("Documents retrieved but processing failed")
                elif processed_docs_count == 0:
                    status = "success"  # No documents found is acceptable for this test
                
                # Count PubMed documents (documents with source_type='Paper' that are linked to trials)
                pubmed_docs_count = 0
                for link in session.query(DocumentLink).filter(DocumentLink.trial_id == main_trial.trial_id).all():
                    doc = session.query(Document).filter(Document.doc_id == link.doc_id).first()
                    if doc and doc.source_type == "Paper":
                        pubmed_docs_count += 1
                
                self.results["pubmed_processing"] = {
                    "status": status,
                    "main_trial": main_trial.nct_id,
                    "trials_processed": 1,  # Only processing the main trial
                    "documents_created": doc_count,
                    "document_links": doc_links,
                    "pubmed_documents": pubmed_docs_count,
                    "retrieval_documents": retrieval_docs_count,
                    "processed_documents": processed_docs_count,
                    "retrieval_metrics": {},
                    "document_details": doc_details,
                    "pipeline_result": {
                        "success": status == "success",
                        "documents_processed": total_documents_processed,
                        "errors": total_errors,
                        "error_count": len(total_errors),
                        "stages_completed": 2  # Retrieval + Processing stages
                    }
                }
                
                logger.info(f"✅ PubMed processing completed for main trial {main_trial.nct_id}: {doc_count} documents, {doc_links} links")
                logger.info(f"📄 Retrieval documents (raw): {retrieval_docs_count}")
                logger.info(f"📄 Processed documents (filtered): {processed_docs_count}")
                logger.info(f"📊 Retrieval metrics: Available in results")
                
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
                total_patterns = 0
                total_conclusions = 0
                pattern_details = []
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
                    "is_pivotal": trial.is_pivotal,
                    # Add fields expected by LLM prompts
                    "disease": trial.indication or "Unknown",
                    "intervention": trial.intervention_types or "Unknown",
                    "study_type": "RCT"  # Default to RCT
                }
                
                # Run study card pipeline
                logger.info(f"Generating study card for main trial {trial.nct_id} (ID: {trial.trial_id})...")
                result = await study_card_pipeline.execute(trial.trial_id, trial_context)
                
                # Extract pattern details
                pattern_info = []
                for pattern in result.pattern_detections:
                    pattern_info.append({
                        "family_id": getattr(pattern, 'family_id', 'unknown'),
                        "pattern_id": getattr(pattern, 'pattern_id', 'unknown'),
                        "severity": getattr(pattern, 'severity', 'unknown'),
                        "confidence": getattr(pattern, 'confidence', 0.0)
                    })
                
                # Extract conclusion details
                conclusion_info = []
                if result.decision_record:
                    conclusion_info.append({
                        "decision": getattr(result.decision_record, 'decision', 'No decision'),
                        "confidence": getattr(result.decision_record, 'confidence', 0.0),
                        "reasoning": getattr(result.decision_record, 'reasoning', 'No reasoning')[:200] + "..." if getattr(result.decision_record, 'reasoning', None) and len(getattr(result.decision_record, 'reasoning', '')) > 200 else getattr(result.decision_record, 'reasoning', 'No reasoning'),
                        "passed_gates": getattr(result.decision_record, 'passed_gates', 0),
                        "failed_gates": getattr(result.decision_record, 'failed_gates', 0)
                    })
                
                study_card_results.append({
                    "trial_id": trial.trial_id,
                    "nct_id": trial.nct_id,
                    "success": result.success,
                    "document_cards": len(getattr(result, 'document_cards', [])),
                    "evidence_spans": len(getattr(result, 'evidence_spans', [])),
                    "claims": len(getattr(result, 'claims', [])),
                    "study_cards": len(getattr(result, 'study_cards', [])),
                    "results_factsheets": len(getattr(result, 'results_factsheets', [])),
                    "pattern_detections": len(getattr(result, 'pattern_detections', [])),
                    "decision_record": getattr(result, 'decision_record', None) is not None,
                    "patterns": pattern_info,
                    "conclusions": conclusion_info,
                    "errors": result.errors,
                    "warnings": result.warnings
                })
                
                total_patterns += len(result.pattern_detections)
                total_conclusions += 1 if result.decision_record else 0
                pattern_details.extend(pattern_info)
                conclusion_details.extend(conclusion_info)
                
                self.results["study_card_generation"] = {
                    "status": "success",
                    "main_trial": trial.nct_id,
                    "trials_processed": 1,  # Only processing the main trial
                    "total_patterns_generated": total_patterns,
                    "total_conclusions_generated": total_conclusions,
                    "pattern_details": pattern_details,
                    "conclusion_details": conclusion_details,
                    "results": study_card_results
                }
                
                logger.info(f"✅ Study card generation completed for main trial {trial.nct_id}")
                logger.info(f"🎯 Total patterns generated: {total_patterns}")
                logger.info(f"📋 Total conclusions generated: {total_conclusions}")
                
                # Note: Independent LLM Analysis is now handled by the orchestrator
                logger.info("🧠 Independent LLM Analysis is handled by the orchestrator")
                
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
                    "pattern_detections": len(orchestration_result.study_card_result.pattern_detections) if orchestration_result.study_card_result else 0
                },
                "independent_analysis_result": {
                    "success": orchestration_result.independent_analysis_result.get("success", False) if orchestration_result.independent_analysis_result else False,
                    "trials_analyzed": orchestration_result.independent_analysis_result.get("trials_analyzed", 0) if orchestration_result.independent_analysis_result else 0,
                    "successful_analyses": orchestration_result.independent_analysis_result.get("successful_analyses", 0) if orchestration_result.independent_analysis_result else 0
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
        from ncfd.pipeline.orchestrator import OrchestrationOutput
        result = OrchestrationOutput(
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
            logger.info("Step 5: Running study card generation")
            study_card_results = await orchestrator.run_study_card_generation(public_trials)
            result.study_card_result = study_card_results
            
            # Step 6: Independent LLM Analysis
            logger.info("Step 6: Running independent LLM analysis")
            independent_analysis_results = await orchestrator.run_independent_llm_analysis(public_trials)
            result.independent_analysis_result = independent_analysis_results
            
            # Step 7: Update metrics
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
                
                # Run comprehensive checks
                await self._check_expected_papers(session)
                await self._check_pmcid_detection_issues(session)
                await self._check_gate_passes(session)
                await self._check_synthesis_results(session)
                await self._check_evidence_coverage(session)
                
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
    
    async def _check_expected_papers(self, session: Session):
        """Check if expected Cassava papers were retrieved and log warnings for missing ones."""
        logger.info("🔍 Checking for expected Cassava papers...")
        
        missing_papers = []
        found_papers = []
        
        # Get all documents in the database
        all_documents = session.query(Document).all()
        
        for expected_paper in EXPECTED_CASSAVA_PAPERS:
            found = False
            paper_info = {
                "title": expected_paper["title"],
                "year": expected_paper["year"],
                "description": expected_paper["description"],
                "pmcid": expected_paper["pmcid"]
            }
            
            # Check by PMCID if available
            if expected_paper["pmcid"]:
                for doc in all_documents:
                    if doc.pmcid == expected_paper["pmcid"]:
                        found = True
                        paper_info["found_by"] = "pmcid"
                        paper_info["doc_id"] = doc.doc_id
                        paper_info["pmid"] = doc.pmid
                        break
            
            # If not found by PMCID, try title matching
            if not found:
                title_keywords = expected_paper["title"].lower().split()[:3]  # First 3 words
                for doc in all_documents:
                    if doc.title:
                        doc_title_lower = doc.title.lower()
                        if all(keyword in doc_title_lower for keyword in title_keywords):
                            found = True
                            paper_info["found_by"] = "title_match"
                            paper_info["doc_id"] = doc.doc_id
                            paper_info["pmid"] = doc.pmid
                            paper_info["pmcid"] = doc.pmcid
                            break
            
            if found:
                found_papers.append(paper_info)
            else:
                missing_papers.append(paper_info)
        
        # Log warnings for missing papers
        if missing_papers:
            warning_msg = f"⚠️  WARNING: {len(missing_papers)} expected Cassava papers were NOT retrieved:"
            logger.warning(warning_msg)
            self.results["warnings"].append(warning_msg)
            
            for paper in missing_papers:
                paper_warning = f"   • {paper['year']}: {paper['title']} ({paper['description']})"
                if paper['pmcid']:
                    paper_warning += f" [PMCID: {paper['pmcid']}]"
                logger.warning(paper_warning)
                self.results["warnings"].append(paper_warning)
        
        # Log success for found papers
        if found_papers:
            logger.info(f"✅ Found {len(found_papers)} expected Cassava papers:")
            for paper in found_papers:
                logger.info(f"   • {paper['year']}: {paper['title']} (found by {paper['found_by']})")
        
        # Store results
        if "validation_results" not in self.results:
            self.results["validation_results"] = {}
        
        self.results["validation_results"]["expected_papers_check"] = {
            "total_expected": len(EXPECTED_CASSAVA_PAPERS),
            "found": len(found_papers),
            "missing": len(missing_papers),
            "found_papers": found_papers,
            "missing_papers": missing_papers
        }
    
    async def _check_pmcid_detection_issues(self, session: Session):
        """Check for PMCID detection issues and log warnings for papers that should have full text."""
        logger.info("🔍 Checking for PMCID detection issues...")
        
        # Get all documents with PMIDs
        documents_with_pmids = session.query(Document).filter(
            Document.pmid.isnot(None)
        ).all()
        
        if not documents_with_pmids:
            logger.info("No documents with PMIDs found to check PMCID detection")
            return
        
        # Known PMIDs that should have PMCID but might be marked as has_full_text=False
        # Based on the user's spot-check results
        known_pmcid_papers = {
            "40141124": "PMC11942311",
            "37762230": "PMC10530843", 
            "37457922": "PMC10339288",
            "22815492": "PMC6621293",
            "33188449": "PMC7664001",
            "32075941": "PMC7342663",
            "36457865": "PMC9706102",
            "39239266": "PMC11543719"
        }
        
        pmcid_detection_issues = []
        
        for doc in documents_with_pmids:
            pmid = doc.pmid
            if pmid in known_pmcid_papers:
                expected_pmcid = known_pmcid_papers[pmid]
                
                # Check if PMCID is missing or incorrect
                if not doc.pmcid or doc.pmcid != expected_pmcid:
                    issue = {
                        "pmid": pmid,
                        "title": doc.title or "Unknown title",
                        "expected_pmcid": expected_pmcid,
                        "actual_pmcid": doc.pmcid,
                        "issue_type": "missing_pmcid" if not doc.pmcid else "incorrect_pmcid"
                    }
                    pmcid_detection_issues.append(issue)
                    
                    # Log warning
                    warning_msg = f"⚠️  PMCID DETECTION ISSUE: PMID {pmid} should have PMCID {expected_pmcid} but has {doc.pmcid or 'None'}"
                    logger.warning(warning_msg)
                    self.results["warnings"].append(warning_msg)
        
        # Also check for documents that have PMCID but are marked as not having full text
        documents_with_pmcid = session.query(Document).filter(
            Document.pmcid.isnot(None),
            Document.pmcid != ""
        ).all()
        
        for doc in documents_with_pmcid:
            # Check if document has full text content
            from ncfd.db.models import DocumentText
            doc_text = session.query(DocumentText).filter(
                DocumentText.doc_id == doc.doc_id
            ).first()
            
            has_full_text = bool(doc_text and doc_text.fulltext_text and len(doc_text.fulltext_text.strip()) > 0)
            
            if not has_full_text:
                issue = {
                    "pmid": doc.pmid,
                    "pmcid": doc.pmcid,
                    "title": doc.title or "Unknown title",
                    "issue_type": "has_pmcid_but_no_full_text"
                }
                pmcid_detection_issues.append(issue)
                
                # Log warning
                warning_msg = f"⚠️  FULL TEXT ISSUE: PMID {doc.pmid} has PMCID {doc.pmcid} but no full text content retrieved"
                logger.warning(warning_msg)
                self.results["warnings"].append(warning_msg)
        
        # Store results
        if "validation_results" not in self.results:
            self.results["validation_results"] = {}
        
        self.results["validation_results"]["pmcid_detection_check"] = {
            "total_documents_checked": len(documents_with_pmids),
            "documents_with_pmcid": len(documents_with_pmcid),
            "pmcid_detection_issues": len(pmcid_detection_issues),
            "issues": pmcid_detection_issues
        }
        
        if pmcid_detection_issues:
            logger.warning(f"Found {len(pmcid_detection_issues)} PMCID detection issues")
        else:
            logger.info("No PMCID detection issues found")
    
    async def _check_gate_passes(self, session: Session):
        """Check if any gates passed and log warnings."""
        logger.info("🚪 Checking for gate passes...")
        
        # Check for gate passes using raw SQL to avoid model/schema mismatches
        try:
            # Check for fired gates using raw SQL (based on actual DB schema)
            fired_gates_result = session.execute(text("""
                SELECT g_id, rationale_text, trial_id 
                FROM gates 
                WHERE fired_bool = true
            """)).fetchall()
            
            # Check for pattern detections using raw SQL
            # Note: severity is stored as integer (0=grey, 1=yellow, 2=amber, 3=red)
            pattern_detections_result = session.execute(text("""
                SELECT family_id, pattern_id, severity, confidence, rationale
                FROM pattern_detections 
                WHERE severity IN (1, 2, 3)
            """)).fetchall()
            
            total_passed = len(fired_gates_result) + len(pattern_detections_result)
            
            if total_passed > 0:
                warning_msg = f"⚠️  WARNING: {total_passed} patterns detected ({len(fired_gates_result)} fired gates, {len(pattern_detections_result)} pattern detections) - this may indicate risk patterns in the trial"
                logger.warning(warning_msg)
                self.results["warnings"].append(warning_msg)
                
                # Log fired gates
                for gate_row in fired_gates_result:
                    g_id, rationale_text, trial_id = gate_row
                    gate_warning = f"   • Fired Gate {g_id} (Trial {trial_id}): {rationale_text[:50]}..." if rationale_text else f"   • Fired Gate {g_id} (Trial {trial_id}): No rationale"
                    logger.warning(gate_warning)
                    self.results["warnings"].append(gate_warning)
                
                # Log passed assessments
                for assessment_row in passed_assessments_result:
                    gate_id, status, confidence, rationale = assessment_row
                    assessment_warning = f"   • Passed Assessment {gate_id}: Status={status}, Confidence={confidence:.2f}" if confidence else f"   • Passed Assessment {gate_id}: Status={status}"
                    logger.warning(assessment_warning)
                    self.results["warnings"].append(assessment_warning)
            else:
                logger.info("✅ No gates passed - gate criteria appear appropriately strict")
            
            # Store results
            if "validation_results" not in self.results:
                self.results["validation_results"] = {}
            
            self.results["validation_results"]["gate_passes_check"] = {
                "total_fired_gates": len(fired_gates_result),
                "total_passed_assessments": len(passed_assessments_result),
                "total_passed": total_passed,
                "fired_gates": [
                    {
                        "g_id": gate_row[0],
                        "trial_id": gate_row[2],
                        "rationale": gate_row[1][:100] + "..." if gate_row[1] and len(gate_row[1]) > 100 else gate_row[1]
                    } for gate_row in fired_gates_result
                ],
                "passed_assessments": [
                    {
                        "gate_id": assessment_row[0],
                        "status": assessment_row[1],
                        "confidence": assessment_row[2],
                        "rationale": str(assessment_row[3])[:100] + "..." if assessment_row[3] and len(str(assessment_row[3])) > 100 else str(assessment_row[3])
                    } for assessment_row in passed_assessments_result
                ]
            }
            
        except Exception as e:
            logger.warning(f"⚠️  Gate pass check failed: {str(e)}")
            self.results["warnings"].append(f"Gate pass check failed: {str(e)}")
    
    async def _check_synthesis_results(self, session: Session):
        """Check synthesis results and log warnings for positive results."""
        logger.info("🧠 Checking synthesis results...")
        
        # Check independent LLM analysis results (from orchestrator)
        if "orchestrator_testing" in self.results:
            orchestrator_results = self.results["orchestrator_testing"]
            indep_result = orchestrator_results.get("independent_analysis_result", {})
            
            if indep_result.get("success", False):
                logger.info("✅ Independent LLM analysis executed successfully via orchestrator")
                # Note: Detailed analysis results would be in the orchestrator's independent_analysis_result
                # but we don't have access to the detailed risk assessment here
            else:
                logger.warning("⚠️  Independent LLM analysis not executed via orchestrator")
        
        # Check study card decision records
        if "study_card_generation" in self.results:
            study_cards = self.results["study_card_generation"]
            conclusion_details = study_cards.get("conclusion_details", [])
            
            for conclusion in conclusion_details:
                decision = conclusion.get("decision", "").lower()
                confidence = conclusion.get("confidence", 0.0)
                
                # Check for positive decisions
                positive_decisions = [
                    "approve", "positive", "favorable", "proceed", 
                    "recommend", "support", "endorse"
                ]
                
                is_positive_decision = any(pos_word in decision for pos_word in positive_decisions)
                
                if is_positive_decision and confidence > 0.6:
                    warning_msg = f"⚠️  WARNING: Study card decision appears POSITIVE (Decision: {decision}, Confidence: {confidence:.2f}) - verify this aligns with expected Cassava concerns"
                    logger.warning(warning_msg)
                    self.results["warnings"].append(warning_msg)
        
        # Store results
        if "validation_results" not in self.results:
            self.results["validation_results"] = {}
        
        self.results["validation_results"]["synthesis_results_check"] = {
            "checked_llm_analysis": "orchestrator_testing" in self.results and self.results["orchestrator_testing"].get("independent_analysis_result", {}).get("success", False),
            "checked_study_cards": "study_card_generation" in self.results,
            "warnings_generated": len([w for w in self.results["warnings"] if "POSITIVE" in w])
        }
    
    async def _check_evidence_coverage(self, session: Session):
        """Check evidence section coverage and log warnings for low coverage."""
        logger.info("📊 Checking evidence section coverage...")
        
        coverage_warnings = []
        
        # Check document coverage by source type
        try:
            from ncfd.db.models import DocumentLink
            
            # Get main trial
            main_trial = session.query(Trial).filter(Trial.nct_id == "NCT05515666").first()
            if not main_trial:
                logger.warning("Main trial not found for coverage check")
                return
            
            # Count documents by source type for the main trial
            trial_links = session.query(DocumentLink).filter(
                DocumentLink.trial_id == main_trial.trial_id
            ).all()
            
            source_type_counts = {}
            total_docs = 0
            
            for link in trial_links:
                doc = session.query(Document).filter(Document.doc_id == link.doc_id).first()
                if doc:
                    source_type = doc.source_type or "Unknown"
                    source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
                    total_docs += 1
            
            # Check for low coverage in key evidence sections
            if total_docs < 5:
                warning_msg = f"⚠️  WARNING: Low document coverage - only {total_docs} documents found for main trial {main_trial.nct_id}"
                logger.warning(warning_msg)
                coverage_warnings.append(warning_msg)
                self.results["warnings"].append(warning_msg)
                
                context_msg = f"   Context: Expected comprehensive literature coverage for Phase 3 Alzheimer's trial - consider expanding search terms or date ranges"
                logger.warning(context_msg)
                coverage_warnings.append(context_msg)
                self.results["warnings"].append(context_msg)
            
            # Check source type diversity
            if len(source_type_counts) < 2:
                warning_msg = f"⚠️  WARNING: Limited source type diversity - only {list(source_type_counts.keys())} found"
                logger.warning(warning_msg)
                coverage_warnings.append(warning_msg)
                self.results["warnings"].append(warning_msg)
            
            # Check for PubMed papers specifically
            pubmed_count = source_type_counts.get("Paper", 0)
            if pubmed_count < 3:
                warning_msg = f"⚠️  WARNING: Low PubMed paper coverage - only {pubmed_count} papers found (expected more for comprehensive literature review)"
                logger.warning(warning_msg)
                coverage_warnings.append(warning_msg)
                self.results["warnings"].append(warning_msg)
                
                context_msg = f"   Context: Simufilam/PTI-125 has extensive literature including mechanism, preclinical, and clinical studies - low paper count may indicate retrieval issues"
                logger.warning(context_msg)
                coverage_warnings.append(context_msg)
                self.results["warnings"].append(context_msg)
            
            # Log coverage summary
            logger.info(f"📊 Evidence coverage summary:")
            logger.info(f"   • Total documents: {total_docs}")
            logger.info(f"   • Source types: {source_type_counts}")
            logger.info(f"   • PubMed papers: {pubmed_count}")
            
            # Store results
            if "validation_results" not in self.results:
                self.results["validation_results"] = {}
            
            self.results["validation_results"]["evidence_coverage_check"] = {
                "total_documents": total_docs,
                "source_type_counts": source_type_counts,
                "pubmed_papers": pubmed_count,
                "coverage_warnings": len(coverage_warnings),
                "warnings": coverage_warnings
            }
            
        except Exception as e:
            logger.warning(f"⚠️  Evidence coverage check failed: {str(e)}")
            self.results["warnings"].append(f"Evidence coverage check failed: {str(e)}")
    
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
        if "study_card_generation" in self.results and self.results["study_card_generation"].get("status") == "success":
            study_cards = self.results["study_card_generation"]
            print(f"\n📋 Study Card Generation Metrics:")
            print(f"   • Trials processed: {study_cards.get('trials_processed', 0)}")
            print(f"   • Total patterns generated: {study_cards.get('total_patterns_generated', 0)}")
            print(f"   • Total conclusions generated: {study_cards.get('total_conclusions_generated', 0)}")
            
            # Show pattern details
            if study_cards.get('pattern_details'):
                print(f"   • Pattern details:")
                for i, pattern in enumerate(study_cards['pattern_details'][:3], 1):
                    print(f"     {i}. {pattern.get('family_id', 'Unknown')}/{pattern.get('pattern_id', 'Unknown')}: {pattern.get('severity', 'Unknown')}")
                    print(f"        Confidence: {pattern.get('confidence', 0.0):.2f}")
            
            # Show conclusion details
            if study_cards.get('conclusion_details'):
                print(f"   • Conclusion details:")
                for i, conclusion in enumerate(study_cards['conclusion_details'][:2], 1):
                    print(f"     {i}. Decision: {conclusion.get('decision', 'No decision')}")
                    print(f"        Confidence: {conclusion.get('confidence', 0.0):.2f}")
                    print(f"        Passed gates: {conclusion.get('passed_gates', 0)}")
                    print(f"        Failed gates: {conclusion.get('failed_gates', 0)}")
                    print(f"        Reasoning: {conclusion.get('reasoning', 'No reasoning')[:100]}...")
        
        # Independent LLM Analysis metrics (from orchestrator)
        if "orchestrator_testing" in self.results and self.results["orchestrator_testing"].get("status") == "success":
            orchestrator_results = self.results["orchestrator_testing"]
            indep_result = orchestrator_results.get("independent_analysis_result", {})
            
            if indep_result.get("success", False):
                print(f"\n🧠 Independent LLM Analysis Metrics (via Orchestrator):")
                print(f"   • Trials analyzed: {indep_result.get('trials_analyzed', 0)}")
                print(f"   • Successful analyses: {indep_result.get('successful_analyses', 0)}")
                print(f"   • Status: {'✅ Success' if indep_result.get('success') else '❌ Failed'}")
            else:
                print(f"\n🧠 Independent LLM Analysis Metrics (via Orchestrator):")
                print(f"   • Status: ❌ Not executed or failed")
                print(f"   • Reason: Independent analysis not included in orchestrator execution")
        
        # Comprehensive validation checks
        if "validation_results" in self.results and self.results["validation_results"].get("status") == "success":
            validation = self.results["validation_results"]
            print(f"\n🔍 Comprehensive Validation Checks:")
            
            # Expected papers check
            if "expected_papers_check" in validation:
                papers_check = validation["expected_papers_check"]
                print(f"   • Expected Papers Check:")
                print(f"     - Expected: {papers_check['total_expected']}")
                print(f"     - Found: {papers_check['found']}")
                print(f"     - Missing: {papers_check['missing']}")
                
                if papers_check['missing'] > 0:
                    print(f"     - Missing papers:")
                    for paper in papers_check['missing_papers'][:3]:  # Show first 3
                        print(f"       • {paper['year']}: {paper['title']}")
            
            # Gate passes check
            if "gate_passes_check" in validation:
                gates_check = validation["gate_passes_check"]
                print(f"   • Gate Passes Check:")
                print(f"     - Total passed: {gates_check['total_passed']}")
                print(f"     - Fired gates: {gates_check['total_fired_gates']}")
                print(f"     - Passed assessments: {gates_check['total_passed_assessments']}")
                
                if gates_check['total_passed'] > 0:
                    print(f"     - Fired gates:")
                    for gate in gates_check['fired_gates'][:3]:  # Show first 3
                        print(f"       • {gate['g_id']}: {gate['rationale']}")
                    
                    print(f"     - Passed assessments:")
                    for assessment in gates_check['passed_assessments'][:3]:  # Show first 3
                        print(f"       • {assessment['gate_id']}: {assessment['status']} (confidence: {assessment['confidence']:.2f})")
            
            # Synthesis results check
            if "synthesis_results_check" in validation:
                synthesis_check = validation["synthesis_results_check"]
                print(f"   • Synthesis Results Check:")
                print(f"     - Warnings generated: {synthesis_check['warnings_generated']}")
                print(f"     - LLM analysis checked: {synthesis_check['checked_llm_analysis']}")
                print(f"     - Study cards checked: {synthesis_check['checked_study_cards']}")
            
            # Evidence coverage check
            if "evidence_coverage_check" in validation:
                coverage_check = validation["evidence_coverage_check"]
                print(f"   • Evidence Coverage Check:")
                print(f"     - Total documents: {coverage_check['total_documents']}")
                print(f"     - PubMed papers: {coverage_check['pubmed_papers']}")
                print(f"     - Coverage warnings: {coverage_check['coverage_warnings']}")
                print(f"     - Source types: {coverage_check['source_type_counts']}")
        
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
    
    def _promote_candidates_to_links(self, trial_id: int, nct_id: str) -> int:
        """Promote trial-doc candidates to document links."""
        promoted_count = 0
        
        with session_scope() as session:
            # Get all trial-doc candidates for this trial
            candidates = session.query(TrialDocCandidate).filter(
                TrialDocCandidate.trial_id == trial_id
            ).all()
            
            # Get trial info for company_id
            trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
            if not trial:
                logger.warning(f"Trial {trial_id} not found")
                return 0
            
            company_id = trial.sponsor_company_id
            
            for candidate in candidates:
                # Check if document link already exists
                existing_link = session.query(DocumentLink).filter(
                    DocumentLink.doc_id == candidate.doc_id,
                    DocumentLink.trial_id == trial_id
                ).first()
                
                if existing_link:
                    continue  # Already linked
                
                # Create document link
                try:
                    link = DocumentLink(
                        doc_id=candidate.doc_id,
                        nct_id=nct_id,
                        trial_id=trial_id,
                        asset_id=None,  # We don't have asset mapping in this test
                        company_id=company_id,
                        link_type='trial_document',
                        confidence=0.8,  # Default confidence
                        heuristics={'stage': candidate.stage},
                        evidence_json={'promoted_from_candidate': True}
                    )
                    session.add(link)
                    promoted_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to create link for doc {candidate.doc_id}: {e}")
            
            session.commit()
        
        return promoted_count

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
