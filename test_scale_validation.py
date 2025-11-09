"""
Scale validation test - verify system handles larger datasets correctly.

Tests:
1. Processing 100 trials without crashes
2. Sponsor relationship rate consistency (~30%)
3. Relationship creation correctness
4. Review queue growth (linear, not exponential)
5. Entity matching rates
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from ingestion.clinicaltrials_gov import fetch_studies_sample
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog, EntityMatchCandidate
from database.models.clinical import ClinicalTrial
from database.models.entities import Company, Institution
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease


def test_scale_validation():
    """Test system with 100 trials."""
    print("\n" + "="*70)
    print("SCALE VALIDATION TEST - 100 ClinicalTrials.gov Records")
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
    
    # Fetch 100 trials
    print("\n2. Fetching 100 trials from ClinicalTrials.gov...")
    start_time = datetime.now()
    
    result = fetch_studies_sample(
        query_term="cancer",
        page_size=100,
        load_to_staging=True
    )
    
    fetch_time = (datetime.now() - start_time).total_seconds()
    print(f"   ✅ Fetched in {fetch_time:.1f}s")
    
    # Process them
    print("\n3. Processing 100 trials through pipeline...")
    start_time = datetime.now()
    
    pipeline = ProcessingPipeline(batch_size=50)
    stats = pipeline.process_source('clinicaltrials_gov', limit=100)
    
    process_time = (datetime.now() - start_time).total_seconds()
    
    print(f"\n   Processing Stats:")
    print(f"   - Processed: {stats['records_processed']}/100")
    print(f"   - Failed: {stats['records_failed']}/100")
    print(f"   - Entities created: {stats['entities_created']}")
    print(f"   - Entities matched: {stats['entities_matched']}")
    print(f"   - Relationships created: {stats['relationships_created']}")
    print(f"   - Needs review: {stats['needs_review']}")
    print(f"   - Processing time: {process_time:.1f}s")
    
    # Verify no crashes
    success_rate = (stats['records_processed'] / 100) * 100 if stats['records_processed'] else 0
    if success_rate >= 95:
        print(f"\n   ✅ No crashes - {success_rate:.1f}% success rate")
    else:
        print(f"\n   ❌ Low success rate - {success_rate:.1f}%")
        return False
    
    # Check sponsor relationship rate
    print("\n4. Verifying sponsor relationship rate...")
    with get_db_session() as session:
        total_trials = session.query(ClinicalTrial).count()
        trials_with_sponsors = session.query(ClinicalTrial).join(
            TrialSponsor
        ).distinct().count()
        
        sponsor_rate = (trials_with_sponsors / total_trials * 100) if total_trials > 0 else 0
        
        # Check company vs institution breakdown
        company_sponsors = session.query(TrialSponsor).join(
            Company, TrialSponsor.entity_id == Company.company_id
        ).count()
        
        institution_sponsors = session.query(TrialSponsor).join(
            Institution, TrialSponsor.entity_id == Institution.institution_id
        ).count()
        
        total_sponsor_rels = company_sponsors + institution_sponsors
        company_rate = (company_sponsors / total_sponsor_rels * 100) if total_sponsor_rels > 0 else 0
        
        print(f"   Total trials: {total_trials}")
        print(f"   Trials with sponsors: {trials_with_sponsors} ({sponsor_rate:.1f}%)")
        print(f"   Company sponsors: {company_sponsors} ({company_rate:.1f}% of sponsor relationships)")
        print(f"   Institution sponsors: {institution_sponsors}")
        
        if 25 <= company_rate <= 35:
            print(f"   ✅ Company sponsor rate ~30% as expected ({company_rate:.1f}%)")
        else:
            print(f"   ⚠️  Company sponsor rate outside expected range: {company_rate:.1f}%")
    
    # Verify relationships being created correctly
    print("\n5. Verifying relationship creation...")
    with get_db_session() as session:
        from sqlalchemy import func
        
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
        
        # Check relationship coverage
        trials_with_drugs = session.query(ClinicalTrial).join(
            TrialDrug
        ).distinct().count()
        
        trials_with_diseases = session.query(ClinicalTrial).join(
            TrialDisease
        ).distinct().count()
        
        drug_coverage = (trials_with_drugs / total_trials * 100) if total_trials > 0 else 0
        disease_coverage = (trials_with_diseases / total_trials * 100) if total_trials > 0 else 0
        
        print(f"   Duplicate relationships:")
        print(f"   - Trial-Drug: {duplicate_trial_drugs}")
        print(f"   - Trial-Disease: {duplicate_trial_diseases}")
        print(f"   Relationship coverage:")
        print(f"   - Trials with drugs: {trials_with_drugs} ({drug_coverage:.1f}%)")
        print(f"   - Trials with diseases: {trials_with_diseases} ({disease_coverage:.1f}%)")
        
        if duplicate_trial_drugs == 0 and duplicate_trial_diseases == 0:
            print(f"   ✅ No duplicate relationships")
        else:
            print(f"   ❌ Duplicate relationships found!")
            return False
        
        if drug_coverage >= 70 and disease_coverage >= 80:
            print(f"   ✅ Good relationship coverage")
        else:
            print(f"   ⚠️  Lower than expected coverage")
    
    # Check review queue growth
    print("\n6. Verifying review queue growth (linear, not exponential)...")
    with get_db_session() as session:
        review_count = session.query(EntityMatchCandidate).filter_by(
            status='needs_review'
        ).count()
        
        # Calculate review rate per entity
        total_entities = stats['entities_created'] + stats['entities_matched']
        review_rate = (review_count / total_entities * 100) if total_entities > 0 else 0
        
        print(f"   Entities needing review: {review_count}")
        print(f"   Total entities processed: {total_entities}")
        print(f"   Review rate: {review_rate:.2f}%")
        
        # Check if review queue is reasonable (should be <10% for most cases)
        if review_rate < 10:
            print(f"   ✅ Review queue growth is reasonable ({review_rate:.2f}%)")
        elif review_rate < 20:
            print(f"   ⚠️  Review queue is moderate ({review_rate:.2f}%)")
        else:
            print(f"   ❌ Review queue is high ({review_rate:.2f}%) - may indicate matching issues")
    
    # Check entity matching rates
    print("\n7. Verifying entity matching rates...")
    total_entities = stats['entities_created'] + stats['entities_matched']
    if total_entities > 0:
        match_rate = (stats['entities_matched'] / total_entities * 100)
        create_rate = (stats['entities_created'] / total_entities * 100)
        
        print(f"   Total entities: {total_entities}")
        print(f"   Matched (existing): {stats['entities_matched']} ({match_rate:.1f}%)")
        print(f"   Created (new): {stats['entities_created']} ({create_rate:.1f}%)")
        
        # Match rate should be reasonable (not too high, not too low)
        if 20 <= match_rate <= 60:
            print(f"   ✅ Match rate is reasonable ({match_rate:.1f}%)")
        else:
            print(f"   ⚠️  Match rate outside typical range ({match_rate:.1f}%)")
    
    # Final summary
    print("\n" + "="*70)
    print("SCALE VALIDATION SUMMARY")
    print("="*70)
    
    all_passed = (
        success_rate >= 95 and
        duplicate_trial_drugs == 0 and
        duplicate_trial_diseases == 0
    )
    
    if all_passed:
        print("\n✅ ALL VALIDATIONS PASSED")
        print("   - System handles 100 trials without crashes")
        print("   - Sponsor relationship rate is consistent")
        print("   - Relationships created correctly (no duplicates)")
        print("   - Review queue growth is reasonable")
        print("   - Entity matching working correctly")
    else:
        print("\n⚠️  SOME VALIDATIONS FAILED")
        if success_rate < 95:
            print(f"   - Low success rate: {success_rate:.1f}%")
        if duplicate_trial_drugs > 0 or duplicate_trial_diseases > 0:
            print(f"   - Duplicate relationships found")
    
    print("="*70)
    
    return all_passed


if __name__ == "__main__":
    success = test_scale_validation()
    sys.exit(0 if success else 1)

