"""
Comprehensive diagnostic script to check all relationship coverage metrics
and identify issues based on realistic targets.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease
from database.models.entities import Company, Drug, Disease
from database.models import EntityMatchCandidate, SourceProcessingLog
from sqlalchemy import func, distinct


def diagnose_all_metrics():
    """Run comprehensive diagnostics on all relationship metrics."""
    print("\n" + "="*70)
    print("COMPREHENSIVE RELATIONSHIP COVERAGE DIAGNOSTICS")
    print("="*70)
    
    with get_db_session() as session:
        # 1. Sponsor Coverage (CRITICAL - should be 95-100%)
        print("\n1. SPONSOR COVERAGE (Target: 95-100%)")
        print("-" * 70)
        
        total_trials = session.query(ClinicalTrial).count()
        
        # Count by entity type
        sponsor_by_type = session.query(
            TrialSponsor.entity_type,
            func.count(distinct(TrialSponsor.trial_id)).label('count')
        ).group_by(TrialSponsor.entity_type).all()
        
        total_trials_with_sponsors = session.query(ClinicalTrial).join(
            TrialSponsor
        ).distinct().count()
        
        sponsor_coverage = (total_trials_with_sponsors / total_trials * 100) if total_trials > 0 else 0
        
        print(f"Total trials: {total_trials}")
        print(f"Trials with sponsors: {total_trials_with_sponsors} ({sponsor_coverage:.1f}%)")
        print(f"\nBreakdown by entity type:")
        for entity_type, count in sponsor_by_type:
            print(f"  {entity_type}: {count} trials")
        
        if sponsor_coverage < 95:
            print(f"\n❌ CRITICAL: Sponsor coverage is {sponsor_coverage:.1f}% (target: 95-100%)")
            print("   Issue: Not all trials have sponsor relationships")
        else:
            print(f"\n✅ Sponsor coverage is good ({sponsor_coverage:.1f}%)")
        
        # 2. Drug Coverage by Trial Type
        print("\n2. DRUG COVERAGE BY TRIAL TYPE")
        print("-" * 70)
        
        # Check if study_type field exists
        try:
            drug_by_type = session.query(
                ClinicalTrial.study_type,
                func.count(distinct(ClinicalTrial.trial_id)).label('total'),
                func.count(distinct(TrialDrug.trial_id)).label('with_drugs')
            ).outerjoin(
                TrialDrug, ClinicalTrial.trial_id == TrialDrug.trial_id
            ).group_by(ClinicalTrial.study_type).all()
            
            print("Breakdown by study type:")
            for study_type, total, with_drugs in drug_by_type:
                pct = (with_drugs / total * 100) if total > 0 else 0
                print(f"  {study_type or 'NULL'}: {with_drugs}/{total} ({pct:.1f}%)")
                
                if study_type and 'interventional' in study_type.lower():
                    if pct < 85:
                        print(f"    ⚠️  Low for interventional trials (target: 85-95%)")
                    else:
                        print(f"    ✅ Good for interventional trials")
                elif study_type and 'observational' in study_type.lower():
                    if pct > 20:
                        print(f"    ⚠️  High for observational trials (expected: 5-15%)")
                    else:
                        print(f"    ✅ Reasonable for observational trials")
        except Exception as e:
            print(f"  ⚠️  Could not check by study_type: {e}")
            # Fallback: overall drug coverage
            total_with_drugs = session.query(ClinicalTrial).join(
                TrialDrug
            ).distinct().count()
            drug_coverage = (total_with_drugs / total_trials * 100) if total_trials > 0 else 0
            print(f"  Overall drug coverage: {total_with_drugs}/{total_trials} ({drug_coverage:.1f}%)")
        
        # 3. Disease Coverage
        print("\n3. DISEASE COVERAGE (Target: 85-95%)")
        print("-" * 70)
        
        trials_with_diseases = session.query(ClinicalTrial).join(
            TrialDisease
        ).distinct().count()
        
        disease_coverage = (trials_with_diseases / total_trials * 100) if total_trials > 0 else 0
        
        print(f"Trials with diseases: {trials_with_diseases}/{total_trials} ({disease_coverage:.1f}%)")
        
        if disease_coverage >= 85:
            print(f"✅ Disease coverage is excellent ({disease_coverage:.1f}%)")
        else:
            print(f"⚠️  Disease coverage below target ({disease_coverage:.1f}%)")
        
        # 4. Cross-Source Entity Coverage
        print("\n4. CROSS-SOURCE ENTITY COVERAGE")
        print("-" * 70)
        
        # Companies in 2+ sources (Target: 60-75%)
        all_companies = session.query(Company).all()
        companies_multi_source = 0
        for company in all_companies:
            if company.data_sources and len(company.data_sources) >= 2:
                companies_multi_source += 1
        
        total_companies = len(all_companies)
        company_multi_pct = (companies_multi_source / total_companies * 100) if total_companies > 0 else 0
        
        print(f"Companies in 2+ sources: {companies_multi_source}/{total_companies} ({company_multi_pct:.1f}%)")
        if company_multi_pct >= 60:
            print(f"✅ Good cross-source coverage (target: 60-75%)")
        else:
            print(f"⚠️  Below target (target: 60-75%)")
        
        # Drugs in 2+ sources (Target: 40-60%)
        all_drugs = session.query(Drug).all()
        drugs_multi_source = 0
        for drug in all_drugs:
            if drug.data_sources and len(drug.data_sources) >= 2:
                drugs_multi_source += 1
        
        total_drugs = len(all_drugs)
        drug_multi_pct = (drugs_multi_source / total_drugs * 100) if total_drugs > 0 else 0
        
        print(f"Drugs in 2+ sources: {drugs_multi_source}/{total_drugs} ({drug_multi_pct:.1f}%)")
        if drug_multi_pct >= 40:
            print(f"✅ Good cross-source coverage (target: 40-60%)")
        else:
            print(f"⚠️  Below target (target: 40-60%)")
        
        # 5. Duplicate Detection
        print("\n5. DUPLICATE DETECTION (Target: <1%)")
        print("-" * 70)
        
        # Duplicate companies by name
        duplicate_companies = session.query(
            Company.name,
            func.count().label('count')
        ).group_by(Company.name).having(func.count() > 1).count()
        
        duplicate_drugs = session.query(
            Drug.primary_name,
            func.count().label('count')
        ).group_by(Drug.primary_name).having(func.count() > 1).count()
        
        duplicate_trial_drugs = session.query(
            TrialDrug.trial_id,
            TrialDrug.drug_id,
            func.count().label('count')
        ).group_by(
            TrialDrug.trial_id,
            TrialDrug.drug_id
        ).having(func.count() > 1).count()
        
        print(f"Duplicate companies: {duplicate_companies}")
        print(f"Duplicate drugs: {duplicate_drugs}")
        print(f"Duplicate trial-drug relationships: {duplicate_trial_drugs}")
        
        if duplicate_trial_drugs == 0:
            print("✅ No duplicate relationships")
        else:
            print(f"❌ {duplicate_trial_drugs} duplicate relationships found")
        
        # 6. Entity Resolution Review Queue
        print("\n6. ENTITY RESOLUTION REVIEW QUEUE (Target: <10%)")
        print("-" * 70)
        
        review_by_status = session.query(
            EntityMatchCandidate.status,
            func.count().label('count')
        ).group_by(EntityMatchCandidate.status).all()
        
        total_review = sum(count for _, count in review_by_status)
        total_entities = total_companies + total_drugs + total_trials
        
        review_rate = (total_review / total_entities * 100) if total_entities > 0 else 0
        
        print(f"Review queue: {total_review} entities")
        print(f"Total entities: {total_entities}")
        print(f"Review rate: {review_rate:.2f}%")
        
        for status, count in review_by_status:
            print(f"  {status}: {count}")
        
        if review_rate < 10:
            print(f"✅ Review queue is reasonable ({review_rate:.2f}%)")
        else:
            print(f"⚠️  Review queue is high ({review_rate:.2f}%)")
        
        # 7. Processing Success Rate
        print("\n7. PROCESSING SUCCESS RATE (Target: >95%)")
        print("-" * 70)
        
        processing_by_status = session.query(
            SourceProcessingLog.processing_status,
            func.count().label('count')
        ).filter_by(
            source_name='clinicaltrials_gov'
        ).group_by(SourceProcessingLog.processing_status).all()
        
        total_processed = sum(count for _, count in processing_by_status)
        success_count = next((count for status, count in processing_by_status if status == 'success'), 0)
        success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
        
        print(f"Processing status breakdown:")
        for status, count in processing_by_status:
            pct = (count / total_processed * 100) if total_processed > 0 else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        
        print(f"\nSuccess rate: {success_rate:.1f}%")
        if success_rate >= 95:
            print(f"✅ Processing success rate is good")
        else:
            print(f"⚠️  Processing success rate below target")
        
        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        issues = []
        if sponsor_coverage < 95:
            issues.append(f"❌ Sponsor coverage too low: {sponsor_coverage:.1f}% (target: 95-100%)")
        if disease_coverage < 85:
            issues.append(f"⚠️  Disease coverage below target: {disease_coverage:.1f}% (target: 85-95%)")
        if duplicate_trial_drugs > 0:
            issues.append(f"❌ Duplicate relationships found: {duplicate_trial_drugs}")
        if review_rate >= 10:
            issues.append(f"⚠️  Review queue high: {review_rate:.2f}% (target: <10%)")
        if success_rate < 95:
            issues.append(f"⚠️  Processing success rate low: {success_rate:.1f}% (target: >95%)")
        
        if issues:
            print("\nIssues found:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ All metrics within acceptable ranges")
        
        return {
            'sponsor_coverage': sponsor_coverage,
            'drug_coverage': drug_coverage if 'drug_coverage' in locals() else None,
            'disease_coverage': disease_coverage,
            'duplicate_relationships': duplicate_trial_drugs,
            'review_rate': review_rate,
            'success_rate': success_rate,
            'issues': issues
        }


if __name__ == "__main__":
    results = diagnose_all_metrics()

