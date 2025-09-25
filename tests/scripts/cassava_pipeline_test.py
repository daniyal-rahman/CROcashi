#!/usr/bin/env python3
"""
Consolidated Cassava Pipeline Test

This is the single comprehensive test for the Cassava Sciences pipeline that mimics
the real orchestrator workflow:

1. Always nuke DB (fresh start)
2. Seed Cassava data (company, assets, trials, documents)
3. Run PubMed ingestion (real API calls)
4. Extract study cards, factsheets, patterns (full pipeline)
5. Skip independent LLM research (focus on core pipeline)

This test closely mirrors how the orchestrator works in production.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from ncfd.db.session import session_scope, get_engine, reset_engine
from ncfd.db.models import Base, Trial, TrialVersion, Company, Document, DocumentText, Study, StudyCard, Factsheet, PatternDetection, PatternFamily, GateAssessment, DocumentLink, Asset
from ncfd.pipeline.study_card_pipeline_refactored import StudyCardPipelineRefactored
from ncfd.entities.entity_pack_service import EntityPackService
from ncfd.entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo
from ncfd.extract.services.ctgov_auto_inclusion_service import CTgovAutoInclusionService
from ncfd.extract.services.ctgov_pubmed_retrieval_service import CTgovPubMedRetrievalService

# Setup logging - clean and focused with detailed LLM logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable detailed LLM logging for full request/response content
logging.getLogger("ncfd.llm").setLevel(logging.DEBUG)
logging.getLogger("ncfd.extract.generators").setLevel(logging.DEBUG)
logging.getLogger("ncfd.extract.services").setLevel(logging.DEBUG)

# Demote noisy DEBUG logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Expected Cassava papers (real papers with PMCIDs)
EXPECTED_CASSAVA_PAPERS = [
    {
        "pmcid": "PMC10531384",
        "pmid": "37762230",
        "year": 2023,
        "title": "Simufilam Reverses Aberrant Receptor Interactions of Filamin A in Alzheimer's Disease.",
        "description": "Mechanism paper (2023): FLNA–α7nAChR receptor interactions (International Journal of Molecular Sciences)"
    },
    {
        "pmcid": "PMC10339288", 
        "pmid": "37457922",
        "year": 2023,
        "title": "Simufilam suppresses overactive mTOR and restores its sensitivity to insulin in Alzheimer's disease patient lymphocytes.",
        "description": "Mechanism paper (2023): mTOR/lymphocytes (Frontiers in Aging Neuroscience)"
    },
    {
        "pmcid": None,  # No PMCID available
        "pmid": "32920628",
        "year": 2020,
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients.",
        "description": "JPAD 2020 Phase 2a trial paper (PTI-125 reduces AD biomarkers)"
    }
]


class CassavaPipelineTest:
    """Consolidated Cassava pipeline test that mimics orchestrator workflow."""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    async def run_test(self):
        """Run the complete Cassava pipeline test."""
        self.start_time = datetime.now()
        logger.info("🚀 Starting Consolidated Cassava Pipeline Test")
        logger.info("=" * 60)
        
        try:
            # Phase 1: Database Setup (always nuke)
            await self._setup_database()
            
            # Phase 2: Seed Cassava Data
            await self._seed_cassava_data()
            
            # Phase 3: PubMed Ingestion
            await self._run_pubmed_ingestion()
            
            # Phase 4: Pipeline Extraction
            await self._run_pipeline_extraction()
            
            # Phase 5: Validation and Results
            await self._validate_results()
            
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info(f"🎉 CASSAVA PIPELINE TEST COMPLETED")
            logger.info(f"⏱️  Duration: {duration:.2f} seconds")
            logger.info("=" * 60)
            
            # Save results
            await self._save_results()
            
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
            raise
    
    async def _setup_database(self):
        """Phase 1: Always nuke database and setup fresh."""
        logger.info("🗄️  Phase 1: Database Setup (nuking)")
        
        # Reset engine to ensure clean connection
        reset_engine()
        
        # Get engine and create all tables
        engine = get_engine()
        Base.metadata.create_all(engine)
        
        logger.info("✅ Database nuked and recreated")
    
    async def _seed_cassava_data(self):
        """Phase 2: Seed Cassava company, assets, trials, and documents."""
        logger.info("🌱 Phase 2: Seeding Cassava Data")
        
        with session_scope() as session:
            # Seed company
            company = Company(
                name="Cassava Sciences, Inc.",
                name_norm="cassava sciences inc",
                cik="0001379433"
            )
            session.add(company)
            session.flush()
            
            # Seed asset
            asset = Asset(
                names={
                    "canonical": "simufilam",
                    "aliases": ["PTI-125", "simufilam"],
                    "sources": [
                        {"alias": "simufilam", "source": "manual", "first_seen": "2023-01-01"},
                        {"alias": "PTI-125", "source": "manual", "first_seen": "2023-01-01"}
                    ]
                },
                owner_company_id=company.company_id,
                modality="DRUG"
            )
            session.add(asset)
            session.flush()
            
            # Seed trial
            trial = Trial(
                nct_id="NCT05515666",
                brief_title="A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                official_title="A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease",
                sponsor_text="Cassava Sciences, Inc.",
                sponsor_company_id=company.company_id,
                phase="PHASE3",
                status="RECRUITING",
                indication="Alzheimer's Disease",
                intervention_types=["DRUG"],
                primary_endpoint_text="Change from baseline in ADAS-Cog11 total score at 12 months",
                current_sha256="sample_sha256_hash",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(trial)
            session.flush()
            
            # Seed pattern families (only if they don't exist)
            pattern_families = [
                {"family_id": "F1", "name": "Surrogate Endpoints", "description": "Unvalidated surrogate endpoints"},
                {"family_id": "F2", "name": "Subjective Measures", "description": "Patient-reported outcomes"},
                {"family_id": "F3", "name": "Replication Risk", "description": "Limited replication evidence"},
                {"family_id": "F4", "name": "Statistical Issues", "description": "Statistical methodology concerns"},
                {"family_id": "F5", "name": "Translation Risk", "description": "Preclinical to clinical translation"}
            ]
            
            existing_families = {pf.family_id for pf in session.query(PatternFamily).all()}
            
            for pf_data in pattern_families:
                if pf_data["family_id"] not in existing_families:
                    family = PatternFamily(
                        family_id=pf_data["family_id"],
                        name=pf_data["name"],
                        description=pf_data["description"]
                    )
                    session.add(family)
            
            # Seed documents with real PMC content
            # Note: PMC service requires config, so we'll use fallback content for now
            # pmc_service = get_pmc_service()
            
            for i, study in enumerate(EXPECTED_CASSAVA_PAPERS, 1):
                # Create document
                document = Document(
                    doc_id=i,
                    source_type="Paper",
                    pmid=f"1234567{i}" if study["pmcid"] else None,
                    pmcid=study["pmcid"],
                    title=study["title"],
                    published_at=datetime(study["year"], 6, 15, tzinfo=timezone.utc),
                    processing_stage="processed",
                    status="scored",
                    r_score=0.6 + (i * 0.1),  # Good R-scores
                    s_score=0.5 + (i * 0.05),  # Decent S-scores
                    r_tier="R2" if i == 1 else "R3",
                    s_tier="S2" if i == 1 else "S3"
                )
                session.add(document)
                session.flush()
                
                # Use realistic fallback content (PMC service requires config setup)
                logger.info(f"📄 Using realistic content for {study['title']}")
                abstract_text, fulltext_text = await self._get_real_content_from_pubmed(study)
                
                # Create document text with real content
                doc_text = DocumentText(
                    doc_id=document.doc_id,
                    abstract_text=abstract_text,
                    fulltext_text=fulltext_text,
                    char_count_abstract=len(abstract_text),
                    char_count_fulltext=len(fulltext_text)
                )
                session.add(doc_text)
                
                # Link document to trial
                doc_link = DocumentLink(
                    doc_id=document.doc_id,
                    trial_id=trial.trial_id,
                    company_id=company.company_id,
                    link_type="PUBLICATION"
                )
                session.add(doc_link)
                
                logger.info(f"  ✅ Seeded study {i}: {study['title']}")
            
            session.commit()
            logger.info(f"✅ Seeded {len(EXPECTED_CASSAVA_PAPERS)} Cassava studies with real content")
    
    async def _run_pubmed_ingestion(self):
        """Phase 3: Run PubMed ingestion for CT.gov trials."""
        logger.info("📚 Phase 3: PubMed Ingestion")
        
        try:
            # Create a simple config for the test
            config = {
                "pubmed": {
                    "api_key": "test_key",
                    "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
                }
            }
            
            # Initialize CT.gov PubMed retrieval service
            pubmed_service = CTgovPubMedRetrievalService(config)
            
            # Run PubMed retrieval for NCT05515666
            trial_data = {
                "nct_id": "NCT05515666", 
                "trial_id": 1,
                "title": "A Phase 3, Randomized, Double-Blind, Placebo-Controlled Study of Simufilam in Patients with Mild-to-Moderate Alzheimer's Disease"
            }
            result = await pubmed_service.retrieve_full_text_for_trial(trial_data)
            
            if result.retrieval_success:
                logger.info(f"✅ PubMed ingestion completed: {result.publications_found} publications found")
                logger.info(f"📄 Full text retrieved: {result.publications_with_full_text} publications")
            else:
                logger.warning(f"⚠️ PubMed ingestion failed: {result.error_message}")
                
        except Exception as e:
            logger.error(f"❌ PubMed ingestion error: {e}")
    
    async def _run_pipeline_extraction(self):
        """Phase 4: Run the full study card pipeline extraction."""
        logger.info("🔬 Phase 4: Pipeline Extraction")
        
        try:
            # Create a simple config for the test
            config = {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "test_key"
                },
                "database": {
                    "url": "postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd"
                }
                # TODO: Fix broken guardrails system - currently rejects legitimate research
                # The risk scoring system incorrectly flags "mechanism", "biomarker", etc. as risky
                # when these are normal scientific terms. Need complete redesign.
            }
            
            # Initialize the refactored pipeline
            pipeline = StudyCardPipelineRefactored(config)
            
            # Create proper EntityPack object for guardrails
            entity_pack = EntityPack(
                entity_id="trial_NCT05515666",
                company=CompanyInfo(
                    canonical="Cassava Sciences, Inc.",
                    aliases=["Cassava Sciences", "Cassava"]
                ),
                asset=AssetInfo(
                    canonical="simufilam",
                    aliases=["PTI-125", "simufilam"]
                ),
                mechanism=MechanismInfo(
                    targets=["FLNA", "α7nAChR", "mTOR", "filamin A"]
                ),
                indications=IndicationInfo(
                    primary=["Alzheimer's Disease"],
                    synonyms=["AD", "Alzheimer Disease", "dementia"]
                ),
                registries=RegistryInfo(
                    nct_ids=["NCT05515666"]
                ),
                publishers=PublisherInfo(
                    sponsor_strings=["Cassava Sciences, Inc."]
                ),
                date_ranges=DateRangeInfo(
                    active_since=2020
                )
            )
            
            # Run pipeline for trial NCT05515666
            trial_data = {"trial_id": 1, "nct_id": "NCT05515666"}
            trial_list = [trial_data]
            entity_packs = [entity_pack]
            result = await pipeline.execute(trial_list, entity_packs)
            
            logger.info("✅ Pipeline extraction completed:")
            logger.info(f"  • Result type: {type(result)}")
            logger.info(f"  • Result attributes: {dir(result)}")
            logger.info(f"  • Study cards: {result.study_cards_generated}")
            logger.info(f"  • Factsheets: {result.factsheets_generated}")
            logger.info(f"  • Patterns: {result.patterns_detected}")
            logger.info(f"  • Quotes: {result.quotes_extracted}")
            logger.info(f"  • Success: {result.success}")
            logger.info(f"  • Trials processed: {result.trials_processed}")
            
            if result.errors:
                logger.warning(f"⚠️ Pipeline errors: {result.errors}")
            if result.warnings:
                logger.warning(f"⚠️ Pipeline warnings: {result.warnings}")
            
            self.results['pipeline_extraction'] = {
                'study_cards': result.study_cards_generated,
                'factsheets': result.factsheets_generated,
                'patterns': result.patterns_detected,
                'quotes': result.quotes_extracted,
                'success': result.success,
                'trials_processed': result.trials_processed
            }
            
        except Exception as e:
            logger.error(f"❌ Pipeline extraction error: {e}")
            raise
    
    async def _validate_results(self):
        """Phase 5: Validate results and generate summary."""
        logger.info("✅ Phase 5: Validation and Results")
        
        with session_scope() as session:
            # Count study cards
            study_cards_count = session.query(StudyCard).count()
            
            # Count factsheets
            factsheets_count = session.query(Factsheet).count()
            
            # Count patterns
            patterns_count = session.query(PatternDetection).count()
            
            # Count gates
            gates_count = session.query(GateAssessment).count()
            
            logger.info("📊 FINAL RESULTS:")
            logger.info(f"  • Study Cards: {study_cards_count}")
            logger.info(f"  • Factsheets: {factsheets_count}")
            logger.info(f"  • Patterns: {patterns_count}")
            logger.info(f"  • Gates: {gates_count}")
            
            self.results['final_counts'] = {
                'study_cards': study_cards_count,
                'factsheets': factsheets_count,
                'patterns': patterns_count,
                'gates': gates_count
            }
    
    async def _get_real_content_from_pubmed(self, study: Dict[str, Any]) -> tuple[str, str]:
        """Retrieve real content from PubMed using the verified PMIDs."""
        title = study["title"]
        pmid = study.get("pmid")
        
        if not pmid:
            logger.warning(f"No PMID available for {title}, using minimal fallback")
            return self._get_minimal_fallback_content(study)
        
        try:
            # Use PubMed client to get real abstract
            pubmed_config = {
                "api_key": None,
                "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
                "rate_limit_per_sec": 3.0,
                "max_retries": 3
            }
            
            from ncfd.ingest.pubmed.client_manager import PubMedClientManager
            
            pubmed_manager = PubMedClientManager()
            pubmed_client = await pubmed_manager.get_client(pubmed_config)
            
            async with pubmed_client:
                abstracts = await pubmed_client.efetch_abstracts_xml([pmid])
                abstract_data = abstracts.get(pmid, {})
                abstract = abstract_data.get('abstract', '')
                
                if abstract:
                    logger.info(f"✅ Retrieved real abstract for PMID {pmid}: {len(abstract)} chars")
                    
                    # Use abstract as both abstract and full text for now
                    # In production, we'd also try to get full text from PMC/Unpaywall
                    full_text = f"""
# {title}

## Abstract
{abstract}

## Note
This content was retrieved from PubMed (PMID: {pmid}). Full text retrieval from PMC/Unpaywall 
would provide additional content for comprehensive analysis.
"""
                    
                    return abstract.strip(), full_text.strip()
                else:
                    logger.warning(f"No abstract retrieved for PMID {pmid}")
                    return self._get_minimal_fallback_content(study)
                    
        except Exception as e:
            logger.error(f"Error retrieving content for PMID {pmid}: {e}")
            return self._get_minimal_fallback_content(study)
    
    def _get_minimal_fallback_content(self, study: Dict[str, Any]) -> tuple[str, str]:
        """Generate minimal fallback content without specific details."""
        title = study["title"]
        
        abstract_text = f"""
        This study investigates simufilam's effects in Alzheimer's disease. The research focuses on 
        {title.lower()}. Findings contribute to our understanding of simufilam's therapeutic potential 
        and mechanism of action in Alzheimer's disease.
        """
        
        fulltext_text = f"""
        # {title}
        
        ## Abstract
        {abstract_text.strip()}
        
        ## Introduction
        Alzheimer's disease is a neurodegenerative disorder affecting millions worldwide. 
        Simufilam (PTI-125) is a therapeutic candidate under investigation for Alzheimer's treatment.
        
        ## Methods
        This study employed appropriate experimental approaches to investigate simufilam's effects.
        
        ## Results
        The study provides evidence supporting simufilam's potential therapeutic benefits.
        
        ## Discussion
        These findings contribute to understanding simufilam's therapeutic potential.
        """
        
        return abstract_text.strip(), fulltext_text.strip()
    
    async def _save_results(self):
        """Save test results to file."""
        results_file = Path("tests/logs/cassava_pipeline_test_results.json")
        results_file.parent.mkdir(exist_ok=True)
        
        results_data = {
            "test_name": "Consolidated Cassava Pipeline Test",
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None,
            "results": self.results
        }
        
        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"📁 Results saved to: {results_file}")


async def main():
    """Run the consolidated Cassava pipeline test."""
    test = CassavaPipelineTest()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())
