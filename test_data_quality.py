"""
Comprehensive data quality and validation tests.

This tests:
1. Entity creation correctness
2. Relationship accuracy
3. Data completeness
4. Edge cases
5. Integration points
"""
import sys
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from ingestion.clinicaltrials_gov import fetch_studies_sample
from src.processing.pipeline import ProcessingPipeline


class DataQualityValidator:
    """Validates data quality and correctness."""
    
    def __init__(self):
        self.issues = []
        self.warnings = []
    
    def validate_entity_quality(self) -> Dict[str, Any]:
        """Validate entity data quality."""
        print("\n" + "="*70)
        print("ENTITY QUALITY VALIDATION")
        print("="*70)
        
        with get_db_session() as session:
            # Check for null/empty names
            null_trials = session.query(ClinicalTrial).filter(
                (ClinicalTrial.trial_title == None) | 
                (ClinicalTrial.trial_title == '')
            ).count()
            
            null_drugs = session.query(Drug).filter(
                (Drug.primary_name == None) | 
                (Drug.primary_name == '')
            ).count()
            
            null_companies = session.query(Company).filter(
                (Company.name == None) | 
                (Company.name == '')
            ).count()
            
            null_diseases = session.query(Disease).filter(
                (Disease.disease_name == None) | 
                (Disease.disease_name == '')
            ).count()
            
            print(f"\nNull/Empty Names:")
            print(f"  Trials: {null_trials}")
            print(f"  Drugs: {null_drugs}")
            print(f"  Companies: {null_companies}")
            print(f"  Diseases: {null_diseases}")
            
            if null_trials > 0 or null_drugs > 0 or null_companies > 0 or null_diseases > 0:
                self.issues.append("Entities with null/empty names found")
            
            # Check for duplicate NCT IDs
            from sqlalchemy import func
            duplicate_ncts = session.query(
                ClinicalTrial.nct_id,
                func.count(ClinicalTrial.trial_id).label('count')
            ).group_by(ClinicalTrial.nct_id).having(
                func.count(ClinicalTrial.trial_id) > 1
            ).all()
            
            if duplicate_ncts:
                print(f"\n⚠️  Duplicate NCT IDs found: {len(duplicate_ncts)}")
                for nct_id, count in duplicate_ncts[:5]:
                    print(f"  {nct_id}: {count} duplicates")
                self.issues.append(f"Duplicate NCT IDs: {len(duplicate_ncts)}")
            
            # Check for orphaned relationships
            orphaned_trial_drugs = session.query(TrialDrug).outerjoin(
                ClinicalTrial, TrialDrug.trial_id == ClinicalTrial.trial_id
            ).filter(ClinicalTrial.trial_id == None).count()
            
            orphaned_trial_diseases = session.query(TrialDisease).outerjoin(
                ClinicalTrial, TrialDisease.trial_id == ClinicalTrial.trial_id
            ).filter(ClinicalTrial.trial_id == None).count()
            
            print(f"\nOrphaned Relationships:")
            print(f"  Trial-Drug: {orphaned_trial_drugs}")
            print(f"  Trial-Disease: {orphaned_trial_diseases}")
            
            if orphaned_trial_drugs > 0 or orphaned_trial_diseases > 0:
                self.issues.append("Orphaned relationships found")
            
            return {
                'null_names': {
                    'trials': null_trials,
                    'drugs': null_drugs,
                    'companies': null_companies,
                    'diseases': null_diseases
                },
                'duplicate_ncts': len(duplicate_ncts),
                'orphaned_relationships': {
                    'trial_drugs': orphaned_trial_drugs,
                    'trial_diseases': orphaned_trial_diseases
                }
            }
    
    def validate_relationship_accuracy(self) -> Dict[str, Any]:
        """Validate relationship accuracy."""
        print("\n" + "="*70)
        print("RELATIONSHIP ACCURACY VALIDATION")
        print("="*70)
        
        with get_db_session() as session:
            # Check for duplicate relationships
            from sqlalchemy import func
            
            duplicate_trial_drugs = session.query(
                TrialDrug.trial_id,
                TrialDrug.drug_id,
                func.count().label('count')
            ).group_by(
                TrialDrug.trial_id,
                TrialDrug.drug_id
            ).having(func.count() > 1).all()
            
            duplicate_trial_diseases = session.query(
                TrialDisease.trial_id,
                TrialDisease.disease_id,
                func.count().label('count')
            ).group_by(
                TrialDisease.trial_id,
                TrialDisease.disease_id
            ).having(func.count() > 1).all()
            
            print(f"\nDuplicate Relationships:")
            print(f"  Trial-Drug: {len(duplicate_trial_drugs)}")
            print(f"  Trial-Disease: {len(duplicate_trial_diseases)}")
            
            if duplicate_trial_drugs or duplicate_trial_diseases:
                self.issues.append("Duplicate relationships found")
            
            # Check relationship completeness
            trials = session.query(ClinicalTrial).count()
            trials_with_sponsors = session.query(ClinicalTrial).join(
                TrialSponsor
            ).distinct().count()
            trials_with_drugs = session.query(ClinicalTrial).join(
                TrialDrug
            ).distinct().count()
            trials_with_diseases = session.query(ClinicalTrial).join(
                TrialDisease
            ).distinct().count()
            
            print(f"\nRelationship Completeness:")
            print(f"  Total trials: {trials}")
            print(f"  Trials with sponsors: {trials_with_sponsors} ({trials_with_sponsors/trials*100:.1f}%)")
            print(f"  Trials with drugs: {trials_with_drugs} ({trials_with_drugs/trials*100:.1f}%)")
            print(f"  Trials with diseases: {trials_with_diseases} ({trials_with_diseases/trials*100:.1f}%)")
            
            if trials_with_sponsors / trials < 0.8:
                self.warnings.append("Low sponsor relationship coverage")
            if trials_with_drugs / trials < 0.5:
                self.warnings.append("Low drug relationship coverage")
            if trials_with_diseases / trials < 0.5:
                self.warnings.append("Low disease relationship coverage")
            
            return {
                'duplicate_relationships': {
                    'trial_drugs': len(duplicate_trial_drugs),
                    'trial_diseases': len(duplicate_trial_diseases)
                },
                'completeness': {
                    'total_trials': trials,
                    'with_sponsors': trials_with_sponsors,
                    'with_drugs': trials_with_drugs,
                    'with_diseases': trials_with_diseases
                }
            }
    
    def validate_data_completeness(self) -> Dict[str, Any]:
        """Validate data completeness."""
        print("\n" + "="*70)
        print("DATA COMPLETENESS VALIDATION")
        print("="*70)
        
        with get_db_session() as session:
            # Check staging vs processed
            total_staged = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov'
            ).count()
            
            processed_staged = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                processed=True
            ).count()
            
            unprocessed_staged = total_staged - processed_staged
            
            print(f"\nStaging Status:")
            print(f"  Total staged: {total_staged}")
            print(f"  Processed: {processed_staged} ({processed_staged/total_staged*100:.1f}%)")
            print(f"  Unprocessed: {unprocessed_staged}")
            
            if unprocessed_staged > 0:
                self.warnings.append(f"{unprocessed_staged} unprocessed records in staging")
            
            # Check processing logs
            successful_logs = session.query(SourceProcessingLog).filter_by(
                source_name='clinicaltrials_gov',
                processing_status='success'
            ).count()
            
            failed_logs = session.query(SourceProcessingLog).filter_by(
                source_name='clinicaltrials_gov',
                processing_status='failed'
            ).count()
            
            print(f"\nProcessing Logs:")
            print(f"  Successful: {successful_logs}")
            print(f"  Failed: {failed_logs}")
            
            if failed_logs > 0:
                # Get sample errors
                failed = session.query(SourceProcessingLog).filter_by(
                    source_name='clinicaltrials_gov',
                    processing_status='failed'
                ).limit(3).all()
                
                print(f"\n  Sample failures:")
                for log in failed:
                    print(f"    {log.source_identifier}: {log.errors}")
            
            return {
                'staging': {
                    'total': total_staged,
                    'processed': processed_staged,
                    'unprocessed': unprocessed_staged
                },
                'processing': {
                    'successful': successful_logs,
                    'failed': failed_logs
                }
            }
    
    def validate_edge_cases(self) -> Dict[str, Any]:
        """Test edge cases."""
        print("\n" + "="*70)
        print("EDGE CASE VALIDATION")
        print("="*70)
        
        with get_db_session() as session:
            # Trials with no interventions
            trials_no_drugs = session.query(ClinicalTrial).outerjoin(
                TrialDrug
            ).filter(TrialDrug.drug_id == None).count()
            
            # Trials with no conditions
            trials_no_diseases = session.query(ClinicalTrial).outerjoin(
                TrialDisease
            ).filter(TrialDisease.disease_id == None).count()
            
            # Trials with no sponsor
            trials_no_sponsor = session.query(ClinicalTrial).outerjoin(
                TrialSponsor
            ).filter(TrialSponsor.entity_id == None).count()
            
            print(f"\nTrials Missing Relationships:")
            print(f"  No drugs: {trials_no_drugs}")
            print(f"  No diseases: {trials_no_diseases}")
            print(f"  No sponsor: {trials_no_sponsor}")
            
            # Check for very long names (potential data issues)
            from sqlalchemy import func
            long_trial_names = session.query(ClinicalTrial).filter(
                func.length(ClinicalTrial.trial_title) > 500
            ).count()
            
            long_drug_names = session.query(Drug).filter(
                func.length(Drug.primary_name) > 200
            ).count()
            
            print(f"\nUnusually Long Names:")
            print(f"  Trial titles >500 chars: {long_trial_names}")
            print(f"  Drug names >200 chars: {long_drug_names}")
            
            if long_trial_names > 0 or long_drug_names > 0:
                self.warnings.append("Unusually long entity names found")
            
            return {
                'missing_relationships': {
                    'no_drugs': trials_no_drugs,
                    'no_diseases': trials_no_diseases,
                    'no_sponsor': trials_no_sponsor
                },
                'long_names': {
                    'trials': long_trial_names,
                    'drugs': long_drug_names
                }
            }
    
    def validate_integration_points(self) -> Dict[str, Any]:
        """Validate integration between components."""
        print("\n" + "="*70)
        print("INTEGRATION VALIDATION")
        print("="*70)
        
        issues = []
        
        # Check if ingestion → staging works
        print("\n1. Ingestion → Staging:")
        try:
            from ingestion.clinicaltrials_gov import fetch_studies_sample
            result = fetch_studies_sample(
                query_term='test',
                page_size=1,
                load_to_staging=True
            )
            if result and 'studies' in result:
                print("   ✅ Ingestion → Staging: Working")
            else:
                print("   ❌ Ingestion → Staging: Failed")
                issues.append("Ingestion not returning data")
        except Exception as e:
            print(f"   ❌ Ingestion → Staging: Error - {e}")
            issues.append(f"Ingestion error: {e}")
        
        # Check if staging → processing works
        print("\n2. Staging → Processing:")
        with get_db_session() as session:
            staged_count = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                processed=False
            ).count()
            
            if staged_count > 0:
                print(f"   ✅ Staging → Processing: {staged_count} records ready")
            else:
                print("   ⚠️  Staging → Processing: No unprocessed records")
        
        # Check if processing → database works
        print("\n3. Processing → Database:")
        with get_db_session() as session:
            trials = session.query(ClinicalTrial).count()
            relationships = session.query(TrialDrug).count()
            
            if trials > 0 and relationships > 0:
                print(f"   ✅ Processing → Database: {trials} trials, {relationships} relationships")
            else:
                print("   ❌ Processing → Database: No data in database")
                issues.append("No data in database")
        
        if issues:
            self.issues.extend(issues)
        
        return {'integration_issues': issues}
    
    def run_all_validations(self) -> Dict[str, Any]:
        """Run all validation checks."""
        print("\n" + "="*70)
        print("COMPREHENSIVE DATA QUALITY VALIDATION")
        print("="*70)
        
        results = {
            'entity_quality': self.validate_entity_quality(),
            'relationship_accuracy': self.validate_relationship_accuracy(),
            'data_completeness': self.validate_data_completeness(),
            'edge_cases': self.validate_edge_cases(),
            'integration': self.validate_integration_points()
        }
        
        # Summary
        print("\n" + "="*70)
        print("VALIDATION SUMMARY")
        print("="*70)
        
        if self.issues:
            print(f"\n❌ ISSUES FOUND: {len(self.issues)}")
            for issue in self.issues:
                print(f"  - {issue}")
        else:
            print("\n✅ No critical issues found")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        results['summary'] = {
            'issues': self.issues,
            'warnings': self.warnings,
            'status': 'PASS' if not self.issues else 'FAIL'
        }
        
        return results


def main():
    """Run comprehensive validation."""
    validator = DataQualityValidator()
    results = validator.run_all_validations()
    
    print("\n" + "="*70)
    if results['summary']['status'] == 'PASS':
        print("✅ VALIDATION PASSED")
    else:
        print("❌ VALIDATION FAILED - Issues need to be addressed")
    print("="*70)
    
    return results['summary']['status'] == 'PASS'


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

