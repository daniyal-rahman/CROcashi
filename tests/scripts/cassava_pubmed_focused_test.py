#!/usr/bin/env python3
"""
Focused Cassava PubMed Ingestion Test

This test focuses specifically on PubMed ingestion issues using the Cassava trial.
It stops at PubMed ingestion and provides detailed logging for:
1. Review and news article filtering issues
2. Guardrails debugging and logging
3. Document retrieval and processing metrics

Usage:
    python tests/scripts/cassava_pubmed_focused_test.py
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

from sqlalchemy.orm import Session
from sqlalchemy import text, inspect

# Import our modules
from ncfd.db.session import session_scope, get_engine, reset_engine
from ncfd.db.models import Base, Trial, Company, Document, Study, DocumentLink, TrialDocCandidate
from ncfd.ingest.pubmed import RetrievalProcessor, AbstractProcessor
from ncfd.config import get_config

# Setup detailed logging for debugging
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO to see more details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable detailed logging for PubMed components
logging.getLogger("ncfd.ingest.pubmed").setLevel(logging.DEBUG)
logging.getLogger("ncfd.pipeline").setLevel(logging.INFO)

# Real-world Cassava trial data
CASSAVA_TRIALS = [
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
        "mechanism": "filamin A inhibitor"
    },
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
        "mechanism": "filamin A inhibitor"
    }
]

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
    ]
}

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

def deduplicate_and_canonicalize_aliases(aliases: List[str]) -> Dict[str, List[str]]:
    """Deduplicate and canonicalize aliases."""
    normalized_to_original = {}
    for alias in aliases:
        normalized = alias.strip().lower()
        if normalized and normalized not in normalized_to_original:
            normalized_to_original[normalized] = alias.strip()
    
    canonical_set = set(normalized_to_original.keys())
    display_list = list(normalized_to_original.values())
    
    return {
        'canonical_set': canonical_set,
        'display_list': display_list
    }

class CassavaPubMedFocusedTest:
    """Focused test for PubMed ingestion issues."""
    
    def __init__(self):
        self.test_start_time = datetime.now(timezone.utc)
        self.results = {
            "test_info": {
                "start_time": self.test_start_time.isoformat(),
                "test_name": "Cassava PubMed Focused Test",
                "version": "1.0"
            },
            "database_setup": {},
            "ctgov_seeding": {},
            "pubmed_processing": {},
            "document_analysis": {},
            "filtering_analysis": {},
            "guardrails_analysis": {},
            "errors": [],
            "warnings": []
        }
        
        # Load configuration
        self.config = self._load_test_config()
        
    def _load_test_config(self) -> Dict[str, Any]:
        """Load test configuration focused on PubMed ingestion."""
        config = {
            "worker_id": "cassava_pubmed_focused_test",
            
            # CT.gov configuration - use seeded trials
            "ctgov": {
                "incremental": False,
                "seed_trials": CASSAVA_TRIALS,
                "batch_size": 10,
                "retry_attempts": 3
            },
            
            # PubMed configuration - enhanced for debugging
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
                    "max_results": 200  # Increased for comprehensive analysis
                },
                "asset_names": ["simufilam", "PTI-125", "filamin A inhibitor"],
                "indications": ["Alzheimer's disease", "dementia", "cognitive impairment"],
                "query_config": {
                    "max_terms": 100,
                    "enable_boolean_operators": True,
                    "date_range": ("2010/01/01", "2025/12/31")
                },
                "reuse_existing": False,  # Force fresh retrieval
                "min_documents_required": 1,
                "skip_if_sufficient": False,
                "enable_stages": ["retrieval", "processing"]
            }
        }
        
        return config
    
    async def run_focused_test(self):
        """Run the focused PubMed test."""
        logger.info("🧪 Starting Cassava PubMed Focused Test")
        logger.info("=" * 80)
        
        try:
            # Phase 1: Database Setup
            await self._setup_database()
            
            # Phase 2: CT.gov Trial Seeding
            await self._seed_ctgov_trials()
            
            # Phase 3: PubMed Processing (Main Focus)
            await self._test_pubmed_pipeline()
            
            # Phase 4: Document Analysis
            await self._analyze_documents()
            
            # Phase 5: Filtering Analysis
            await self._analyze_filtering()
            
            # Phase 6: Guardrails Analysis
            await self._analyze_guardrails()
            
            # Phase 7: Expected Papers Check
            await self._check_expected_papers()
            
            # Final reporting
            self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            self.results["errors"].append(f"Test execution failed: {str(e)}")
            raise
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
                    
                    seeded_trials.append({
                        "trial_id": trial.trial_id,
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
        """Test PubMed literature processing with detailed logging."""
        logger.info("📚 Phase 3: Testing PubMed pipeline (MAIN FOCUS)")
        
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
                
                # Run retrieval processing
                logger.info("🔍 Starting retrieval processing...")
                retrieval_result = await retrieval_processor.execute_retrieval(
                    trial_id=main_trial.trial_id,
                    asset_aliases=comprehensive_asset_names,
                    indication_terms=comprehensive_indications,
                    max_results=200,  # Increased for comprehensive analysis
                    trial_nct=main_trial.nct_id,
                    trial_phase=main_trial.phase,
                    company_name="Cassava Sciences, Inc.",
                    company_aliases=["Cassava Sciences", "Pain Therapeutics"]
                )
                
                if not retrieval_result.success:
                    raise ValueError(f"Retrieval failed: {retrieval_result.error_message}")
                
                logger.info(f"✅ Retrieval completed: {retrieval_result.documents_discovered} documents discovered")
                
                # Run abstract processing
                logger.info("📄 Starting abstract processing...")
                processing_result = await abstract_processor.process_documents(
                    documents=retrieval_result.documents,
                    trial_id=main_trial.trial_id,
                    trial_asset="simufilam",
                    trial_indication="Alzheimer's disease",
                    trial_nct=main_trial.nct_id
                )
                
                logger.info(f"✅ Abstract processing completed: {processing_result.documents_processed} documents processed")
                
                # Promote trial-doc candidates to document links
                logger.info("🔗 Promoting trial-doc candidates to document links...")
                promoted_count = self._promote_candidates_to_links(main_trial.trial_id, main_trial.nct_id)
                logger.info(f"✅ Promoted {promoted_count} trial-doc candidates to document links")
                
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
                documents = session.query(Document).limit(20).all()  # Get first 20 documents for details
                for doc in documents:
                    doc_details.append({
                        "pmid": doc.pmid,
                        "title": (doc.title[:100] + "...") if doc.title and len(doc.title) > 100 else doc.title,
                        "source_type": doc.source_type,
                        "pubtype": getattr(doc, 'pubtype', None),
                        "has_full_text": getattr(doc, 'has_full_text', None),
                        "pmcid": doc.pmcid
                    })
                
                self.results["pubmed_processing"] = {
                    "status": "success",
                    "main_trial": main_trial.nct_id,
                    "trials_processed": 1,
                    "documents_created": doc_count,
                    "document_links": doc_links,
                    "retrieval_documents": retrieval_docs_count,
                    "processed_documents": processed_docs_count,
                    "document_details": doc_details,
                    "pipeline_result": {
                        "success": True,
                        "documents_processed": total_documents,
                        "errors": [],
                        "error_count": 0,
                        "stages_completed": 2
                    }
                }
                
                logger.info(f"✅ PubMed processing completed for main trial {main_trial.nct_id}: {doc_count} documents, {doc_links} links")
                logger.info(f"📄 Retrieval documents (raw): {retrieval_docs_count}")
                logger.info(f"📄 Processed documents (filtered): {processed_docs_count}")
                
        except Exception as e:
            logger.error(f"PubMed pipeline test failed: {str(e)}")
            self.results["pubmed_processing"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _analyze_documents(self):
        """Analyze retrieved documents for content quality and filtering issues."""
        logger.info("📊 Phase 4: Analyzing document content and quality")
        
        try:
            with session_scope() as session:
                # Get all documents
                documents = session.query(Document).all()
                
                if not documents:
                    logger.warning("No documents found for analysis")
                    self.results["document_analysis"] = {
                        "status": "no_documents",
                        "total_documents": 0
                    }
                    return
                
                # Analyze document types
                doc_types = {}
                pubtypes = {}
                source_types = {}
                review_articles = []
                news_articles = []
                clinical_trials = []
                other_docs = []
                
                for doc in documents:
                    # Count by source type
                    source_type = doc.source_type or "Unknown"
                    source_types[source_type] = source_types.get(source_type, 0) + 1
                    
                    # Count by pubtype
                    pubtype = getattr(doc, 'pubtype', None) or "Unknown"
                    pubtypes[pubtype] = pubtypes.get(pubtype, 0) + 1
                    
                    # Analyze content for review/news articles
                    title = doc.title or ""
                    abstract = getattr(doc, 'abstract', None) or ""
                    
                    # Check for review articles
                    if any(keyword in title.lower() for keyword in ['review', 'systematic review', 'meta-analysis']):
                        review_articles.append({
                            "pmid": doc.pmid,
                            "title": title[:100] + "..." if len(title) > 100 else title,
                            "pubtype": pubtype,
                            "source_type": source_type
                        })
                    
                    # Check for news articles
                    if any(keyword in title.lower() for keyword in ['news', 'press release', 'announcement', 'update']):
                        news_articles.append({
                            "pmid": doc.pmid,
                            "title": title[:100] + "..." if len(title) > 100 else title,
                            "pubtype": pubtype,
                            "source_type": source_type
                        })
                    
                    # Check for clinical trials
                    if any(keyword in title.lower() for keyword in ['clinical trial', 'randomized', 'phase', 'study']):
                        clinical_trials.append({
                            "pmid": doc.pmid,
                            "title": title[:100] + "..." if len(title) > 100 else title,
                            "pubtype": pubtype,
                            "source_type": source_type
                        })
                    
                    # Other documents
                    if not any(keyword in title.lower() for keyword in ['review', 'news', 'clinical trial', 'randomized', 'phase', 'study']):
                        other_docs.append({
                            "pmid": doc.pmid,
                            "title": title[:100] + "..." if len(title) > 100 else title,
                            "pubtype": pubtype,
                            "source_type": source_type
                        })
                
                # Generate warnings for problematic content
                warnings = []
                
                if len(news_articles) > 0:
                    warning_msg = f"⚠️  WARNING: {len(news_articles)} news articles found - these should be filtered out"
                    logger.warning(warning_msg)
                    warnings.append(warning_msg)
                
                if len(review_articles) > len(clinical_trials):
                    warning_msg = f"⚠️  WARNING: More review articles ({len(review_articles)}) than clinical trials ({len(clinical_trials)}) - check filtering"
                    logger.warning(warning_msg)
                    warnings.append(warning_msg)
                
                self.results["document_analysis"] = {
                    "status": "success",
                    "total_documents": len(documents),
                    "source_types": source_types,
                    "pubtypes": pubtypes,
                    "review_articles": {
                        "count": len(review_articles),
                        "articles": review_articles[:10]  # First 10 for details
                    },
                    "news_articles": {
                        "count": len(news_articles),
                        "articles": news_articles[:10]  # First 10 for details
                    },
                    "clinical_trials": {
                        "count": len(clinical_trials),
                        "articles": clinical_trials[:10]  # First 10 for details
                    },
                    "other_documents": {
                        "count": len(other_docs),
                        "articles": other_docs[:10]  # First 10 for details
                    },
                    "warnings": warnings
                }
                
                logger.info(f"✅ Document analysis completed: {len(documents)} total documents")
                logger.info(f"📊 Source types: {source_types}")
                logger.info(f"📊 Pubtypes: {pubtypes}")
                logger.info(f"📚 Review articles: {len(review_articles)}")
                logger.info(f"📰 News articles: {len(news_articles)}")
                logger.info(f"🔬 Clinical trials: {len(clinical_trials)}")
                logger.info(f"📄 Other documents: {len(other_docs)}")
                
        except Exception as e:
            logger.error(f"Document analysis failed: {str(e)}")
            self.results["document_analysis"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _analyze_filtering(self):
        """Analyze filtering effectiveness and identify issues."""
        logger.info("🔍 Phase 5: Analyzing filtering effectiveness")
        
        try:
            with session_scope() as session:
                # Get all documents
                documents = session.query(Document).all()
                
                if not documents:
                    logger.warning("No documents found for filtering analysis")
                    self.results["filtering_analysis"] = {
                        "status": "no_documents",
                        "total_documents": 0
                    }
                    return
                
                # Analyze filtering effectiveness
                filtering_issues = []
                quality_metrics = {
                    "high_quality": 0,
                    "medium_quality": 0,
                    "low_quality": 0,
                    "unclear_quality": 0
                }
                
                for doc in documents:
                    title = doc.title or ""
                    abstract = getattr(doc, 'abstract', None) or ""
                    pubtype = getattr(doc, 'pubtype', None) or ""
                    
                    # Quality assessment based on content
                    quality_score = 0
                    
                    # Positive indicators
                    if any(keyword in title.lower() for keyword in ['clinical trial', 'randomized', 'phase', 'study']):
                        quality_score += 3
                    if any(keyword in title.lower() for keyword in ['simufilam', 'pti-125', 'filamin']):
                        quality_score += 2
                    if any(keyword in title.lower() for keyword in ['alzheimer', 'dementia', 'cognitive']):
                        quality_score += 2
                    if pubtype and 'clinical trial' in pubtype.lower():
                        quality_score += 2
                    
                    # Negative indicators
                    if any(keyword in title.lower() for keyword in ['news', 'press release', 'announcement']):
                        quality_score -= 5
                    if any(keyword in title.lower() for keyword in ['review', 'systematic review', 'meta-analysis']):
                        quality_score -= 1  # Reviews are okay but not primary
                    
                    # Categorize quality
                    if quality_score >= 5:
                        quality_metrics["high_quality"] += 1
                    elif quality_score >= 2:
                        quality_metrics["medium_quality"] += 1
                    elif quality_score >= 0:
                        quality_metrics["low_quality"] += 1
                    else:
                        quality_metrics["unclear_quality"] += 1
                    
                    # Identify filtering issues
                    if quality_score < 0:
                        filtering_issues.append({
                            "pmid": doc.pmid,
                            "title": title[:100] + "..." if len(title) > 100 else title,
                            "quality_score": quality_score,
                            "issue": "Low quality content that should be filtered"
                        })
                
                # Generate filtering recommendations
                recommendations = []
                
                if quality_metrics["unclear_quality"] > 0:
                    recommendations.append("Consider adding negative keywords to filter out low-quality content")
                
                if quality_metrics["high_quality"] < quality_metrics["low_quality"]:
                    recommendations.append("Review search terms and filtering criteria - more low-quality than high-quality content")
                
                self.results["filtering_analysis"] = {
                    "status": "success",
                    "total_documents": len(documents),
                    "quality_metrics": quality_metrics,
                    "filtering_issues": filtering_issues[:10],  # First 10 issues
                    "recommendations": recommendations
                }
                
                logger.info(f"✅ Filtering analysis completed")
                logger.info(f"📊 Quality metrics: {quality_metrics}")
                logger.info(f"⚠️  Filtering issues: {len(filtering_issues)}")
                logger.info(f"💡 Recommendations: {len(recommendations)}")
                
        except Exception as e:
            logger.error(f"Filtering analysis failed: {str(e)}")
            self.results["filtering_analysis"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _analyze_guardrails(self):
        """Analyze guardrails effectiveness using the new pre-LLM guardrails system."""
        logger.info("🛡️ Phase 6: Analyzing guardrails effectiveness")
        
        try:
            from ncfd.ingest.pubmed.retrieval.pre_llm_guardrails import PreLLMGuardrailsSystem, PreLLMGuardrailsConfig
            from ncfd.entities.schema import EntityPack, AssetInfo, IndicationInfo, MechanismInfo
            
            with session_scope() as session:
                # Get all documents
                documents = session.query(Document).all()
                
                if not documents:
                    logger.warning("No documents found for guardrails analysis")
                    self.results["guardrails_analysis"] = {
                        "status": "no_documents",
                        "total_documents": 0
                    }
                    return
                
                # Initialize pre-LLM guardrails system
                guardrails_config = PreLLMGuardrailsConfig(
                    reject_off_topic=True,
                    reject_high_risk=True,
                    high_risk_threshold=0.6,
                    require_relevance=True,
                    log_decisions=False,  # Reduce noise in test
                    log_rejections=False
                )
                guardrails = PreLLMGuardrailsSystem(guardrails_config)
                
                # Create entity pack for Cassava
                entity_pack = EntityPack(
                    entity_id='cassava_test',
                    company=None,
                    asset=AssetInfo(canonical='simufilam', aliases=['PTI-125', 'PTI 125']),
                    mechanism=MechanismInfo(targets=['filamin A', 'FLNA']),
                    indications=IndicationInfo(primary=['alzheimer disease'], synonyms=['alzheimer', 'ad']),
                    registries=None,
                    publishers=None,
                    date_ranges=None
                )
                
                # Analyze guardrails effectiveness
                guardrails_issues = []
                guardrails_metrics = {
                    "passed_guardrails": 0,
                    "failed_guardrails": 0,
                    "unclear_guardrails": 0
                }
                
                for doc in documents:
                    # Apply pre-LLM guardrails check
                    result = guardrails.should_process_document(doc, entity_pack)
                    
                    if result.should_process:
                        guardrails_metrics["passed_guardrails"] += 1
                    else:
                        guardrails_metrics["failed_guardrails"] += 1
                        guardrails_issues.append({
                            "pmid": doc.pmid,
                            "title": doc.title[:100] + "..." if doc.title and len(doc.title) > 100 else doc.title,
                            "reason": result.reason,
                            "risk_score": result.risk_score,
                            "rejection_details": result.rejection_details,
                            "issue": f"Failed guardrails - {result.reason}"
                        })
                
                # Generate guardrails recommendations
                recommendations = []
                
                if guardrails_metrics["failed_guardrails"] > 0:
                    recommendations.append("Pre-LLM guardrails are working - filtering inappropriate content")
                
                if guardrails_metrics["failed_guardrails"] > guardrails_metrics["passed_guardrails"]:
                    recommendations.append("Guardrails may be too strict - consider adjusting thresholds")
                
                # Get rejection summary
                rejection_summary = guardrails.get_rejection_summary()
                
                self.results["guardrails_analysis"] = {
                    "status": "success",
                    "total_documents": len(documents),
                    "guardrails_metrics": guardrails_metrics,
                    "guardrails_issues": guardrails_issues[:10],  # First 10 issues
                    "rejection_summary": rejection_summary,
                    "recommendations": recommendations
                }
                
                logger.info(f"✅ Guardrails analysis completed")
                logger.info(f"📊 Guardrails metrics: {guardrails_metrics}")
                logger.info(f"📊 Rejection summary: {rejection_summary}")
                logger.info(f"⚠️  Guardrails issues: {len(guardrails_issues)}")
                logger.info(f"💡 Recommendations: {len(recommendations)}")
                
        except Exception as e:
            logger.error(f"Guardrails analysis failed: {str(e)}")
            self.results["guardrails_analysis"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
    async def _check_expected_papers(self):
        """Check if expected Cassava papers were retrieved and log warnings for missing ones."""
        logger.info("🔍 Phase 7: Checking for expected Cassava papers...")
        
        try:
            with session_scope() as session:
                # Get all documents with scores
                all_documents = session.query(Document).all()
                
                if not all_documents:
                    logger.warning("No documents found for expected papers check")
                    self.results["expected_papers_check"] = {
                        "status": "no_documents",
                        "total_documents": 0
                    }
                    return
                
                # Sort documents by r_score (descending) to see ranking
                documents_with_scores = []
                for doc in all_documents:
                    documents_with_scores.append({
                        "doc_id": doc.doc_id,
                        "pmid": doc.pmid,
                        "title": doc.title,
                        "r_score": float(doc.r_score) if doc.r_score is not None else None,
                        "s_score": float(doc.s_score) if doc.s_score is not None else None,
                        "r_tier": doc.r_tier,
                        "s_tier": doc.s_tier
                    })
                
                # Sort by r_score (highest first)
                documents_with_scores.sort(key=lambda x: x["r_score"] or 0, reverse=True)
                
                missing_papers = []
                found_papers = []
                
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
                        for i, doc in enumerate(documents_with_scores):
                            # Find document with matching PMCID
                            actual_doc = session.query(Document).filter(Document.pmcid == expected_paper["pmcid"]).first()
                            if actual_doc:
                                found = True
                                paper_info["found_by"] = "pmcid"
                                paper_info["doc_id"] = actual_doc.doc_id
                                paper_info["pmid"] = actual_doc.pmid
                                paper_info["rank"] = i + 1
                                paper_info["r_score"] = float(actual_doc.r_score) if actual_doc.r_score is not None else None
                                paper_info["s_score"] = float(actual_doc.s_score) if actual_doc.s_score is not None else None
                                paper_info["r_tier"] = actual_doc.r_tier
                                paper_info["s_tier"] = actual_doc.s_tier
                                break
                    
                    # If not found by PMCID, try title matching
                    if not found:
                        title_keywords = expected_paper["title"].lower().split()[:3]  # First 3 words
                        for i, doc in enumerate(documents_with_scores):
                            if doc["title"]:
                                doc_title_lower = doc["title"].lower()
                                if all(keyword in doc_title_lower for keyword in title_keywords):
                                    found = True
                                    paper_info["found_by"] = "title_match"
                                    paper_info["doc_id"] = doc["doc_id"]
                                    paper_info["pmid"] = doc["pmid"]
                                    paper_info["pmcid"] = doc.get("pmcid")
                                    paper_info["rank"] = i + 1
                                    paper_info["r_score"] = doc["r_score"]
                                    paper_info["s_score"] = doc["s_score"]
                                    paper_info["r_tier"] = doc["r_tier"]
                                    paper_info["s_tier"] = doc["s_tier"]
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
                
                # Log success for found papers with scoring information
                if found_papers:
                    logger.info(f"✅ Found {len(found_papers)} expected Cassava papers:")
                    for paper in found_papers:
                        score_info = f"R:{paper['r_score']:.3f}" if paper['r_score'] is not None else "R:N/A"
                        score_info += f" S:{paper['s_score']:.3f}" if paper['s_score'] is not None else " S:N/A"
                        logger.info(f"   • Rank #{paper['rank']}: {paper['year']} {paper['title']} (PMID: {paper['pmid']}) - {score_info}")
                
                # Show top 10 documents by score for comparison
                logger.info(f"\n📊 Top 10 documents by R-score:")
                for i, doc in enumerate(documents_with_scores[:10]):
                    score_info = f"R:{doc['r_score']:.3f}" if doc['r_score'] is not None else "R:N/A"
                    score_info += f" S:{doc['s_score']:.3f}" if doc['s_score'] is not None else " S:N/A"
                    logger.info(f"  #{i+1}: {doc['title'][:80]}... (PMID: {doc['pmid']}) - {score_info}")
                
                # Store results
                self.results["expected_papers_check"] = {
                    "status": "success",
                    "total_expected": len(EXPECTED_CASSAVA_PAPERS),
                    "found": len(found_papers),
                    "missing": len(missing_papers),
                    "found_papers": found_papers,
                    "missing_papers": missing_papers,
                    "top_documents": documents_with_scores[:10]
                }
                
                logger.info(f"✅ Expected papers check completed: {len(found_papers)}/{len(EXPECTED_CASSAVA_PAPERS)} found")
                
        except Exception as e:
            logger.error(f"Expected papers check failed: {str(e)}")
            self.results["expected_papers_check"] = {
                "status": "failed",
                "error": str(e)
            }
            raise
    
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
                        asset_id=None,
                        company_id=company_id,
                        link_type='trial_document',
                        confidence=0.8,
                        heuristics={'stage': candidate.stage},
                        evidence={
                            'evidence_type': 'promoted_from_candidate',
                            'source_text': 'Automatically promoted from trial-doc candidate',
                            'confidence': 0.8,
                            'validation_status': 'pending'
                        }
                    )
                    session.add(link)
                    promoted_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to create link for doc {candidate.doc_id}: {e}")
            
            session.commit()
        
        return promoted_count
    
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
        results_file = project_root / "tests" / "logs" / "cassava_pubmed_focused_test_results.json"
        results_file.parent.mkdir(exist_ok=True)
        
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Print summary
        print("\n" + "="*80)
        print("🧪 CASSAVA PUBMED FOCUSED TEST RESULTS")
        print("="*80)
        
        print(f"\n⏱️  Test Duration: {test_duration:.2f} seconds")
        print(f"📁 Results saved to: {results_file}")
        
        # Phase summaries
        phases = [
            ("Database Setup", self.results["database_setup"]),
            ("CT.gov Seeding", self.results["ctgov_seeding"]),
            ("PubMed Processing", self.results["pubmed_processing"]),
            ("Document Analysis", self.results["document_analysis"]),
            ("Filtering Analysis", self.results["filtering_analysis"]),
            ("Guardrails Analysis", self.results["guardrails_analysis"]),
            ("Expected Papers Check", self.results["expected_papers_check"])
        ]
        
        for phase_name, phase_result in phases:
            status = "✅" if phase_result.get("status") == "success" else "❌"
            print(f"\n{status} {phase_name}: {phase_result.get('status', 'unknown')}")
            
            if phase_result.get("status") == "failed":
                print(f"   Error: {phase_result.get('error', 'Unknown error')}")
        
        # Document analysis results
        if "document_analysis" in self.results and self.results["document_analysis"].get("status") == "success":
            doc_analysis = self.results["document_analysis"]
            print(f"\n📊 Document Analysis Results:")
            print(f"   • Total documents: {doc_analysis['total_documents']}")
            print(f"   • Review articles: {doc_analysis['review_articles']['count']}")
            print(f"   • News articles: {doc_analysis['news_articles']['count']}")
            print(f"   • Clinical trials: {doc_analysis['clinical_trials']['count']}")
            print(f"   • Other documents: {doc_analysis['other_documents']['count']}")
            
            if doc_analysis['warnings']:
                print(f"   • Warnings: {len(doc_analysis['warnings'])}")
                for warning in doc_analysis['warnings']:
                    print(f"     - {warning}")
        
        # Filtering analysis results
        if "filtering_analysis" in self.results and self.results["filtering_analysis"].get("status") == "success":
            filtering = self.results["filtering_analysis"]
            print(f"\n🔍 Filtering Analysis Results:")
            print(f"   • High quality: {filtering['quality_metrics']['high_quality']}")
            print(f"   • Medium quality: {filtering['quality_metrics']['medium_quality']}")
            print(f"   • Low quality: {filtering['quality_metrics']['low_quality']}")
            print(f"   • Unclear quality: {filtering['quality_metrics']['unclear_quality']}")
            print(f"   • Filtering issues: {len(filtering['filtering_issues'])}")
            
            if filtering['recommendations']:
                print(f"   • Recommendations:")
                for rec in filtering['recommendations']:
                    print(f"     - {rec}")
        
        # Guardrails analysis results
        if "guardrails_analysis" in self.results and self.results["guardrails_analysis"].get("status") == "success":
            guardrails = self.results["guardrails_analysis"]
            print(f"\n🛡️ Guardrails Analysis Results:")
            print(f"   • Passed guardrails: {guardrails['guardrails_metrics']['passed_guardrails']}")
            print(f"   • Failed guardrails: {guardrails['guardrails_metrics']['failed_guardrails']}")
            print(f"   • Guardrails issues: {len(guardrails['guardrails_issues'])}")
            
            if 'rejection_summary' in guardrails:
                print(f"   • Rejection summary: {guardrails['rejection_summary']}")
            
            if guardrails['recommendations']:
                print(f"   • Recommendations:")
                for rec in guardrails['recommendations']:
                    print(f"     - {rec}")
        
        # Expected papers check results
        if "expected_papers_check" in self.results and self.results["expected_papers_check"].get("status") == "success":
            expected_papers = self.results["expected_papers_check"]
            print(f"\n📚 Expected Papers Check Results:")
            print(f"   • Expected: {expected_papers['total_expected']}")
            print(f"   • Found: {expected_papers['found']}")
            print(f"   • Missing: {expected_papers['missing']}")
            
            if expected_papers['missing'] > 0:
                print(f"   • Missing papers:")
                for paper in expected_papers['missing_papers']:
                    print(f"     - {paper['year']}: {paper['title']} ({paper['description']})")
            
            if expected_papers['found'] > 0:
                print(f"   • Found papers:")
                for paper in expected_papers['found_papers']:
                    score_info = f"R:{paper['r_score']:.3f}" if paper['r_score'] is not None else "R:N/A"
                    score_info += f" S:{paper['s_score']:.3f}" if paper['s_score'] is not None else " S:N/A"
                    print(f"     - Rank #{paper['rank']}: {paper['year']} {paper['title']} (PMID: {paper['pmid']}) - {score_info}")
            
            # Show top 5 documents by score for comparison
            if 'top_documents' in expected_papers and expected_papers['top_documents']:
                print(f"\n📊 Top 5 documents by R-score:")
                for i, doc in enumerate(expected_papers['top_documents'][:5]):
                    score_info = f"R:{doc['r_score']:.3f}" if doc['r_score'] is not None else "R:N/A"
                    score_info += f" S:{doc['s_score']:.3f}" if doc['s_score'] is not None else " S:N/A"
                    print(f"  #{i+1}: {doc['title'][:60]}... (PMID: {doc['pmid']}) - {score_info}")
        
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
    test = CassavaPubMedFocusedTest()
    await test.run_focused_test()


if __name__ == "__main__":
    asyncio.run(main())
