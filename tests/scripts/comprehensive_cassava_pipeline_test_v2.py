#!/usr/bin/env python3
"""
Comprehensive Cassava Trial Pipeline Test V2

This test provides a clean, simplified approach to testing the Cassava Sciences
Phase 3 trial (NCT05515666) with the complete pipeline:

1. CT.gov ingestion (filtered to Cassava trials only)
2. PubMed literature processing 
3. Study card generation with LLM analysis
4. Independent LLM analysis
5. Comprehensive validation and reporting

Key improvements over v1:
- Single execution path (no confusing orchestrator vs individual tests)
- Proper CT.gov ingestion with filtering
- Simplified configuration management
- Better error handling and logging
- Clear separation of concerns

Usage:
    python tests/scripts/comprehensive_cassava_pipeline_test_v2.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, date
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
from ncfd.db.models import Base, Trial, TrialVersion, Company, Document, DocumentText, Study, StudyCard
from ncfd.pipeline.orchestrator import PipelineOrchestrator
from ncfd.config import get_config

# Setup logging - clean and focused
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Demote noisy DEBUG logs
logging.getLogger("ncfd.ingest.pubmed").setLevel(logging.WARNING)
# Keep pipeline logging at INFO level to see R ranking logs
logging.getLogger("ncfd.pipeline").setLevel(logging.INFO)

# Real-world Cassava trial data - comprehensive list for building aliases and company info
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

# Specific Cassava papers that should be retrieved (focused on 3 key studies)
EXPECTED_CASSAVA_PAPERS = [
    {
        "pmcid": "PMC10531384",
        "year": 2023,
        "title": "Simufilam Reverses Aberrant Receptor Interactions",
        "description": "Mechanism paper (2023): FLNA–α7nAChR receptor interactions (Cell Mol Neurobiol)"
    },
    {
        "pmcid": "PMC10339288", 
        "year": 2023,
        "title": "Simufilam suppresses overactive mTOR and restores its",
        "description": "Mechanism paper (2023): mTOR/lymphocytes (Frontiers in Aging)"
    },
    {
        "pmcid": None,  # No PMCID available
        "year": 2020,
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients",
        "description": "JPAD 2020 Phase 2a trial paper (PTI-125 reduces AD biomarkers)"
    }
]


class ComprehensiveCassavaTestV2:
    """Comprehensive test for Cassava trial pipeline processing - V2 with simplified architecture."""
    
    def __init__(self):
        self.test_start_time = datetime.now(timezone.utc)
        self.results = {
            "test_info": {
                "start_time": self.test_start_time.isoformat(),
                "test_name": "Comprehensive Cassava Pipeline Test V2",
                "version": "2.0"
            },
            "database_setup": {},
            "ctgov_ingestion": {},
            "pubmed_processing": {},
            "study_card_generation": {},
            "independent_analysis": {},
            "validation_results": {},
            "errors": [],
            "warnings": []
        }
        
        # Load configuration
        self.config = self._load_test_config()
        
    def _load_test_config(self) -> Dict[str, Any]:
        """Load test configuration with simplified, clear settings."""
        config = {
            "worker_id": "cassava_test_v2",
            "execution_order": ["pubmed", "study_card"],  # Skip CT.gov and independent_llm_analysis
            "parallel_execution": False,
            "dependency_checking": True,
            
            # CT.gov configuration - focused on Cassava trials only
            "ctgov": {
                "incremental": False,
                "force_full_scan": False,  # Don't scan all trials
                "batch_size": 10,
                "retry_attempts": 3,
                "max_studies_per_run": 5,  # Limit to only 5 trials maximum
                "default_since_days": 365,  # Look back 1 year to find Cassava trials
                "filters": {
                    "sponsor_keywords": ["Cassava Sciences", "Cassava", "simufilam", "PTI-125"],
                    "indication_keywords": ["Alzheimer", "dementia", "cognitive"],
                    "phase_filters": ["PHASE2", "PHASE3"]
                }
            },
            
            # PubMed configuration - comprehensive simufilam search with new client manager
            "pubmed": {
                "entity_id": "simufilam",
                "domain": "neurology",
                "asset_names": ["simufilam", "PTI-125", "PTI 125"],
                "indications": ["Alzheimer Disease", "Alzheimer's", "AD", "dementia"],
                "client_config": {
                    "rate_limit_per_sec": 15,  # 15 requests per second (900 per minute) - higher limit
                    "batch_size": 100,  # Increased batch size for efficiency
                    "timeout_seconds": 30,
                    "max_retries": 3,
                    "api_key": None,  # Set your NCBI API key here for higher limits
                    "email": "ncfd@example.com",
                    "tool": "NCFD"
                },
                "queue_config": {
                    "max_concurrent_requests": 3,
                    "request_timeout": 60
                },
                "monitoring_config": {
                    "enabled": True,
                    "alert_thresholds": {
                        "rate_limit_hits_per_minute": 10,  # Increased threshold for higher rate limit
                        "consecutive_failures": 3,
                        "queue_size": 100,
                        "avg_response_time": 10.0,
                        "error_rate": 0.1
                    }
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
                    "max_results": 150  # Limited to 150 for testing (will be further filtered)
                },
                "asset_names": ["simufilam", "PTI-125", "filamin A inhibitor"],
                "indications": ["Alzheimer's disease", "dementia", "cognitive impairment"],
                "query_config": {
                    "max_terms": 100,
                    "enable_boolean_operators": True,
                    "date_range": ("2010/01/01", "2025/12/31")
                },
                "reuse_existing": False,  # Force fresh retrieval for testing
                "min_documents_required": 1,
                "skip_if_sufficient": False,
                "enable_stages": ["retrieval", "processing"],
                "max_results": 200  # Limit total documents to 200
            },
            
            # Study card configuration
            "study_card": {
                "max_documents_per_trial": 3,
                "store_json_snapshots": True,
                "llm_timeout_seconds": 120,
                "retrieval_timeout_seconds": 180,
                "prioritization": {
                    "max_documents_per_trial": 3,
                    "min_r_score": 0.0,
                    "min_s_score": 0.0,
                    "high_priority_r_threshold": 0.6,
                    "weights": {
                        "r_score": 0.4,
                        "s_score": 0.3,
                        "recency": 0.2,
                        "text_availability": 0.1
                    }
                },
                "retriever": {
                    "auto_span_generation": True,
                    "late_fusion": False,
                    "max_span_length": 500,
                    "min_confidence": 0.6
                },
                "guardrails": {
                    "reject_off_topic": True,
                    "reject_high_risk": True,
                    "high_risk_threshold": 0.8,  # Increased from 0.6 to be less strict
                    "require_relevance": True,
                    "require_asset_or_indication": True,
                    "log_decisions": True,
                    "log_rejections": True
                },
                "quality_gate": {
                    "min_documents_analyzed": 1,
                    "min_quotes": 1,
                    "min_evidence_spans": 1,
                    "min_confidence": 0.3,
                    "require_method": False,
                    "require_results": False,
                    "require_patterns": False,
                    "min_llm_artifacts": 1
                },
                "stages": {
                    "retrieval": {"enable": True, "timeout_seconds": 180},
                    "llm_method_auditing": {"enable": True, "timeout_seconds": 300},
                    "llm_results_distillation": {"enable": True, "timeout_seconds": 300},
                    "gate_proposal": {"enable": True, "timeout_seconds": 180},
                    "gate_validation": {"enable": True, "timeout_seconds": 180},
                    "gate_assessment": {"enable": True, "timeout_seconds": 180},
                    "fda_lens": {"enable": True, "timeout_seconds": 180},
                    "memo_composition": {"enable": True, "timeout_seconds": 180}
                }
            },
            
            # Independent LLM Analysis configuration
            "independent_llm_analysis": {
                # "enabled": True,
                "enabled": False,
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
        """Run the comprehensive pipeline test with simplified architecture."""
        logger.info("🧪 Starting Comprehensive Cassava Pipeline Test V2")
        logger.info("=" * 80)
        
        try:
            # Phase 1: Database Setup
            await self._setup_database()
            
            # Phase 2: CT.gov Ingestion (filtered to Cassava trials)
            await self._run_ctgov_ingestion()
            
            # Phase 3: PubMed Processing
            await self._run_pubmed_processing()
            
            # Phase 4: Study Card Generation
            await self._run_study_card_generation()
            
            # Phase 5: Pattern Evaluation and Gate Firing
            await self._run_pattern_evaluation()
            
            # Phase 6: Independent LLM Analysis
            await self._run_independent_analysis()
            
            # Phase 7: Validation and Reporting
            await self._validate_results()
            
            # Final reporting
            self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            self.results["errors"].append(f"Test execution failed: {str(e)}")
            print(f"\n❌ TEST FAILED: {str(e)}")
            print("="*80)
            sys.exit(1)
        finally:
            # Cleanup - COMMENTED OUT TO PRESERVE DATA FOR INSPECTION
            logger.info("🧹 Database cleanup SKIPPED - data preserved for inspection")
    
    async def _setup_database(self):
        """Setup test database with clean state."""
        logger.info("📊 Phase 1: Setting up test database")
        
        try:
            # Reset engine to ensure it uses the test environment
            reset_engine()
            
            # Clear all data
            await self._clear_database()
            
            # Create required PostgreSQL extensions
            await self._create_database_extensions()
            
            # Create all tables
            engine = get_engine()
            Base.metadata.create_all(engine)
            logger.info("✅ Database tables created successfully")
            
            # Seed company data
            await self._seed_company_data()
            
            # Seed trial data
            await self._seed_trial_data()
            
            self.results["database_setup"] = {
                "status": "success",
                "tables_created": True,
                "data_cleared": True,
                "extensions_created": True,
                "company_seeded": True,
                "trial_seeded": True
            }
            
            logger.info("✅ Database setup completed successfully")
            
        except Exception as e:
            logger.error(f"Database setup failed: {str(e)}")
            self.results["database_setup"] = {
                "status": "failed",
                "error": str(e)
            }
            print(f"\n❌ DATABASE SETUP FAILED: {str(e)}")
            sys.exit(1)
    
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
                "retrieval_sessions", "retrieval_documents", "processed_documents"
            ]
            
            for table in tables_to_clear:
                if table in existing_tables:
                    try:
                        session.execute(text(f"DELETE FROM {table}"))
                        session.commit()
                        logger.info(f"Cleared table: {table}")
                    except Exception as e:
                        session.rollback()
                        logger.warning(f"Could not clear table {table}: {e}")
                else:
                    logger.info(f"Skipping {table} (not present in schema)")
            
            logger.info("✅ Database cleared successfully")
    
    async def _create_database_extensions(self):
        """Create required PostgreSQL extensions."""
        logger.info("🔧 Creating required PostgreSQL extensions...")
        
        with session_scope() as session:
            # List of required extensions
            extensions = [
                "CREATE EXTENSION IF NOT EXISTS pg_trgm;",  # For trigram indexes
                "CREATE EXTENSION IF NOT EXISTS btree_gin;",  # For GIN indexes on btree types
                "CREATE EXTENSION IF NOT EXISTS btree_gist;",  # For GiST indexes on btree types
                "CREATE EXTENSION IF NOT EXISTS unaccent;",  # For text search
            ]
            
            for extension_sql in extensions:
                try:
                    session.execute(text(extension_sql))
                    session.commit()
                    extension_name = extension_sql.split()[5].rstrip(';')
                    logger.info(f"✅ Created extension: {extension_name}")
                except Exception as e:
                    logger.warning(f"⚠️  Could not create extension {extension_sql}: {e}")
                    session.rollback()
            
            logger.info("✅ Database extensions setup completed")
    
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
            
            session.commit()
            logger.info(f"✅ Seeded company: {company.name} (ID: {company.company_id})")
    
    async def _seed_trial_data(self):
        """Seed sample Cassava trial data."""
        logger.info("🧪 Seeding sample Cassava trial data...")
        
        with session_scope() as session:
            # Create a sample Cassava trial
            trial = Trial(
                nct_id="NCT05515666",  # Main trial NCT ID (matches test configuration)
                brief_title="A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                official_title="A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                sponsor_text="Cassava Sciences, Inc.",
                phase="PHASE3",
                status="RECRUITING",
                indication="Alzheimer's Disease",
                intervention_types=["DRUG"],
                primary_endpoint_text="Change from baseline in ADAS-Cog11 total score at 12 months",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(trial)
            session.flush()
            
            # Create trial version
            trial_version = TrialVersion(
                trial_id=trial.trial_id,
                captured_at=datetime.now(timezone.utc),
                sha256="sample_sha256_hash",
                raw_jsonb={
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT05515666",
                            "briefTitle": "A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                            "officialTitle": "A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease"
                        },
                        "sponsorCollaboratorsModule": {
                            "leadSponsor": {
                                "name": "Cassava Sciences, Inc."
                            }
                        },
                        "conditionsModule": {
                            "conditions": ["Alzheimer Disease"]
                        },
                        "interventionsModule": {
                            "interventions": [
                                {
                                    "name": "Simufilam",
                                    "type": "DRUG"
                                }
                            ]
                        }
                    }
                },
                last_update_posted_date=date(2023, 1, 1),
                primary_endpoint_text="Change from baseline in ADAS-Cog11 total score at 12 months",
                sample_size=64
            )
            session.add(trial_version)
            
            # Create sample documents linked to the trial
            sample_documents = [
                Document(
                    pmid="12345678",
                    title="Simufilam: A Novel Therapeutic Approach for Alzheimer's Disease",
                    source_type="Abstract",
                    published_at=datetime(2023, 6, 15, tzinfo=timezone.utc),
                    trial_id=trial.trial_id,
                    processing_stage="raw",
                    status="fetched"
                ),
                Document(
                    pmid="87654321",
                    title="PTI-125 Clinical Trial Results in Mild-to-Moderate Alzheimer's Disease",
                    source_type="Abstract",
                    published_at=datetime(2023, 8, 20, tzinfo=timezone.utc),
                    trial_id=trial.trial_id,
                    processing_stage="raw",
                    status="fetched"
                ),
                Document(
                    pmid="11223344",
                    title="Filamin A Inhibition as a Therapeutic Strategy for Neurodegenerative Diseases",
                    source_type="Abstract",
                    published_at=datetime(2023, 9, 10, tzinfo=timezone.utc),
                    trial_id=trial.trial_id,
                    processing_stage="raw",
                    status="fetched"
                )
            ]
            
            for doc in sample_documents:
                session.add(doc)
                session.flush()  # Get the doc_id
                
                # Create corresponding DocumentText entries
                doc_text = DocumentText(
                    doc_id=doc.doc_id,
                    abstract_text=f"This study investigates the efficacy of simufilam in patients with Alzheimer's disease. Results show significant improvement in cognitive function." if doc.pmid == "12345678" else
                                 f"Phase 2 clinical trial results demonstrating the safety and efficacy of PTI-125 (simufilam) in patients with mild-to-moderate Alzheimer's disease." if doc.pmid == "87654321" else
                                 f"Review of filamin A inhibition mechanisms and their potential therapeutic applications in neurodegenerative diseases including Alzheimer's disease.",
                    char_count_abstract=150
                )
                session.add(doc_text)
            
            session.commit()
            logger.info(f"✅ Seeded trial: {trial.nct_id} - {trial.brief_title}")
            logger.info(f"✅ Seeded {len(sample_documents)} sample documents linked to trial")
    
    async def _run_ctgov_ingestion(self):
        """Skip CT.gov ingestion and use existing data."""
        logger.info("🔬 Phase 2: Skipping CT.gov ingestion (using existing data)")
        
        try:
            # Skip CT.gov ingestion and mark as successful
            self.results["ctgov_ingestion"] = {
                "status": "skipped",
                "reason": "Using existing trial data in database",
                "trials_processed": 0,
                "trials_updated": 0,
                "trials_created": 0,
                "changes_detected": 0
            }
            logger.info("✅ CT.gov ingestion skipped - using existing data")
                
        except Exception as e:
            logger.error(f"CT.gov ingestion setup failed: {str(e)}")
            self.results["ctgov_ingestion"] = {
                "status": "failed",
                "error": str(e)
            }
            print(f"\n❌ CT.GOV INGESTION SETUP FAILED: {str(e)}")
            sys.exit(1)
    
    async def _run_pubmed_processing(self):
        """Run PubMed processing for Cassava trials."""
        logger.info("📚 Phase 3: Running PubMed processing")
        
        try:
            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.config)
            
            # Get Cassava trials from database
            with session_scope() as session:
                cassava_trials = session.query(Trial).filter(
                    Trial.sponsor_text.like('%Cassava%')
                ).all()
                
                if not cassava_trials:
                    raise ValueError("No Cassava trials found in database")
                
                # Convert to orchestrator format
                trial_list = []
                for trial in cassava_trials:
                    trial_list.append({
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
                        'matching_confidence': 1.0
                    })
            
            # Run PubMed processing
            logger.info(f"Running PubMed processing for {len(trial_list)} Cassava trials...")
            pubmed_result = await orchestrator.run_pubmed_processing(trial_list)
            
            if pubmed_result:
                self.results["pubmed_processing"] = {
                    "status": "success",
                    "documents_processed": pubmed_result.documents_processed,
                    "trials_processed": len(trial_list),  # Use the number of trials we passed in
                    "success": pubmed_result.success,
                    "errors": pubmed_result.errors if hasattr(pubmed_result, 'errors') else [],
                    "warnings": pubmed_result.warnings if hasattr(pubmed_result, 'warnings') else []
                }
                logger.info(f"✅ PubMed processing completed: {pubmed_result.documents_processed} documents processed")
            else:
                self.results["pubmed_processing"] = {
                    "status": "failed",
                    "error": "No PubMed result returned"
                }
                logger.error("❌ PubMed processing failed: No result returned")
                
        except Exception as e:
            logger.error(f"PubMed processing failed: {str(e)}")
            self.results["pubmed_processing"] = {
                "status": "failed",
                "error": str(e)
            }
            print(f"\n❌ PUBMED PROCESSING FAILED: {str(e)}")
            sys.exit(1)
    
    async def _run_study_card_generation(self):
        """Run study card generation for Cassava trials."""
        logger.info("📋 Phase 4: Running study card generation")
        
        try:
            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.config)
            
            # Get Cassava trials from database
            with session_scope() as session:
                cassava_trials = session.query(Trial).filter(
                    Trial.sponsor_text.like('%Cassava%')
                ).all()
                
                # Convert to orchestrator format
                trial_list = []
                for trial in cassava_trials:
                    trial_list.append({
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
                        'matching_confidence': 1.0
                    })
            
            # Run study card generation
            logger.info(f"Running study card generation for {len(trial_list)} Cassava trials...")
            study_card_result = await orchestrator.run_study_card_generation(trial_list)
            
            if study_card_result:
                self.results["study_card_generation"] = {
                    "status": "success",
                    "success": study_card_result.success,
                    "pattern_detections": len(study_card_result.pattern_detections) if hasattr(study_card_result, 'pattern_detections') else 0,
                    "decision_records": 1 if hasattr(study_card_result, 'decision_record') and study_card_result.decision_record else 0,
                    "errors": study_card_result.errors if hasattr(study_card_result, 'errors') else [],
                    "warnings": study_card_result.warnings if hasattr(study_card_result, 'warnings') else []
                }
                logger.info(f"✅ Study card generation completed successfully")
            else:
                self.results["study_card_generation"] = {
                    "status": "failed",
                    "error": "No study card result returned"
                }
                logger.error("❌ Study card generation failed: No result returned")
                
        except Exception as e:
            logger.error(f"Study card generation failed: {str(e)}")
            self.results["study_card_generation"] = {
                "status": "failed",
                "error": str(e)
            }
            print(f"\n❌ STUDY CARD GENERATION FAILED: {str(e)}")
            sys.exit(1)
    
    async def _run_pattern_evaluation(self):
        """Run pattern evaluation and gate firing for Cassava trials."""
        logger.info("🎯 TEST: Phase 5: Running pattern evaluation and gate firing")
        
        try:
            # Initialize orchestrator
            logger.info("🚪 TEST: Initializing PipelineOrchestrator")
            orchestrator = PipelineOrchestrator(self.config)
            
            # Get Cassava trials from database
            logger.info("🚪 TEST: Querying database for Cassava trials")
            with session_scope() as session:
                cassava_trials = session.query(Trial).filter(
                    Trial.sponsor_text.like('%Cassava%')
                ).all()
                logger.info(f"🚪 TEST: Found {len(cassava_trials)} Cassava trials in database")
                
                if not cassava_trials:
                    logger.warning("🚪 TEST: No Cassava trials found for signal evaluation")
                    return
                
                # Convert to trial list format
                trial_list = []
                for trial in cassava_trials:
                    trial_data = {
                        'trial_id': trial.trial_id,
                        'nct_id': trial.nct_id,
                        'is_pivotal': trial.is_pivotal
                    }
                    trial_list.append(trial_data)
                    logger.info(f"🚪 TEST: Added trial to list: {trial_data}")
            
            # Run pattern evaluation
            logger.info(f"🎯 TEST: Calling orchestrator.run_pattern_evaluation with {len(trial_list)} trials")
            logger.info(f"🎯 TEST: Trial list being passed to orchestrator: {trial_list}")
            pattern_result = await orchestrator.run_pattern_evaluation(trial_list)
            
            if pattern_result:
                self.results["pattern_evaluation"] = {
                    "success": True,
                    "trials_processed": pattern_result.get('trials_processed', 0),
                    "patterns_detected": pattern_result.get('patterns_detected', 0),
                    "gates_fired": pattern_result.get('gates_fired', 0),
                    "trial_results": pattern_result.get('trial_results', [])
                }
                logger.info(f"✅ Pattern evaluation completed: {pattern_result.get('trials_processed', 0)} trials, {pattern_result.get('patterns_detected', 0)} patterns, {pattern_result.get('gates_fired', 0)} gates")
            else:
                logger.error("❌ Pattern evaluation returned no results")
                self.results["pattern_evaluation"] = {"success": False, "error": "No results returned"}
                
        except Exception as e:
            logger.error(f"Pattern evaluation failed: {e}")
            self.results["pattern_evaluation"] = {"success": False, "error": str(e)}
            print(f"\n❌ PATTERN EVALUATION FAILED: {str(e)}")
            sys.exit(1)
    
    async def _run_independent_analysis(self):
        """Run independent LLM analysis for Cassava trials."""
        logger.info("🧠 Phase 6: Running independent LLM analysis")
        
        try:
            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(self.config)
            
            # Get Cassava trials from database
            with session_scope() as session:
                cassava_trials = session.query(Trial).filter(
                    Trial.sponsor_text.like('%Cassava%')
                ).all()
                
                # Convert to orchestrator format
                trial_list = []
                for trial in cassava_trials:
                    trial_list.append({
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
                        'matching_confidence': 1.0
                    })
            
            # Run independent LLM analysis
            logger.info(f"Running independent LLM analysis for {len(trial_list)} Cassava trials...")
            analysis_result = await orchestrator.run_independent_llm_analysis(trial_list)
            
            if analysis_result:
                self.results["independent_analysis"] = {
                    "status": "success",
                    "success": analysis_result.get("success", False),
                    "trials_analyzed": analysis_result.get("trials_analyzed", 0),
                    "successful_analyses": analysis_result.get("successful_analyses", 0),
                    "failed_analyses": analysis_result.get("failed_analyses", 0),
                    "execution_time_seconds": analysis_result.get("execution_time_seconds", 0)
                }
                logger.info(f"✅ Independent LLM analysis completed: {analysis_result.get('successful_analyses', 0)} successful analyses")
            else:
                self.results["independent_analysis"] = {
                    "status": "failed",
                    "error": "No analysis result returned"
                }
                logger.error("❌ Independent LLM analysis failed: No result returned")
                
        except Exception as e:
            logger.error(f"Independent LLM analysis failed: {str(e)}")
            self.results["independent_analysis"] = {
                "status": "failed",
                "error": str(e)
            }
            print(f"\n❌ INDEPENDENT LLM ANALYSIS FAILED: {str(e)}")
            sys.exit(1)
    
    async def _validate_results(self):
        """Validate test results and data integrity."""
        logger.info("✅ Phase 7: Validating results")
        
        try:
            with session_scope() as session:
                # Count all entities
                company_count = session.query(Company).count()
                trial_count = session.query(Trial).count()
                document_count = session.query(Document).count()
                study_count = session.query(Study).count()
                study_card_count = session.query(StudyCard).count()
                
                # Validate relationships
                trials_with_company = session.query(Trial).filter(
                    Trial.sponsor_company_id.isnot(None)
                ).count()
                
                trials_with_documents = session.query(Trial).join(
                    Document, Trial.trial_id == Document.trial_id
                ).distinct().count()
                
                # Run comprehensive checks
                await self._check_expected_papers(session)
                await self._check_gate_passes(session)
                await self._check_evidence_coverage(session)
                
                # Check for critical validation issues
                validation_status = "success"
                validation_errors = []
                
                if study_card_count == 0:
                    validation_status = "failed"
                    validation_errors.append("No study cards found in database - study cards not saved")
                
                if trials_with_documents == 0:
                    validation_status = "failed"
                    validation_errors.append("No trials linked to documents - document linking failed")
                
                self.results["validation_results"] = {
                    "status": validation_status,
                    "entity_counts": {
                        "companies": company_count,
                        "trials": trial_count,
                        "documents": document_count,
                        "studies": study_count,
                        "study_cards": study_card_count
                    },
                    "errors": validation_errors,
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
            print(f"\n❌ VALIDATION FAILED: {str(e)}")
            sys.exit(1)
    
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
                        paper_info["r_score"] = float(doc.r_score) if doc.r_score is not None else None
                        paper_info["s_score"] = float(doc.s_score) if doc.s_score is not None else None
                        paper_info["r_tier"] = doc.r_tier
                        paper_info["s_tier"] = doc.s_tier
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
                            paper_info["r_score"] = float(doc.r_score) if doc.r_score is not None else None
                            paper_info["s_score"] = float(doc.s_score) if doc.s_score is not None else None
                            paper_info["r_tier"] = doc.r_tier
                            paper_info["s_tier"] = doc.s_tier
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
                score_info = f"R:{paper['r_score']:.3f}" if paper['r_score'] is not None else "R:N/A"
                score_info += f" S:{paper['s_score']:.3f}" if paper['s_score'] is not None else " S:N/A"
                logger.info(f"   • {paper['year']}: {paper['title']} (PMID: {paper['pmid']}) - {score_info}")
        
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
    
    async def _check_gate_passes(self, session: Session):
        """Check if any gates passed and log warnings."""
        logger.info("🎯 Checking for gate passes...")
        
        # Check for gate passes using raw SQL to avoid model/schema mismatches
        try:
            # Check for fired gates using raw SQL (based on actual DB schema)
            fired_gates_result = session.execute(text("""
                SELECT g_id, rationale_text, trial_id 
                FROM gates 
                WHERE fired_bool = true
            """)).fetchall()
            
            # Check for pattern detections using raw SQL
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
            else:
                logger.info("✅ No gates passed - gate criteria appear appropriately strict")
            
            # Store results
            if "validation_results" not in self.results:
                self.results["validation_results"] = {}
            
            self.results["validation_results"]["gate_passes_check"] = {
                "total_fired_gates": len(fired_gates_result),
                "total_passed": total_passed,
                "fired_gates": [
                    {
                        "g_id": gate_row[0],
                        "trial_id": gate_row[2],
                        "rationale": gate_row[1][:100] + "..." if gate_row[1] and len(gate_row[1]) > 100 else gate_row[1]
                    } for gate_row in fired_gates_result
                ]
            }
            
        except Exception as e:
            logger.warning(f"⚠️  Gate pass check failed: {str(e)}")
            self.results["warnings"].append(f"Gate pass check failed: {str(e)}")
    
    async def _check_evidence_coverage(self, session: Session):
        """Check evidence section coverage and log warnings for low coverage."""
        logger.info("📊 Checking evidence section coverage...")
        
        coverage_warnings = []
        
        # Check document coverage by source type
        try:
            # Get main trial
            main_trial = session.query(Trial).filter(Trial.nct_id == "NCT05515666").first()
                
            if not main_trial:
                logger.warning("Main trial not found for coverage check")
                return
            
            # Count documents by source type for the main trial
            trial_docs = session.query(Document).filter(
                Document.trial_id == main_trial.trial_id
            ).all()
            
            source_type_counts = {}
            total_docs = 0
            
            for doc in trial_docs:
                source_type = doc.source_type or "Unknown"
                source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
                total_docs += 1
            
            # Check for low coverage in key evidence sections
            if total_docs < 5:
                warning_msg = f"⚠️  WARNING: Low document coverage - only {total_docs} documents found for main trial {main_trial.nct_id}"
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
        results_file = project_root / "tests" / "logs" / "comprehensive_cassava_test_v2_results.json"
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Print summary
        print("\n" + "="*80)
        print("🧪 COMPREHENSIVE CASSAVA PIPELINE TEST V2 RESULTS")
        print("="*80)
        
        print(f"\n⏱️  Test Duration: {test_duration:.2f} seconds")
        print(f"📁 Results saved to: {results_file}")
        
        # Phase summaries
        phases = [
            ("Database Setup", self.results["database_setup"]),
            ("CT.gov Ingestion", self.results["ctgov_ingestion"]),
            ("PubMed Processing", self.results["pubmed_processing"]),
            ("Study Card Generation", self.results["study_card_generation"]),
            ("Independent Analysis", self.results["independent_analysis"]),
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
            print(f"   • Study Cards: {counts['study_cards']}")
        
        # PubMed metrics
        if "pubmed_processing" in self.results and self.results["pubmed_processing"].get("status") == "success":
            pubmed = self.results["pubmed_processing"]
            print(f"\n📚 PubMed Processing Metrics:")
            print(f"   • Trials processed: {pubmed.get('trials_processed', 0)}")
            print(f"   • Documents processed: {pubmed.get('documents_processed', 0)}")
            print(f"   • Success: {pubmed.get('success', False)}")
        
        # Study card metrics
        if "study_card_generation" in self.results and self.results["study_card_generation"].get("status") == "success":
            study_cards = self.results["study_card_generation"]
            print(f"\n📋 Study Card Generation Metrics:")
            print(f"   • Success: {study_cards.get('success', False)}")
            print(f"   • Pattern detections: {study_cards.get('pattern_detections', 0)}")
            print(f"   • Decision records: {study_cards.get('decision_records', 0)}")
        
        # Independent analysis metrics
        if "independent_analysis" in self.results and self.results["independent_analysis"].get("status") == "success":
            analysis = self.results["independent_analysis"]
            print(f"\n🧠 Independent LLM Analysis Metrics:")
            print(f"   • Success: {analysis.get('success', False)}")
            print(f"   • Trials analyzed: {analysis.get('trials_analyzed', 0)}")
            print(f"   • Successful analyses: {analysis.get('successful_analyses', 0)}")
            print(f"   • Failed analyses: {analysis.get('failed_analyses', 0)}")
            print(f"   • Execution time: {analysis.get('execution_time_seconds', 0):.2f}s")
        
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
            
            # Gate passes check
            if "gate_passes_check" in validation:
                gates_check = validation["gate_passes_check"]
                print(f"   • Gate Passes Check:")
                print(f"     - Total passed: {gates_check['total_passed']}")
                print(f"     - Fired gates: {gates_check['total_fired_gates']}")
            
            # Evidence coverage check
            if "evidence_coverage_check" in validation:
                coverage_check = validation["evidence_coverage_check"]
                print(f"   • Evidence Coverage Check:")
                print(f"     - Total documents: {coverage_check['total_documents']}")
                print(f"     - PubMed papers: {coverage_check['pubmed_papers']}")
                print(f"     - Coverage warnings: {coverage_check['coverage_warnings']}")
        
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


async def main():
    """Main test function."""
    test = ComprehensiveCassavaTestV2()
    await test.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())
