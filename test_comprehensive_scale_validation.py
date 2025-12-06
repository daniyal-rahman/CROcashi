"""
Comprehensive scale validation test - validates wiring and tests real data ingestion at scale.

Tests:
1. Wiring validation (ingestion → staging → processing → relationships)
2. Multi-source data ingestion (ClinicalTrials, PubMed, OpenFDA, PatentsView, SEC)
3. Scale processing (500+ records across sources)
4. Relationship creation validation
5. Data quality checks (duplicates, coverage, accuracy)
6. Performance metrics
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

sys.path.insert(0, str(Path(__file__).parent))

from ingestion.clinicaltrials_gov import fetch_studies_sample
from ingestion.pubmed import fetch_sample as pubmed_fetch
from ingestion.openfda import search_drugs as openfda_search
from ingestion.patentsview import search_patents as patentsview_search
from ingestion.sec_edgar import fetch_8k_filings_by_cik
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models import (
    SourceProcessingLog, EntityMatchCandidate,
    Company, Drug, Disease, ClinicalTrial, Publication, Patent, SECFiling
)
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationDrug, PublicationTrial, PublicationCompany,
    PatentDrug, PatentCompany,
    FilingCompany, FilingDrug
)
from sqlalchemy import func, distinct
from test_wiring_validation import WiringValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_wiring_and_scale():
    """
    Comprehensive test: wiring validation + scale data ingestion.
    
    Returns:
        True if all validations pass, False otherwise
    """
    print("\n" + "="*80)
    print("COMPREHENSIVE SCALE VALIDATION TEST")
    print("="*80)
    
    results = {
        'wiring': {},
        'ingestion': {},
        'processing': {},
        'relationships': {},
        'quality': {},
        'performance': {}
    }
    
    # Step 1: Wiring Validation
    print("\n" + "="*80)
    print("STEP 1: WIRING VALIDATION")
    print("="*80)
    
    validator = WiringValidator()
    wiring_results = validator.run_all_checks()
    results['wiring'] = wiring_results
    
    if wiring_results['summary']['status'] != 'PASS':
        print("\n⚠️  Wiring issues detected, but continuing with scale test...")
    
    # Step 2: Multi-Source Data Ingestion
    print("\n" + "="*80)
    print("STEP 2: MULTI-SOURCE DATA INGESTION")
    print("="*80)
    
    ingestion_results = ingest_multiple_sources()
    results['ingestion'] = ingestion_results
    
    # Step 3: Process All Sources
    print("\n" + "="*80)
    print("STEP 3: PROCESSING ALL SOURCES")
    print("="*80)
    
    processing_results = process_all_sources()
    results['processing'] = processing_results
    
    # Step 4: Relationship Validation
    print("\n" + "="*80)
    print("STEP 4: RELATIONSHIP VALIDATION")
    print("="*80)
    
    relationship_results = validate_all_relationships()
    results['relationships'] = relationship_results
    
    # Step 5: Data Quality Checks
    print("\n" + "="*80)
    print("STEP 5: DATA QUALITY CHECKS")
    print("="*80)
    
    quality_results = perform_comprehensive_quality_checks()
    results['quality'] = quality_results
    
    # Step 6: Performance Metrics
    print("\n" + "="*80)
    print("STEP 6: PERFORMANCE METRICS")
    print("="*80)
    
    performance_results = calculate_performance_metrics(processing_results)
    results['performance'] = performance_results
    
    # Final Summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    all_passed = generate_final_summary(results)
    
    return all_passed


def ingest_multiple_sources() -> Dict[str, Any]:
    """Ingest data from multiple sources into staging."""
    results = {
        'clinicaltrials_gov': {'count': 0, 'time': 0},
        'pubmed': {'count': 0, 'time': 0},
        'openfda': {'count': 0, 'time': 0},
        'patentsview': {'count': 0, 'time': 0},
        'sec_edgar': {'count': 0, 'time': 0}
    }
    
    # Clean previous test data
    print("\nCleaning previous test data...")
    with get_db_session() as session:
        for source in ['clinicaltrials_gov', 'pubmed', 'openfda', 'patentsview', 'sec_edgar']:
            session.query(SourceProcessingLog).filter_by(source_name=source).delete()
            session.query(StagingRawData).filter_by(source_system=source).delete()
        session.commit()
    
    # ClinicalTrials.gov - 200 trials
    print("\n1. Ingesting ClinicalTrials.gov data (200 trials)...")
    start = datetime.now()
    try:
        fetch_studies_sample(
            query_term="cancer",
            page_size=200,
            load_to_staging=True
        )
        with get_db_session() as session:
            count = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                processed=False
            ).count()
        results['clinicaltrials_gov'] = {
            'count': count,
            'time': (datetime.now() - start).total_seconds()
        }
        print(f"   ✅ Ingested {count} trials in {results['clinicaltrials_gov']['time']:.1f}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        logger.exception("ClinicalTrials ingestion failed")
    
    # PubMed - 100 publications
    print("\n2. Ingesting PubMed data (100 publications)...")
    start = datetime.now()
    try:
        pubmed_fetch(
            term="clinical trial AND cancer",
            retmax=100,
            load_to_staging=True
        )
        with get_db_session() as session:
            count = session.query(StagingRawData).filter_by(
                source_system='pubmed',
                processed=False
            ).count()
        results['pubmed'] = {
            'count': count,
            'time': (datetime.now() - start).total_seconds()
        }
        print(f"   ✅ Ingested {count} publications in {results['pubmed']['time']:.1f}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        logger.exception("PubMed ingestion failed")
    
    # OpenFDA - 100 drugs
    print("\n3. Ingesting OpenFDA data (100 drugs)...")
    start = datetime.now()
    try:
        openfda_search(
            query="*",
            limit=100,
            load_to_staging=True
        )
        with get_db_session() as session:
            count = session.query(StagingRawData).filter_by(
                source_system='openfda',
                processed=False
            ).count()
        results['openfda'] = {
            'count': count,
            'time': (datetime.now() - start).total_seconds()
        }
        print(f"   ✅ Ingested {count} drugs in {results['openfda']['time']:.1f}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        logger.exception("OpenFDA ingestion failed")
    
    # PatentsView - 100 patents
    print("\n4. Ingesting PatentsView data (100 patents)...")
    start = datetime.now()
    try:
        patentsview_search(
            query='{"_gte":{"patent_date":"2020-01-01"}}',
            limit=100,
            load_to_staging=True
        )
        with get_db_session() as session:
            count = session.query(StagingRawData).filter_by(
                source_system='patentsview',
                processed=False
            ).count()
        results['patentsview'] = {
            'count': count,
            'time': (datetime.now() - start).total_seconds()
        }
        print(f"   ✅ Ingested {count} patents in {results['patentsview']['time']:.1f}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        logger.exception("PatentsView ingestion failed")
    
    # SEC Edgar - 50 filings (using Moderna CIK as example)
    print("\n5. Ingesting SEC Edgar data (50 filings)...")
    start = datetime.now()
    try:
        fetch_8k_filings_by_cik(
            cik="1682852",  # Moderna CIK
            limit=50,
            load_to_staging=True
        )
        with get_db_session() as session:
            count = session.query(StagingRawData).filter_by(
                source_system='sec_edgar',
                processed=False
            ).count()
        results['sec_edgar'] = {
            'count': count,
            'time': (datetime.now() - start).total_seconds()
        }
        print(f"   ✅ Ingested {count} filings in {results['sec_edgar']['time']:.1f}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        logger.exception("SEC Edgar ingestion failed")
    
    total_ingested = sum(r['count'] for r in results.values())
    print(f"\n   Total records ingested: {total_ingested}")
    
    return results


def process_all_sources() -> Dict[str, Any]:
    """Process all sources through the pipeline."""
    results = {}
    pipeline = ProcessingPipeline(batch_size=50)
    
    sources = ['clinicaltrials_gov', 'pubmed', 'openfda', 'patentsview', 'sec_edgar']
    
    total_start = datetime.now()
    
    for source in sources:
        print(f"\nProcessing {source}...")
        start = datetime.now()
        
        try:
            stats = pipeline.process_source(source, limit=None)
            process_time = (datetime.now() - start).total_seconds()
            
            results[source] = {
                'processed': stats.get('records_processed', 0),
                'failed': stats.get('records_failed', 0),
                'entities_created': stats.get('entities_created', 0),
                'entities_matched': stats.get('entities_matched', 0),
                'relationships_created': stats.get('relationships_created', 0),
                'needs_review': stats.get('needs_review', 0),
                'time': process_time,
                'throughput': stats.get('records_processed', 0) / process_time if process_time > 0 else 0
            }
            
            print(f"   ✅ Processed {results[source]['processed']} records")
            print(f"      - Entities created: {results[source]['entities_created']}")
            print(f"      - Entities matched: {results[source]['entities_matched']}")
            print(f"      - Relationships: {results[source]['relationships_created']}")
            print(f"      - Time: {process_time:.1f}s ({results[source]['throughput']:.2f} records/s)")
            
        except Exception as e:
            print(f"   ❌ Error processing {source}: {e}")
            logger.exception(f"Processing failed for {source}")
            results[source] = {'error': str(e)}
    
    total_time = (datetime.now() - total_start).total_seconds()
    total_processed = sum(r.get('processed', 0) for r in results.values())
    
    results['total'] = {
        'processed': total_processed,
        'time': total_time,
        'throughput': total_processed / total_time if total_time > 0 else 0
    }
    
    print(f"\n   Total processed: {total_processed} records in {total_time:.1f}s")
    print(f"   Overall throughput: {results['total']['throughput']:.2f} records/s")
    
    return results


def validate_all_relationships() -> Dict[str, Any]:
    """Validate relationships across all sources."""
    results = {
        'trial_relationships': {},
        'publication_relationships': {},
        'patent_relationships': {},
        'filing_relationships': {},
        'duplicates': {},
        'coverage': {}
    }
    
    with get_db_session() as session:
        # Trial relationships
        total_trials = session.query(ClinicalTrial).count()
        if total_trials > 0:
            trials_with_sponsors = session.query(ClinicalTrial).join(
                TrialSponsor
            ).distinct().count()
            trials_with_drugs = session.query(ClinicalTrial).join(
                TrialDrug
            ).distinct().count()
            trials_with_diseases = session.query(ClinicalTrial).join(
                TrialDisease
            ).distinct().count()
            
            results['trial_relationships'] = {
                'total_trials': total_trials,
                'with_sponsors': trials_with_sponsors,
                'sponsor_rate': (trials_with_sponsors / total_trials * 100) if total_trials > 0 else 0,
                'with_drugs': trials_with_drugs,
                'drug_rate': (trials_with_drugs / total_trials * 100) if total_trials > 0 else 0,
                'with_diseases': trials_with_diseases,
                'disease_rate': (trials_with_diseases / total_trials * 100) if total_trials > 0 else 0
            }
            
            print(f"\nTrial Relationships:")
            print(f"   Total trials: {total_trials}")
            print(f"   With sponsors: {trials_with_sponsors} ({results['trial_relationships']['sponsor_rate']:.1f}%)")
            print(f"   With drugs: {trials_with_drugs} ({results['trial_relationships']['drug_rate']:.1f}%)")
            print(f"   With diseases: {trials_with_diseases} ({results['trial_relationships']['disease_rate']:.1f}%)")
        
        # Publication relationships
        total_pubs = session.query(Publication).count()
        if total_pubs > 0:
            pubs_with_drugs = session.query(Publication).join(
                PublicationDrug
            ).distinct().count()
            pubs_with_trials = session.query(Publication).join(
                PublicationTrial
            ).distinct().count()
            pubs_with_companies = session.query(Publication).join(
                PublicationCompany
            ).distinct().count()
            
            results['publication_relationships'] = {
                'total_pubs': total_pubs,
                'with_drugs': pubs_with_drugs,
                'drug_rate': (pubs_with_drugs / total_pubs * 100) if total_pubs > 0 else 0,
                'with_trials': pubs_with_trials,
                'trial_rate': (pubs_with_trials / total_pubs * 100) if total_pubs > 0 else 0,
                'with_companies': pubs_with_companies,
                'company_rate': (pubs_with_companies / total_pubs * 100) if total_pubs > 0 else 0
            }
            
            print(f"\nPublication Relationships:")
            print(f"   Total publications: {total_pubs}")
            print(f"   With drugs: {pubs_with_drugs} ({results['publication_relationships']['drug_rate']:.1f}%)")
            print(f"   With trials: {pubs_with_trials} ({results['publication_relationships']['trial_rate']:.1f}%)")
            print(f"   With companies: {pubs_with_companies} ({results['publication_relationships']['company_rate']:.1f}%)")
        
        # Patent relationships
        total_patents = session.query(Patent).count()
        if total_patents > 0:
            patents_with_drugs = session.query(Patent).join(
                PatentDrug
            ).distinct().count()
            patents_with_companies = session.query(Patent).join(
                PatentCompany
            ).distinct().count()
            
            results['patent_relationships'] = {
                'total_patents': total_patents,
                'with_drugs': patents_with_drugs,
                'drug_rate': (patents_with_drugs / total_patents * 100) if total_patents > 0 else 0,
                'with_companies': patents_with_companies,
                'company_rate': (patents_with_companies / total_patents * 100) if total_patents > 0 else 0
            }
            
            print(f"\nPatent Relationships:")
            print(f"   Total patents: {total_patents}")
            print(f"   With drugs: {patents_with_drugs} ({results['patent_relationships']['drug_rate']:.1f}%)")
            print(f"   With companies: {patents_with_companies} ({results['patent_relationships']['company_rate']:.1f}%)")
        
        # Filing relationships
        total_filings = session.query(SECFiling).count()
        if total_filings > 0:
            filings_with_companies = session.query(SECFiling).join(
                FilingCompany
            ).distinct().count()
            filings_with_drugs = session.query(SECFiling).join(
                FilingDrug
            ).distinct().count()
            
            results['filing_relationships'] = {
                'total_filings': total_filings,
                'with_companies': filings_with_companies,
                'company_rate': (filings_with_companies / total_filings * 100) if total_filings > 0 else 0,
                'with_drugs': filings_with_drugs,
                'drug_rate': (filings_with_drugs / total_filings * 100) if total_filings > 0 else 0
            }
            
            print(f"\nFiling Relationships:")
            print(f"   Total filings: {total_filings}")
            print(f"   With companies: {filings_with_companies} ({results['filing_relationships']['company_rate']:.1f}%)")
            print(f"   With drugs: {filings_with_drugs} ({results['filing_relationships']['drug_rate']:.1f}%)")
        
        # Check for duplicates
        duplicate_trial_drugs = session.query(
            TrialDrug.trial_id,
            TrialDrug.drug_id,
            func.count().label('count')
        ).group_by(
            TrialDrug.trial_id,
            TrialDrug.drug_id
        ).having(func.count() > 1).count()
        
        duplicate_trial_sponsors = session.query(
            TrialSponsor.trial_id,
            TrialSponsor.entity_id,
            func.count().label('count')
        ).group_by(
            TrialSponsor.trial_id,
            TrialSponsor.entity_id
        ).having(func.count() > 1).count()
        
        results['duplicates'] = {
            'trial_drug': duplicate_trial_drugs,
            'trial_sponsor': duplicate_trial_sponsors,
            'has_duplicates': duplicate_trial_drugs > 0 or duplicate_trial_sponsors > 0
        }
        
        print(f"\nDuplicate Check:")
        print(f"   Duplicate trial-drug relationships: {duplicate_trial_drugs}")
        print(f"   Duplicate trial-sponsor relationships: {duplicate_trial_sponsors}")
        
        if results['duplicates']['has_duplicates']:
            print(f"   ❌ Duplicates found!")
        else:
            print(f"   ✅ No duplicates")
    
    return results


def perform_comprehensive_quality_checks() -> Dict[str, Any]:
    """Perform comprehensive data quality checks."""
    results = {
        'entity_counts': {},
        'relationship_counts': {},
        'review_queue': {},
        'data_coverage': {}
    }
    
    with get_db_session() as session:
        # Entity counts
        results['entity_counts'] = {
            'companies': session.query(Company).count(),
            'drugs': session.query(Drug).count(),
            'diseases': session.query(Disease).count(),
            'trials': session.query(ClinicalTrial).count(),
            'publications': session.query(Publication).count(),
            'patents': session.query(Patent).count(),
            'filings': session.query(SECFiling).count()
        }
        
        print(f"\nEntity Counts:")
        for entity_type, count in results['entity_counts'].items():
            print(f"   {entity_type}: {count}")
        
        # Relationship counts
        results['relationship_counts'] = {
            'trial_sponsor': session.query(TrialSponsor).count(),
            'trial_drug': session.query(TrialDrug).count(),
            'trial_disease': session.query(TrialDisease).count(),
            'publication_drug': session.query(PublicationDrug).count(),
            'publication_trial': session.query(PublicationTrial).count(),
            'publication_company': session.query(PublicationCompany).count(),
            'patent_drug': session.query(PatentDrug).count(),
            'patent_company': session.query(PatentCompany).count(),
            'filing_company': session.query(FilingCompany).count(),
            'filing_drug': session.query(FilingDrug).count()
        }
        
        print(f"\nRelationship Counts:")
        for rel_type, count in results['relationship_counts'].items():
            print(f"   {rel_type}: {count}")
        
        # Review queue
        review_count = session.query(EntityMatchCandidate).filter_by(
            status='needs_review'
        ).count()
        
        total_entities = sum(results['entity_counts'].values())
        review_rate = (review_count / total_entities * 100) if total_entities > 0 else 0
        
        results['review_queue'] = {
            'count': review_count,
            'rate': review_rate,
            'reasonable': review_rate < 15
        }
        
        print(f"\nReview Queue:")
        print(f"   Entities needing review: {review_count} ({review_rate:.2f}%)")
        if results['review_queue']['reasonable']:
            print(f"   ✅ Review queue is reasonable")
        else:
            print(f"   ⚠️  Review queue is high")
    
    return results


def calculate_performance_metrics(processing_results: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate performance metrics."""
    results = {
        'throughput': {},
        'efficiency': {},
        'scalability': {}
    }
    
    # Calculate throughput per source
    for source, stats in processing_results.items():
        if source != 'total' and isinstance(stats, dict) and 'throughput' in stats:
            results['throughput'][source] = stats['throughput']
    
    # Overall metrics
    if 'total' in processing_results:
        total_stats = processing_results['total']
        results['efficiency'] = {
            'total_records': total_stats.get('processed', 0),
            'total_time': total_stats.get('time', 0),
            'overall_throughput': total_stats.get('throughput', 0)
        }
    
    print(f"\nPerformance Metrics:")
    print(f"   Overall throughput: {results['efficiency'].get('overall_throughput', 0):.2f} records/s")
    
    return results


def generate_final_summary(results: Dict[str, Any]) -> bool:
    """Generate final summary and determine if all tests passed."""
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)
    
    all_passed = True
    
    # Wiring
    wiring_status = results['wiring'].get('summary', {}).get('status', 'UNKNOWN')
    print(f"\n1. Wiring Validation: {wiring_status}")
    if wiring_status != 'PASS':
        all_passed = False
        for issue in results['wiring'].get('summary', {}).get('issues', []):
            print(f"   ❌ {issue}")
    
    # Ingestion
    total_ingested = sum(r.get('count', 0) for r in results['ingestion'].values())
    print(f"\n2. Data Ingestion: {total_ingested} records ingested")
    if total_ingested < 400:  # Expect at least 400 records
        print(f"   ⚠️  Lower than expected ingestion count")
        all_passed = False
    
    # Processing
    total_processed = results['processing'].get('total', {}).get('processed', 0)
    print(f"\n3. Processing: {total_processed} records processed")
    if total_processed < 400:
        print(f"   ⚠️  Lower than expected processing count")
        all_passed = False
    
    # Relationships
    has_duplicates = results['relationships'].get('duplicates', {}).get('has_duplicates', False)
    print(f"\n4. Relationships: {'✅ No duplicates' if not has_duplicates else '❌ Duplicates found'}")
    if has_duplicates:
        all_passed = False
    
    # Quality
    review_reasonable = results['quality'].get('review_queue', {}).get('reasonable', False)
    print(f"\n5. Data Quality: {'✅ Review queue reasonable' if review_reasonable else '⚠️  Review queue high'}")
    
    # Performance
    throughput = results['performance'].get('efficiency', {}).get('overall_throughput', 0)
    print(f"\n6. Performance: {throughput:.2f} records/s")
    if throughput < 1.0:
        print(f"   ⚠️  Low throughput")
        all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL VALIDATIONS PASSED")
    else:
        print("⚠️  SOME VALIDATIONS FAILED")
    print("="*80)
    
    return all_passed


if __name__ == "__main__":
    success = test_wiring_and_scale()
    sys.exit(0 if success else 1)

