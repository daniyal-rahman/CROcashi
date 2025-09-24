#!/usr/bin/env python3
"""
Cassava Extraction Focused Test

This test seeds the database with the 3 specific Cassava studies and focuses on:
- Study card extraction
- Factsheet extraction  
- Pattern detection
- Quality gates

Skips CT.gov and PubMed ingestion phases to isolate extraction components.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ncfd.db.session import session_scope
from ncfd.db.models import (
    Base, Trial, Document, DocumentText, Company, Asset, 
    StudyCard, Factsheet, PatternDetection, GateAssessment, DocumentLink
)
from ncfd.pipeline.orchestrator import PipelineOrchestrator
from ncfd.utils.config_manager import ConfigManager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# The 3 specific Cassava studies from the logs
CASSAVA_STUDIES = [
    {
        "pmcid": "PMC10531384",
        "pmid": "37512345",  # Example PMID
        "year": 2023,
        "title": "Simufilam Reverses Aberrant Receptor Interactions",
        "description": "Mechanism paper (2023): FLNA–α7nAChR receptor interactions (Cell Mol Neurobiol)",
        "abstract": "Simufilam, a small molecule drug candidate for Alzheimer's disease, has been shown to reverse aberrant receptor interactions involving filamin A (FLNA) and α7 nicotinic acetylcholine receptor (α7nAChR). This study demonstrates that simufilam disrupts the pathological linkage between FLNA and α7nAChR, restoring normal receptor function and reducing neuroinflammation in Alzheimer's disease models.",
        "full_text": "Simufilam Reverses Aberrant Receptor Interactions in Alzheimer's Disease\n\nAbstract\nSimufilam, a small molecule drug candidate for Alzheimer's disease, has been shown to reverse aberrant receptor interactions involving filamin A (FLNA) and α7 nicotinic acetylcholine receptor (α7nAChR). This study demonstrates that simufilam disrupts the pathological linkage between FLNA and α7nAChR, restoring normal receptor function and reducing neuroinflammation in Alzheimer's disease models.\n\nIntroduction\nAlzheimer's disease (AD) is characterized by the accumulation of amyloid-beta (Aβ) plaques and tau tangles, leading to neuroinflammation and cognitive decline. Recent research has identified aberrant receptor interactions as a key pathological mechanism in AD.\n\nMethods\nWe used postmortem human AD brain tissue and transgenic mouse models to investigate the effects of simufilam on FLNA-α7nAChR interactions. Immunohistochemistry and co-immunoprecipitation assays were performed to assess receptor binding.\n\nResults\nSimufilam treatment significantly reduced FLNA-α7nAChR binding in AD brain tissue compared to controls. The drug restored normal receptor function and reduced neuroinflammation markers.\n\nConclusion\nThese findings support the therapeutic potential of simufilam for Alzheimer's disease by targeting aberrant receptor interactions.",
        "study_type": "preclinical",
        "r_score": 0.68,
        "s_score": 0.72
    },
    {
        "pmcid": "PMC10339288",
        "pmid": "37512346",  # Example PMID
        "year": 2023,
        "title": "Simufilam suppresses overactive mTOR and restores its",
        "description": "Mechanism paper (2023): mTOR/lymphocytes (Frontiers in Aging)",
        "abstract": "This study investigates the effects of simufilam on mTOR signaling in lymphocytes from Alzheimer's disease patients. We found that simufilam suppresses overactive mTOR signaling and restores normal cellular function, providing a potential therapeutic mechanism for AD treatment.",
        "full_text": "Simufilam Suppresses Overactive mTOR and Restores Normal Cellular Function in Alzheimer's Disease\n\nAbstract\nThis study investigates the effects of simufilam on mTOR signaling in lymphocytes from Alzheimer's disease patients. We found that simufilam suppresses overactive mTOR signaling and restores normal cellular function, providing a potential therapeutic mechanism for AD treatment.\n\nIntroduction\nMammalian target of rapamycin (mTOR) signaling is dysregulated in Alzheimer's disease, contributing to cellular dysfunction and neurodegeneration. Simufilam has shown promise in modulating mTOR activity.\n\nMethods\nPeripheral blood lymphocytes were isolated from AD patients and healthy controls. mTOR signaling was assessed using Western blot analysis and flow cytometry.\n\nResults\nSimufilam treatment significantly reduced mTOR phosphorylation and restored normal lymphocyte function in AD patients. The drug also improved cellular viability and reduced apoptosis.\n\nConclusion\nThese results demonstrate that simufilam can modulate mTOR signaling and restore cellular function in Alzheimer's disease, supporting its therapeutic potential.",
        "study_type": "preclinical", 
        "r_score": 0.68,
        "s_score": 0.75
    },
    {
        "pmcid": None,  # No PMCID available
        "pmid": "37512347",  # Example PMID
        "year": 2020,
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients",
        "description": "JPAD 2020 Phase 2a trial paper (PTI-125 reduces AD biomarkers)",
        "abstract": "This Phase 2a clinical trial evaluated the safety and efficacy of PTI-125 in patients with mild-to-moderate Alzheimer's disease. The study demonstrated that PTI-125 significantly reduced key biomarkers of AD, including tau phosphorylation and amyloid-beta levels, while showing good safety and tolerability.",
        "full_text": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients: A Phase 2a Clinical Trial\n\nAbstract\nThis Phase 2a clinical trial evaluated the safety and efficacy of PTI-125 in patients with mild-to-moderate Alzheimer's disease. The study demonstrated that PTI-125 significantly reduced key biomarkers of AD, including tau phosphorylation and amyloid-beta levels, while showing good safety and tolerability.\n\nIntroduction\nPTI-125 is a small molecule drug candidate that targets filamin A to reduce neuroinflammation and improve cognitive function in Alzheimer's disease.\n\nMethods\nThis was an open-label, single-arm Phase 2a study in 13 patients with mild-to-moderate AD. Patients received PTI-125 100mg twice daily for 28 days. Primary endpoints included safety and pharmacokinetics, with secondary endpoints assessing biomarker changes.\n\nResults\nPTI-125 was well-tolerated with no serious adverse events. The drug significantly reduced phosphorylated tau (pTau181) levels by 34% and amyloid-beta 42 (Aβ42) levels by 28% compared to baseline. Cognitive assessments showed improvement in ADAS-Cog scores.\n\nConclusion\nPTI-125 demonstrated safety and efficacy in reducing AD biomarkers, supporting further clinical development for Alzheimer's disease treatment.",
        "study_type": "clinical_trial",
        "r_score": 0.60,
        "s_score": 0.65
    }
]

class CassavaExtractionFocusedTest:
    """Focused test for Cassava extraction components."""
    
    def __init__(self):
        # Load environment variables first
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from tests.utils.env_loader import setup_test_environment
        setup_test_environment()
        
        # Reset the database engine to pick up new environment variables
        from ncfd.db.session import reset_engine
        reset_engine()
        
        self.test_start_time = datetime.now(timezone.utc)
        self.results = {
            "test_info": {
                "start_time": self.test_start_time.isoformat(),
                "test_type": "cassava_extraction_focused",
                "description": "Focused test on extraction, pattern detection, and quality gates"
            },
            "phases": {},
            "summary": {}
        }
        
    async def run_test(self):
        """Run the complete focused test."""
        logger.info("🧪 Starting Cassava Extraction Focused Test")
        logger.info("=" * 80)
        
        try:
            # Phase 1: Database setup and seeding
            await self._phase_1_database_setup()
            
            # Phase 2: Study card generation (extraction focus)
            await self._phase_2_study_card_generation()
            
            # Phase 3: Results validation
            await self._phase_3_validation()
            
            # Generate summary
            self._generate_summary()
            
            logger.info("✅ Cassava Extraction Focused Test completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
            raise
    
    async def _phase_1_database_setup(self):
        """Phase 1: Database setup and seeding."""
        logger.info("🗄️ Phase 1: Database setup and seeding")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Nuke and recreate database
            await self._nuke_database()
            
            # Create tables
            await self._create_tables()
            
            # Seed Cassava data
            await self._seed_cassava_data()
            
            # Seed the 3 specific studies
            await self._seed_cassava_studies()
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            self.results["phases"]["database_setup"] = {
                "status": "completed",
                "duration_seconds": duration,
                "studies_seeded": len(CASSAVA_STUDIES),
                "description": "Database nuked, recreated, and seeded with Cassava data"
            }
            
            logger.info(f"✅ Database setup completed in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            raise
    
    async def _nuke_database(self):
        """Nuke the database by dropping all tables."""
        logger.info("💥 Nuking database...")
        
        # Create engine
        engine = create_engine(os.getenv('POSTGRES_DSN'))
        
        # Drop all tables
        with engine.connect() as conn:
            # Drop tables in reverse dependency order
            tables_to_drop = [
                'pattern_detections', 'pattern_families', 'gate_assessments', 'gates',
                'factsheets', 'study_cards', 'document_text', 'documents', 'document_links',
                'trials', 'companies', 'assets', 'signals', 'scores', 'catalysts', 'labels', 'disclosures'
            ]
            
            for table in tables_to_drop:
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    logger.info(f"  Dropped table: {table}")
                except Exception as e:
                    logger.debug(f"  Table {table} not found or already dropped: {e}")
            
            conn.commit()
        
        logger.info("✅ Database nuked successfully")
    
    async def _create_tables(self):
        """Create all database tables."""
        logger.info("🏗️ Creating database tables...")
        
        # Create engine
        engine = create_engine(os.getenv('POSTGRES_DSN'))
        
        # Create all tables
        Base.metadata.create_all(engine)
        
        logger.info("✅ Database tables created successfully")
    
    async def _seed_cassava_data(self):
        """Seed basic Cassava company and trial data."""
        logger.info("🏢 Seeding Cassava company data...")
        
        with session_scope() as session:
            # Create Cassava company
            company = Company(
                company_id=2,
                name="Cassava Sciences, Inc.",
                name_norm="cassava sciences inc",
                cik="0001234567",
                lei="LEI123456789",
                state_incorp="Delaware",
                country_incorp="United States",
                sic="2834",
                website_domain="cassavasciences.com",
                created_at=datetime.now(timezone.utc)
            )
            session.add(company)
            
            # Create Cassava asset
            asset = Asset(
                asset_id=2,
                names={
                    "canonical": "simufilam",
                    "aliases": ["simufilam", "PTI-125", "filamin A inhibitor"]
                },
                moa="Filamin A inhibitor",
                target="Filamin A",
                modality="Small molecule",
                owner_company_id=2
            )
            session.add(asset)
            
            # Create Cassava trial
            trial = Trial(
                trial_id=2,
                nct_id="NCT05515666",
                brief_title="A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                sponsor_text="Cassava Sciences, Inc.",
                sponsor_company_id=2,
                phase="PHASE3",
                indication="Alzheimer's Disease",
                status="RECRUITING",
                is_pivotal=True,
                current_sha256="test_sha256_hash"
            )
            session.add(trial)
            
            session.commit()
            logger.info("✅ Seeded Cassava company, asset, and trial")
    
    async def _seed_cassava_studies(self):
        """Seed the 3 specific Cassava studies."""
        logger.info("📚 Seeding 3 specific Cassava studies...")
        
        with session_scope() as session:
            for i, study in enumerate(CASSAVA_STUDIES, 1):
                # Create document
                document = Document(
                    doc_id=20 + i,  # Start from 21
                    source_type="Paper",
                    pmid=study["pmid"],
                    pmcid=study["pmcid"],
                    title=study["title"],
                    r_score=study["r_score"],
                    s_score=study["s_score"],
                    r_tier="R2" if study["r_score"] >= 0.6 else "R1",
                    s_tier="S2" if study["s_score"] >= 0.6 else "S1",
                    status="parsed",
                    processing_stage="processed"
                )
                session.add(document)
                
                # Create document text
                document_text = DocumentText(
                    doc_id=20 + i,
                    abstract_text=study["abstract"],
                    fulltext_text=study["full_text"],
                    char_count_abstract=len(study["abstract"]) if study["abstract"] else 0,
                    char_count_fulltext=len(study["full_text"]) if study["full_text"] else 0
                )
                session.add(document_text)
                
                # Create document link to trial
                doc_link = DocumentLink(
                    doc_id=20 + i,
                    nct_id="NCT05515666",  # Cassava trial NCT ID
                    trial_id=2,  # Cassava trial
                    asset_id=2,  # Cassava asset
                    company_id=2,  # Cassava company
                    link_type="trial_document",
                    confidence=0.9
                )
                session.add(doc_link)
                
                logger.info(f"  ✅ Seeded study {i}: {study['title']}")
            
            session.commit()
            logger.info(f"✅ Seeded {len(CASSAVA_STUDIES)} Cassava studies")
    
    async def _phase_2_study_card_generation(self):
        """Phase 2: Study card generation (extraction focus)."""
        logger.info("📋 Phase 2: Study card generation (extraction focus)")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Load test configuration
            config_manager = ConfigManager()
            test_config = self._get_test_config()
            
            # Initialize orchestrator
            orchestrator = PipelineOrchestrator(test_config)
            
            # Run study card generation for the Cassava trial
            logger.info("Running study card generation for Cassava trial...")
            
            result = await orchestrator.run_study_card_generation(
                trial_list=[{"trial_id": 2}]  # Cassava trial
            )
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            self.results["phases"]["study_card_generation"] = {
                "status": "completed",
                "duration_seconds": duration,
                "result": result,
                "description": "Study card generation with extraction focus"
            }
            
            logger.info(f"✅ Study card generation completed in {duration:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Study card generation failed: {e}")
            raise
    
    async def _phase_3_validation(self):
        """Phase 3: Results validation."""
        logger.info("🔍 Phase 3: Results validation")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            with session_scope() as session:
                # Check study cards
                study_cards = session.query(StudyCard).all()
                logger.info(f"📊 Study cards created: {len(study_cards)}")
                
                # Check factsheets
                factsheets = session.query(Factsheet).all()
                logger.info(f"📊 Factsheets created: {len(factsheets)}")
                
                # Check patterns
                patterns = session.query(PatternDetection).all()
                logger.info(f"📊 Patterns detected: {len(patterns)}")
                
                # Check gate assessments
                gate_assessments = session.query(GateAssessment).all()
                logger.info(f"📊 Gate assessments: {len(gate_assessments)}")
                
                # Validate factsheet content
                await self._validate_factsheet_content(factsheets)
                
                # Validate study types
                await self._validate_study_types(factsheets)
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                self.results["phases"]["validation"] = {
                    "status": "completed",
                    "duration_seconds": duration,
                    "study_cards_count": len(study_cards),
                    "factsheets_count": len(factsheets),
                    "patterns_count": len(patterns),
                    "gate_assessments_count": len(gate_assessments),
                    "description": "Validation of extraction results"
                }
                
                logger.info(f"✅ Validation completed in {duration:.2f}s")
                
        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            raise
    
    async def _validate_factsheet_content(self, factsheets):
        """Validate factsheet content quality."""
        logger.info("🔍 Validating factsheet content...")
        
        for factsheet in factsheets:
            logger.info(f"  Factsheet {factsheet.factsheet_id}:")
            logger.info(f"    Study Type: {factsheet.study_type}")
            logger.info(f"    Sections: {list(factsheet.factsheet_sections.keys()) if factsheet.factsheet_sections else 'None'}")
            logger.info(f"    Provenance: {list(factsheet.provenance.keys()) if factsheet.provenance else 'None'}")
            logger.info(f"    Normalized Facts: {list(factsheet.normalized_facts.keys()) if factsheet.normalized_facts else 'None'}")
    
    async def _validate_study_types(self, factsheets):
        """Validate study type classification."""
        logger.info("🔍 Validating study type classification...")
        
        expected_types = ["preclinical", "preclinical", "clinical_trial"]
        
        for i, factsheet in enumerate(factsheets):
            expected_type = expected_types[i] if i < len(expected_types) else "unknown"
            actual_type = factsheet.study_type
            
            if actual_type == expected_type:
                logger.info(f"  ✅ Study {i+1}: Correctly classified as {actual_type}")
            else:
                logger.warning(f"  ⚠️ Study {i+1}: Expected {expected_type}, got {actual_type}")
    
    def _get_test_config(self):
        """Get test configuration."""
        return {
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
                "guardrails": {
                    "reject_off_topic": True,
                    "reject_high_risk": True,
                    "high_risk_threshold": 0.8,
                    "require_relevance": True,
                    "require_asset_or_indication": True,
                    "log_decisions": True,
                    "log_rejections": True
                },
                "validation": {
                    "strict_validation": False,
                    "fail_fast_on_validation": False,
                    "validation_error_action": "warn",
                },
            },
            "ctgov": {},
            "sec": {},
            "pubmed": {}
        }
    
    def _generate_summary(self):
        """Generate test summary."""
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - self.test_start_time).total_seconds()
        
        self.results["test_info"]["end_time"] = end_time.isoformat()
        self.results["test_info"]["total_duration_seconds"] = total_duration
        
        self.results["summary"] = {
            "status": "completed",
            "total_duration_seconds": total_duration,
            "phases_completed": len(self.results["phases"]),
            "database_retained": True,
            "description": "Focused test on extraction, pattern detection, and quality gates completed successfully"
        }
        
        logger.info("📊 Test Summary:")
        logger.info(f"  Total Duration: {total_duration:.2f}s")
        logger.info(f"  Phases Completed: {len(self.results['phases'])}")
        logger.info(f"  Database Retained: Yes (for inspection)")
        logger.info("=" * 80)


async def main():
    """Main test function."""
    test = CassavaExtractionFocusedTest()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())
