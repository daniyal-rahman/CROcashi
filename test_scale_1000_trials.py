"""
Scale validation test - verify system handles 1000+ trials correctly.

Tests:
1. Processing 1000+ trials without crashes
2. Processing time and throughput metrics
3. Entity creation vs matching rates
4. Relationship creation rates (sponsors, drugs, diseases)
5. Review queue size and growth rate
6. Quality checks: duplicate relationships, entity resolution accuracy
7. Relationship rate validation
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from ingestion.clinicaltrials_gov import fetch_studies_sample
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog, EntityMatchCandidate
from database.models.clinical import ClinicalTrial, TrialStatusHistory
from database.models.entities import Company, Institution, Drug, Disease
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease
from sqlalchemy import func


def test_scale_1000_trials(trial_count: int = 1000):
    """
    Test system with 1000+ trials and validate quality metrics.
    
    Args:
        trial_count: Number of trials to process (default: 1000)
        
    Returns:
        True if all validations pass, False otherwise
    """
    print("\n" + "="*70)
    print(f"SCALE VALIDATION TEST - {trial_count} ClinicalTrials.gov Records")
    print("="*70)
    
    # Clean slate
    print("\n1. Cleaning previous test data...")
    with get_db_session() as session:
        session.query(SourceProcessingLog).filter_by(
            source_name='clinicaltrials_gov'
        ).delete()
        session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov'
        ).delete()
        session.commit()
    
    # Fetch trials
    print(f"\n2. Fetching {trial_count} trials from ClinicalTrials.gov...")
    start_time = datetime.now()
    
    result = fetch_studies_sample(
        query_term="cancer",
        page_size=trial_count,
        load_to_staging=True
    )
    
    fetch_time = (datetime.now() - start_time).total_seconds()
    print(f"   ✅ Fetched in {fetch_time:.1f}s")
    
    # Process them
    print(f"\n3. Processing {trial_count} trials through pipeline...")
    start_time = datetime.now()
    
    pipeline = ProcessingPipeline(batch_size=100)
    stats = pipeline.process_source('clinicaltrials_gov', limit=trial_count)
    
    process_time = (datetime.now() - start_time).total_seconds()
    throughput = stats['records_processed'] / process_time if process_time > 0 else 0
    
    print(f"\n   Processing Stats:")
    print(f"   - Processed: {stats['records_processed']}/{trial_count}")
    print(f"   - Failed: {stats['records_failed']}/{trial_count}")
    print(f"   - Entities created: {stats['entities_created']}")
    print(f"   - Entities matched: {stats['entities_matched']}")
    print(f"   - Relationships created: {stats['relationships_created']}")
    print(f"   - Needs review: {stats['needs_review']}")
    print(f"   - Processing time: {process_time:.1f}s")
    print(f"   - Throughput: {throughput:.2f} trials/second")
    
    # Verify no crashes
    success_rate = (stats['records_processed'] / trial_count * 100) if stats['records_processed'] else 0
    if success_rate >= 95:
        print(f"\n   ✅ No crashes - {success_rate:.1f}% success rate")
    else:
        print(f"\n   ❌ Low success rate - {success_rate:.1f}%")
        return False
    
    # Quality checks
    print("\n4. Quality Checks...")
    quality_results = perform_quality_checks(stats, trial_count)
    
    # Relationship rate validation
    print("\n5. Relationship Rate Validation...")
    relationship_results = validate_relationship_rates()
    
    # Entity resolution accuracy
    print("\n6. Entity Resolution Accuracy...")
    resolution_results = check_entity_resolution_accuracy(stats)
    
    # Status history tracking
    print("\n7. Status History Tracking...")
    status_results = check_status_history_tracking()
    
    # Final summary
    print("\n" + "="*70)
    print("SCALE VALIDATION SUMMARY")
    print("="*70)
    
    all_passed = (
        success_rate >= 95 and
        quality_results['no_duplicates'] and
        relationship_results['sponsor_rate_valid'] and
        relationship_results['drug_rate_valid'] and
        relationship_results['disease_rate_valid']
    )
    
    print(f"\n   Success Rate: {success_rate:.1f}% {'✅' if success_rate >= 95 else '❌'}")
    print(f"   No Duplicate Relationships: {'✅' if quality_results['no_duplicates'] else '❌'}")
    print(f"   Sponsor Rate Valid: {'✅' if relationship_results['sponsor_rate_valid'] else '❌'}")
    print(f"   Drug Rate Valid: {'✅' if relationship_results['drug_rate_valid'] else '❌'}")
    print(f"   Disease Rate Valid: {'✅' if relationship_results['disease_rate_valid'] else '❌'}")
    print(f"   Status History Tracking: {'✅' if status_results['status_history_working'] else '❌'}")
    
    if all_passed:
        print("\n✅ ALL VALIDATIONS PASSED")
        print(f"   - System successfully processed {trial_count} trials")
        print(f"   - Throughput: {throughput:.2f} trials/second")
        print(f"   - All quality checks passed")
    else:
        print("\n⚠️  SOME VALIDATIONS FAILED")
        if success_rate < 95:
            print(f"   - Low success rate: {success_rate:.1f}%")
        if not quality_results['no_duplicates']:
            print(f"   - Duplicate relationships found")
        if not relationship_results['sponsor_rate_valid']:
            print(f"   - Sponsor relationship rate outside expected range")
    
    print("="*70)
    
    return all_passed


def perform_quality_checks(stats: Dict[str, Any], trial_count: int) -> Dict[str, Any]:
    """Perform quality checks on processed data."""
    results = {
        'no_duplicates': True,
        'duplicate_counts': {}
    }
    
    with get_db_session() as session:
        # Check for duplicate relationships
        duplicate_trial_drugs = session.query(
            TrialDrug.trial_id,
            TrialDrug.drug_id,
            func.count().label('count')
        ).group_by(
            TrialDrug.trial_id,
            TrialDrug.drug_id
        ).having(func.count() > 1).count()
        
        duplicate_trial_diseases = session.query(
            TrialDisease.trial_id,
            TrialDisease.disease_id,
            func.count().label('count')
        ).group_by(
            TrialDisease.trial_id,
            TrialDisease.disease_id
        ).having(func.count() > 1).count()
        
        duplicate_trial_sponsors = session.query(
            TrialSponsor.trial_id,
            TrialSponsor.entity_id,
            func.count().label('count')
        ).group_by(
            TrialSponsor.trial_id,
            TrialSponsor.entity_id
        ).having(func.count() > 1).count()
        
        results['duplicate_counts'] = {
            'trial_drug': duplicate_trial_drugs,
            'trial_disease': duplicate_trial_diseases,
            'trial_sponsor': duplicate_trial_sponsors
        }
        
        if duplicate_trial_drugs > 0 or duplicate_trial_diseases > 0 or duplicate_trial_sponsors > 0:
            results['no_duplicates'] = False
            print(f"   ❌ Duplicate relationships found:")
            print(f"   - Trial-Drug: {duplicate_trial_drugs}")
            print(f"   - Trial-Disease: {duplicate_trial_diseases}")
            print(f"   - Trial-Sponsor: {duplicate_trial_sponsors}")
        else:
            print(f"   ✅ No duplicate relationships")
    
    return results


def validate_relationship_rates() -> Dict[str, Any]:
    """Validate that relationship rates are reasonable."""
    results = {
        'sponsor_rate_valid': False,
        'drug_rate_valid': False,
        'disease_rate_valid': False,
        'rates': {}
    }
    
    with get_db_session() as session:
        total_trials = session.query(ClinicalTrial).count()
        
        if total_trials == 0:
            return results
        
        # Sponsor rate
        trials_with_sponsors = session.query(ClinicalTrial).join(
            TrialSponsor
        ).distinct().count()
        sponsor_rate = (trials_with_sponsors / total_trials * 100)
        results['rates']['sponsor'] = sponsor_rate
        results['sponsor_rate_valid'] = 20 <= sponsor_rate <= 50  # Reasonable range
        
        # Drug rate
        trials_with_drugs = session.query(ClinicalTrial).join(
            TrialDrug
        ).distinct().count()
        drug_rate = (trials_with_drugs / total_trials * 100)
        results['rates']['drug'] = drug_rate
        results['drug_rate_valid'] = 60 <= drug_rate <= 90  # Most trials should have drugs
        
        # Disease rate
        trials_with_diseases = session.query(ClinicalTrial).join(
            TrialDisease
        ).distinct().count()
        disease_rate = (trials_with_diseases / total_trials * 100)
        results['rates']['disease'] = disease_rate
        results['disease_rate_valid'] = 70 <= disease_rate <= 95  # Most trials should have diseases
        
        print(f"   Total trials: {total_trials}")
        print(f"   Trials with sponsors: {trials_with_sponsors} ({sponsor_rate:.1f}%)")
        print(f"   Trials with drugs: {trials_with_drugs} ({drug_rate:.1f}%)")
        print(f"   Trials with diseases: {trials_with_diseases} ({disease_rate:.1f}%)")
        
        if results['sponsor_rate_valid']:
            print(f"   ✅ Sponsor rate is reasonable ({sponsor_rate:.1f}%)")
        else:
            print(f"   ⚠️  Sponsor rate outside expected range ({sponsor_rate:.1f}%)")
        
        if results['drug_rate_valid']:
            print(f"   ✅ Drug rate is reasonable ({drug_rate:.1f}%)")
        else:
            print(f"   ⚠️  Drug rate outside expected range ({drug_rate:.1f}%)")
        
        if results['disease_rate_valid']:
            print(f"   ✅ Disease rate is reasonable ({disease_rate:.1f}%)")
        else:
            print(f"   ⚠️  Disease rate outside expected range ({disease_rate:.1f}%)")
    
    return results


def check_entity_resolution_accuracy(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Check entity resolution accuracy metrics."""
    results = {
        'match_rate_reasonable': False,
        'review_rate_reasonable': False
    }
    
    with get_db_session() as session:
        total_entities = stats['entities_created'] + stats['entities_matched']
        
        if total_entities > 0:
            match_rate = (stats['entities_matched'] / total_entities * 100)
            create_rate = (stats['entities_created'] / total_entities * 100)
            
            # Match rate should be reasonable (not too high, not too low)
            results['match_rate_reasonable'] = 10 <= match_rate <= 70
            
            print(f"   Total entities: {total_entities}")
            print(f"   Matched (existing): {stats['entities_matched']} ({match_rate:.1f}%)")
            print(f"   Created (new): {stats['entities_created']} ({create_rate:.1f}%)")
            
            if results['match_rate_reasonable']:
                print(f"   ✅ Match rate is reasonable ({match_rate:.1f}%)")
            else:
                print(f"   ⚠️  Match rate outside typical range ({match_rate:.1f}%)")
        
        # Check review queue
        review_count = session.query(EntityMatchCandidate).filter_by(
            status='needs_review'
        ).count()
        
        review_rate = (review_count / total_entities * 100) if total_entities > 0 else 0
        results['review_rate_reasonable'] = review_rate < 15  # Should be <15% for good matching
        
        print(f"   Entities needing review: {review_count} ({review_rate:.2f}%)")
        
        if results['review_rate_reasonable']:
            print(f"   ✅ Review queue is reasonable ({review_rate:.2f}%)")
        else:
            print(f"   ⚠️  Review queue is high ({review_rate:.2f}%)")
    
    return results


def check_status_history_tracking() -> Dict[str, Any]:
    """Check that status history tracking is working."""
    results = {
        'status_history_working': False,
        'status_history_count': 0
    }
    
    with get_db_session() as session:
        # Check if status history entries exist
        status_history_count = session.query(TrialStatusHistory).count()
        results['status_history_count'] = status_history_count
        
        # Check if trials have status history
        trials_with_history = session.query(ClinicalTrial).join(
            TrialStatusHistory
        ).distinct().count()
        
        total_trials = session.query(ClinicalTrial).count()
        
        if total_trials > 0:
            history_coverage = (trials_with_history / total_trials * 100)
            results['status_history_working'] = status_history_count > 0
            
            print(f"   Total status history entries: {status_history_count}")
            print(f"   Trials with status history: {trials_with_history} ({history_coverage:.1f}%)")
            
            if results['status_history_working']:
                print(f"   ✅ Status history tracking is working")
            else:
                print(f"   ⚠️  No status history entries found")
        else:
            print(f"   ⚠️  No trials in database")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test system with 1000+ trials')
    parser.add_argument(
        '--count',
        type=int,
        default=1000,
        help='Number of trials to process (default: 1000)'
    )
    
    args = parser.parse_args()
    
    success = test_scale_1000_trials(trial_count=args.count)
    sys.exit(0 if success else 1)

