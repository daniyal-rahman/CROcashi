#!/usr/bin/env python3
"""
Comprehensive test for CT.gov + PubMed ingestion for Cassava Sciences trials.

This test:
1. Queries CT.gov for all Cassava/Simufilam trials
2. Stores trial data in the test database
3. Uses the orchestrator to ingest PubMed literature for these trials
4. Shows all results and relationships
5. Cleans up the database after the test

Usage:
    python tests/scripts/cassava_ctgov_pubmed_test.py
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

import requests
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import our modules
from ncfd.db.session import session_scope, get_engine
from ncfd.db.models import Base, Trial, Company, Document, Study, DocumentLink, TrialDocCandidate
from ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator
from ncfd.pipeline.pubmed_pipeline import PubMedPipeline

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CT.gov API configuration
CTG_API = "https://clinicaltrials.gov/api/v2/studies"
CASSAVA_QUERY = '("Cassava Sciences" OR Simufilam OR "PTI-125" OR "PTI 125" OR "filamin A inhibitor")'


def ctgov_search_all(query_term: str, page_size: int = 200) -> List[Dict[str, Any]]:
    """
    Pull all studies matching a query term from CT.gov v2 (handles pagination).
    """
    params = {
        "query.term": query_term,
        "pageSize": page_size,
        "format": "json",
        "countTotal": "true",
    }

    studies = []
    page_token = None
    while True:
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(CTG_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        studies.extend(data.get("studies", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return studies


def _get(d: Dict[str, Any], path: List[str], default=None):
    """Helper to safely get nested dictionary values."""
    cur = d
    for k in path:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
    return default if cur is None else cur


def extract_trial_data(study: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant trial data from CT.gov study response."""
    ps = study.get("protocolSection", {})
    idm = ps.get("identificationModule", {})
    status = ps.get("statusModule", {})
    design = ps.get("designModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {})
    conds = ps.get("conditionsModule", {}) or {}
    arms = ps.get("armsInterventionsModule", {}) or {}
    intervs = []

    # Try both possible places interventions may appear
    for inv in (arms.get("interventions") or []):
        name = inv.get("name")
        if name:
            intervs.append(name)
    if not intervs:
        im = ps.get("interventionsModule", {}) or {}
        for inv in (im.get("interventions") or []):
            name = inv.get("name")
            if name:
                intervs.append(name)

    return {
        "nct_id": idm.get("nctId"),
        "title": idm.get("briefTitle") or idm.get("officialTitle"),
        "overall_status": status.get("overallStatus"),
        "phase": (design.get("phases") or []),  # v2 often returns a list
        "study_type": design.get("studyType"),
        "lead_sponsor": _get(sponsor, ["leadSponsor", "name"]),
        "conditions": conds.get("conditions") or [],
        "interventions": intervs,
        "start_date": _get(status, ["startDateStruct", "date"]),
        "primary_completion_date": _get(status, ["primaryCompletionDateStruct", "date"]),
        "completion_date": _get(status, ["completionDateStruct", "date"]),
        "last_update_posted": _get(status, ["lastUpdatePostDateStruct", "date"]),
        "has_results": "resultsSection" in study or study.get("hasResults", False),
        "raw_data": study  # Store full raw data for reference
    }


def looks_like_cassava(trial_data: Dict[str, Any]) -> bool:
    """Check if trial data looks like it's related to Cassava/Simufilam."""
    hay = " ".join([
        trial_data.get("title") or "",
        " ".join(trial_data.get("interventions") or []),
        trial_data.get("lead_sponsor") or "",
    ]).lower()
    needles = ["cassava sciences", "simufilam", "pti-125", "pti 125"]
    return any(n in hay for n in needles)


def fetch_cassava_trials() -> List[Dict[str, Any]]:
    """Fetch all Cassava/Simufilam trials from CT.gov."""
    logger.info("Fetching Cassava trials from CT.gov...")
    studies = ctgov_search_all(CASSAVA_QUERY)
    trial_data = [extract_trial_data(s) for s in studies]
    # Filter to only obvious Cassava/Simufilam hits
    cassava_trials = [t for t in trial_data if looks_like_cassava(t)]
    logger.info(f"Found {len(cassava_trials)} Cassava/Simufilam trials")
    return cassava_trials


def create_or_get_company(session: Session, company_name: str) -> int:
    """Create or get company by name, return company_id."""
    # Try to find existing company
    existing = session.query(Company).filter(
        Company.name_norm.ilike(f"%{company_name.lower()}%")
    ).first()
    
    if existing:
        return existing.company_id
    
    # Create new company
    company = Company(
        name=company_name,
        name_norm=company_name.lower(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(company)
    session.flush()  # Get the ID
    return company.company_id


def store_trial_in_db(session: Session, trial_data: Dict[str, Any]) -> int:
    """Store trial data in database, return trial_id."""
    # Create or get company
    sponsor_name = trial_data.get("lead_sponsor", "Unknown Sponsor")
    company_id = create_or_get_company(session, sponsor_name)
    
    # Convert phase list to string and map to allowed values
    phase = trial_data.get("phase", [])
    if isinstance(phase, list):
        # Map CT.gov phases to database allowed phases
        phase_mapping = {
            "PHASE1": "PHASE2",  # Map PHASE1 to PHASE2 for database constraint
            "PHASE2": "PHASE2",
            "PHASE2B": "PHASE2B", 
            "PHASE2/3": "PHASE2_3",
            "PHASE3": "PHASE3",
            "PHASE4": "PHASE4"
        }
        mapped_phases = []
        for p in phase:
            if p in phase_mapping:
                mapped_phases.append(phase_mapping[p])
            else:
                # Default to PHASE2 for unknown phases
                mapped_phases.append("PHASE2")
        phase_str = ",".join(mapped_phases) if mapped_phases else None
    else:
        # Single phase value
        phase_mapping = {
            "PHASE1": "PHASE2",
            "PHASE2": "PHASE2",
            "PHASE2B": "PHASE2B", 
            "PHASE2/3": "PHASE2_3",
            "PHASE3": "PHASE3",
            "PHASE4": "PHASE4"
        }
        phase_str = phase_mapping.get(str(phase), "PHASE2") if phase else None
    
    # Convert dates
    def parse_date(date_str):
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        except:
            return None
    
    # Check if trial already exists
    existing_trial = session.query(Trial).filter(
        Trial.nct_id == trial_data["nct_id"]
    ).first()
    
    if existing_trial:
        logger.info(f"Trial {trial_data['nct_id']} already exists, updating...")
        # Update existing trial
        existing_trial.brief_title = trial_data.get("title")
        existing_trial.sponsor_text = sponsor_name
        existing_trial.sponsor_company_id = company_id
        existing_trial.phase = phase_str
        existing_trial.indication = ", ".join(trial_data.get("conditions", []))
        existing_trial.status = trial_data.get("overall_status")
        existing_trial.est_primary_completion_date = parse_date(trial_data.get("primary_completion_date"))
        existing_trial.first_posted_date = parse_date(trial_data.get("start_date"))
        existing_trial.last_update_posted_date = parse_date(trial_data.get("last_update_posted"))
        existing_trial.has_results = trial_data.get("has_results", False)
        existing_trial.intervention_types = trial_data.get("interventions")
        existing_trial.updated_at = datetime.now(timezone.utc)
        existing_trial.current_sha256 = f"ctgov_{trial_data['nct_id']}_{datetime.now(timezone.utc).timestamp()}"
        return existing_trial.trial_id
    
    # Create new trial
    trial = Trial(
        nct_id=trial_data["nct_id"],
        brief_title=trial_data.get("title"),
        sponsor_text=sponsor_name,
        sponsor_company_id=company_id,
        phase=phase_str,
        indication=", ".join(trial_data.get("conditions", [])),
        status=trial_data.get("overall_status"),
        est_primary_completion_date=parse_date(trial_data.get("primary_completion_date")),
        first_posted_date=parse_date(trial_data.get("start_date")),
        last_update_posted_date=parse_date(trial_data.get("last_update_posted")),
        has_results=trial_data.get("has_results", False),
        intervention_types=trial_data.get("interventions"),
        current_sha256=f"ctgov_{trial_data['nct_id']}_{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(trial)
    session.flush()  # Get the ID
    return trial.trial_id


def setup_test_database():
    """Setup test database with all tables."""
    logger.info("Setting up test database...")
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Test database setup complete")


def clear_test_database():
    """Clear all data from test database."""
    logger.info("Clearing test database...")
    with session_scope() as session:
        # Delete in order to respect foreign key constraints
        session.execute(text("DELETE FROM trial_doc_candidates"))
        session.execute(text("DELETE FROM document_links"))
        session.execute(text("DELETE FROM document_entities"))
        session.execute(text("DELETE FROM document_citations"))
        session.execute(text("DELETE FROM pubmed_meta"))
        session.execute(text("DELETE FROM pmc_meta"))
        session.execute(text("DELETE FROM documents"))
        session.execute(text("DELETE FROM studies"))
        session.execute(text("DELETE FROM trial_versions"))
        session.execute(text("DELETE FROM trials"))
        session.execute(text("DELETE FROM company_aliases"))
        session.execute(text("DELETE FROM companies"))
        session.commit()
    logger.info("Test database cleared")


def query_trials_from_db(session: Session) -> List[Dict[str, Any]]:
    """Query all trials from database with their details."""
    trials = session.query(Trial).all()
    results = []
    
    for trial in trials:
        trial_data = {
            "trial_id": trial.trial_id,
            "nct_id": trial.nct_id,
            "title": trial.brief_title,
            "sponsor": trial.sponsor_text,
            "phase": trial.phase,
            "indication": trial.indication,
            "status": trial.status,
            "has_results": trial.has_results,
            "interventions": trial.intervention_types,
            "created_at": trial.created_at.isoformat() if trial.created_at else None,
            "studies_count": len(trial.studies),
            "documents_count": 0,
            "pubmed_documents": []
        }
        
        # Count documents linked to this trial
        doc_links = session.query(DocumentLink).filter(
            DocumentLink.trial_id == trial.trial_id
        ).all()
        
        trial_data["documents_count"] = len(doc_links)
        
        # Get PubMed documents
        for link in doc_links:
            if link.doc_id:
                doc = session.query(Document).filter(
                    Document.doc_id == link.doc_id
                ).first()
                if doc and doc.source_type == "Paper":
                    trial_data["pubmed_documents"].append({
                        "doc_id": doc.doc_id,
                        "pmid": doc.pmid,
                        "title": doc.title,
                        "published_at": doc.published_at.isoformat() if doc.published_at else None,
                        "status": doc.status
                    })
        
        results.append(trial_data)
    
    return results


def run_pubmed_ingestion_for_trials(trial_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run PubMed ingestion for the given trials using the orchestrator."""
    logger.info("Setting up PubMed ingestion...")
    
    # Create configuration for PubMed pipeline
    pubmed_config = {
        "asset_names": ["simufilam", "PTI-125", "PTI 125", "filamin A inhibitor"],
        "indications": ["Alzheimer's disease", "dementia", "cognitive impairment", "Alzheimer"],
        "client_config": {
            "rate_limit_requests_per_minute": 60,
            "batch_size": 20,
            "max_retries": 3,
            "timeout_seconds": 30,
            "api_key": os.getenv("PUBMED_API_KEY"),
            "email": os.getenv("PUBMED_EMAIL", "test@example.com"),
            "tool": "NCFD"
        },
        "retrieval": {
            "backend": "bm25",
            "max_docs_per_trial": 50,
            "min_relevance_score": 0.1
        },
        "enable_stages": ["U1"],
        "enable_oa_detection": False  # Skip OA for this test
    }
    
    # Create trial configurations for PubMed ingestion
    trial_configs = []
    for trial_data in trial_data_list:
        # Extract asset names from interventions
        interventions = trial_data.get("interventions", [])
        asset_names = []
        for intervention in interventions:
            if intervention:
                # Look for drug names in the intervention
                intervention_lower = intervention.lower()
                if any(drug in intervention_lower for drug in ["simufilam", "pti-125", "pti 125"]):
                    asset_names.extend(["simufilam", "PTI-125"])
                else:
                    # Add the intervention as a potential asset
                    asset_names.append(intervention)
        
        # Extract indications from conditions
        conditions = trial_data.get("conditions", [])
        indications = []
        for condition in conditions:
            if condition:
                indications.append(condition)
        
        # Add common Alzheimer's terms if not present
        if not any("alzheimer" in ind.lower() for ind in indications):
            indications.extend(["Alzheimer's disease", "dementia", "cognitive impairment"])
        
        trial_configs.append({
            "trial_id": trial_data["nct_id"],
            "asset_names": list(set(asset_names)) if asset_names else ["simufilam", "PTI-125"],
            "indications": list(set(indications)) if indications else ["Alzheimer's disease", "dementia"],
            "max_results": 50
        })
    
    logger.info(f"Created {len(trial_configs)} trial configurations for PubMed ingestion")
    
    # Create orchestrator configuration
    orchestrator_config = {
        "pubmed": pubmed_config,
        "worker_id": "cassava_test"
    }
    
    # Initialize orchestrator
    orchestrator = UnifiedPipelineOrchestrator(orchestrator_config)
    
    # Run PubMed pipeline
    logger.info("Running PubMed pipeline...")
    try:
        # Use the orchestrator's PubMed execution method
        result = orchestrator._execute_pubmed_pipeline(force_full_scan=True)
        
        if result and result.success:
            logger.info(f"PubMed pipeline completed successfully: {result.documents_processed} documents processed")
            return {
                "success": True,
                "documents_processed": result.documents_processed,
                "documents_failed": result.documents_failed,
                "errors": result.errors or [],
                "warnings": result.warnings or []
            }
        else:
            logger.error(f"PubMed pipeline failed: {result.errors if result else 'Unknown error'}")
            return {
                "success": False,
                "documents_processed": 0,
                "documents_failed": 0,
                "errors": result.errors if result else ["Unknown error"],
                "warnings": []
            }
    except Exception as e:
        logger.error(f"Error running PubMed pipeline: {str(e)}", exc_info=True)
        return {
            "success": False,
            "documents_processed": 0,
            "documents_failed": 0,
            "errors": [str(e)],
            "warnings": []
        }


def print_results(trials_data: List[Dict[str, Any]], pubmed_result: Dict[str, Any]):
    """Print comprehensive results."""
    print("\n" + "="*80)
    print("CASSAVA CT.GOV + PUBMED INGESTION TEST RESULTS")
    print("="*80)
    
    print(f"\n📊 SUMMARY:")
    print(f"  • CT.gov trials found: {len(trials_data)}")
    print(f"  • PubMed ingestion success: {pubmed_result['success']}")
    print(f"  • Documents processed: {pubmed_result['documents_processed']}")
    print(f"  • Documents failed: {pubmed_result['documents_failed']}")
    
    if pubmed_result['errors']:
        print(f"  • Errors: {len(pubmed_result['errors'])}")
        for error in pubmed_result['errors']:
            print(f"    - {error}")
    
    if pubmed_result['warnings']:
        print(f"  • Warnings: {len(pubmed_result['warnings'])}")
        for warning in pubmed_result['warnings']:
            print(f"    - {warning}")
    
    print(f"\n🔬 CT.GOV TRIALS:")
    for i, trial in enumerate(trials_data, 1):
        print(f"\n  {i}. {trial['nct_id']}: {trial['title']}")
        print(f"     Sponsor: {trial['sponsor']}")
        print(f"     Phase: {trial['phase']}")
        print(f"     Status: {trial['status']}")
        print(f"     Indication: {trial['indication']}")
        print(f"     Interventions: {', '.join(trial['interventions']) if trial['interventions'] else 'None'}")
        print(f"     Has Results: {trial['has_results']}")
        print(f"     Studies in DB: {trial['studies_count']}")
        print(f"     Documents linked: {trial['documents_count']}")
        
        if trial['pubmed_documents']:
            print(f"     PubMed Documents:")
            for doc in trial['pubmed_documents'][:5]:  # Show first 5
                print(f"       - PMID {doc['pmid']}: {doc['title'][:80]}...")
            if len(trial['pubmed_documents']) > 5:
                print(f"       ... and {len(trial['pubmed_documents']) - 5} more")
    
    print(f"\n📚 DATABASE QUERIES:")
    print(f"  • Total trials in database: {len(trials_data)}")
    total_docs = sum(trial['documents_count'] for trial in trials_data)
    print(f"  • Total documents linked: {total_docs}")
    total_pubmed = sum(len(trial['pubmed_documents']) for trial in trials_data)
    trials_with_docs = sum(1 for trial in trials_data if trial['documents_count'] > 0)
    print(f"  • Total PubMed documents: {total_pubmed}")
    print(f"  • Trials with document links: {trials_with_docs}")


def main():
    """Main test function."""
    logger.info("Starting Cassava CT.gov + PubMed ingestion test...")
    
    try:
        # Setup test database
        setup_test_database()
        
        # Clear any existing data
        clear_test_database()
        
        # Fetch Cassava trials from CT.gov
        cassava_trials = fetch_cassava_trials()
        
        if not cassava_trials:
            logger.warning("No Cassava trials found!")
            return
        
        # Store trials in database
        logger.info("Storing trials in database...")
        with session_scope() as session:
            for trial_data in cassava_trials:
                trial_id = store_trial_in_db(session, trial_data)
                trial_data["trial_id"] = trial_id
                logger.info(f"Stored trial {trial_data['nct_id']} with ID {trial_id}")
        
        # Run PubMed ingestion
        pubmed_result = run_pubmed_ingestion_for_trials(cassava_trials)
        
        # Query results from database
        logger.info("Querying results from database...")
        with session_scope() as session:
            trials_data = query_trials_from_db(session)
        
        # Print comprehensive results
        print_results(trials_data, pubmed_result)
        
        # Save results to file
        results_file = project_root / "tests" / "logs" / "cassava_test_results.json"
        results_file.parent.mkdir(exist_ok=True)
        
        results_data = {
            "test_timestamp": datetime.now(timezone.utc).isoformat(),
            "ctgov_trials": cassava_trials,
            "database_trials": trials_data,
            "pubmed_result": pubmed_result
        }
        
        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2, default=str)
        
        logger.info(f"Results saved to: {results_file}")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        raise
    finally:
        # Clean up database
        logger.info("Cleaning up test database...")
        clear_test_database()
        logger.info("Test completed!")


if __name__ == "__main__":
    main()
