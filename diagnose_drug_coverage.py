"""
Diagnostic script to find why trial-drug coverage is only 41% instead of 60-90%.

Checks:
1. Are interventions in raw data?
2. Are interventions being extracted?
3. Are drugs being resolved/created?
4. Are relationships being created?
"""
import sys
from pathlib import Path
from typing import Dict, Any, List
import json

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.entities import Drug
from database.models.relationships import TrialDrug
from database.models.staging import StagingRawData
from database.models import EntityMatchCandidate, SourceProcessingLog
from sqlalchemy import func, and_


def diagnose_drug_coverage():
    """Run comprehensive diagnostics on drug coverage issue."""
    print("\n" + "="*70)
    print("DRUG COVERAGE DIAGNOSTIC")
    print("="*70)
    
    with get_db_session() as session:
        # Step 1: Overall statistics
        print("\n1. OVERALL STATISTICS")
        print("-" * 70)
        
        total_trials = session.query(ClinicalTrial).count()
        trials_with_drugs = session.query(ClinicalTrial).join(
            TrialDrug
        ).distinct().count()
        
        total_drugs = session.query(Drug).count()
        drugs_in_trials = session.query(TrialDrug.drug_id).distinct().count()
        
        total_trial_drug_rels = session.query(TrialDrug).count()
        
        print(f"Total trials: {total_trials}")
        print(f"Trials with drugs: {trials_with_drugs} ({trials_with_drugs/total_trials*100:.1f}%)")
        print(f"Total drugs in database: {total_drugs}")
        print(f"Unique drugs in trials: {drugs_in_trials}")
        print(f"Total trial-drug relationships: {total_trial_drug_rels}")
        
        if total_drugs > drugs_in_trials * 2:
            print(f"\n⚠️  WARNING: {total_drugs} drugs exist but only {drugs_in_trials} are linked to trials")
            print("   This suggests relationship creation is failing")
        
        # Step 2: Check raw data for interventions
        print("\n2. CHECKING RAW DATA FOR INTERVENTIONS")
        print("-" * 70)
        
        staging_records = session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov',
            processed=True
        ).limit(50).all()
        
        trials_with_interventions = 0
        total_interventions = 0
        intervention_types = {}
        
        for record in staging_records:
            raw_data = record.raw_data
            
            # Check both nested and flat formats
            interventions = []
            if 'protocolSection' in raw_data:
                protocol = raw_data.get('protocolSection', {})
                arms_module = protocol.get('armsInterventionsModule', {})
                interventions = arms_module.get('interventions', [])
            elif 'interventions' in raw_data:
                interventions = raw_data.get('interventions', [])
                if not isinstance(interventions, list):
                    interventions = [interventions]
            
            if interventions:
                trials_with_interventions += 1
                total_interventions += len(interventions)
                
                for interv in interventions:
                    interv_type = interv.get('intervention_type', interv.get('type', 'unknown')).lower()
                    intervention_types[interv_type] = intervention_types.get(interv_type, 0) + 1
        
        print(f"Trials checked: {len(staging_records)}")
        print(f"Trials with interventions in raw data: {trials_with_interventions} ({trials_with_interventions/len(staging_records)*100:.1f}%)")
        print(f"Total interventions found: {total_interventions}")
        print(f"Average interventions per trial: {total_interventions/len(staging_records):.1f}")
        print(f"\nIntervention types found:")
        for interv_type, count in sorted(intervention_types.items(), key=lambda x: -x[1]):
            print(f"  {interv_type}: {count}")
        
        # Step 3: Check entity match candidates for drugs
        print("\n3. CHECKING DRUG ENTITY RESOLUTION")
        print("-" * 70)
        
        drug_candidates = session.query(EntityMatchCandidate).filter_by(
            entity_type='drug'
        ).all()
        
        drug_candidates_by_status = {}
        for candidate in drug_candidates:
            status = candidate.status
            drug_candidates_by_status[status] = drug_candidates_by_status.get(status, 0) + 1
        
        print(f"Total drug match candidates: {len(drug_candidates)}")
        for status, count in sorted(drug_candidates_by_status.items()):
            print(f"  {status}: {count}")
        
        if len(drug_candidates) > 50:
            print(f"\n⚠️  WARNING: {len(drug_candidates)} drugs in review queue")
            print("   This suggests matching thresholds are too strict")
        
        # Step 4: Check specific trial without drugs
        print("\n4. ANALYZING TRIAL WITHOUT DRUGS")
        print("-" * 70)
        
        trial_without_drugs = session.query(ClinicalTrial).outerjoin(
            TrialDrug
        ).filter(
            TrialDrug.trial_id == None
        ).first()
        
        if trial_without_drugs:
            print(f"Example trial without drugs: {trial_without_drugs.nct_id}")
            print(f"Title: {trial_without_drugs.trial_title}")
            
            # Get staging data
            staging = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=trial_without_drugs.nct_id
            ).first()
            
            if staging:
                raw_data = staging.raw_data
                
                # Check for interventions
                interventions = []
                if 'protocolSection' in raw_data:
                    protocol = raw_data.get('protocolSection', {})
                    arms_module = protocol.get('armsInterventionsModule', {})
                    interventions = arms_module.get('interventions', [])
                elif 'interventions' in raw_data:
                    interventions = raw_data.get('interventions', [])
                    if not isinstance(interventions, list):
                        interventions = [interventions]
                
                print(f"\nInterventions in raw data: {len(interventions)}")
                for i, interv in enumerate(interventions[:5]):  # Show first 5
                    interv_type = interv.get('intervention_type', interv.get('type', 'unknown'))
                    interv_name = interv.get('intervention_name', interv.get('name', 'unknown'))
                    print(f"  {i+1}. Type: {interv_type}, Name: {interv_name}")
                
                # Check processing log
                log = session.query(SourceProcessingLog).filter_by(
                    source_name='clinicaltrials_gov',
                    source_identifier=trial_without_drugs.nct_id
                ).first()
                
                if log:
                    print(f"\nProcessing log:")
                    print(f"  Status: {log.processing_status}")
                    print(f"  Entities created: {log.entities_created or 0}")
                    print(f"  Entities matched: {log.entities_matched or 0}")
                    print(f"  Relationships created: {log.relationships_created or 0}")
                    if log.errors:
                        print(f"  Errors: {log.errors}")
        
        # Step 5: Check relationship extraction
        print("\n5. CHECKING RELATIONSHIP EXTRACTION")
        print("-" * 70)
        
        # Find trials with drugs in database but no relationships
        trials_with_drugs_but_no_rels = session.query(ClinicalTrial).outerjoin(
            TrialDrug
        ).filter(
            TrialDrug.trial_id == None
        ).join(
            StagingRawData,
            ClinicalTrial.nct_id == StagingRawData.source_record_id
        ).filter(
            StagingRawData.source_system == 'clinicaltrials_gov',
            StagingRawData.processed == True
        ).limit(10).all()
        
        print(f"Trials without drug relationships: {len(trials_with_drugs_but_no_rels)}")
        
        # Check if drugs were extracted but not linked
        for trial in trials_with_drugs_but_no_rels[:3]:  # Check first 3
            staging = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=trial.nct_id
            ).first()
            
            if staging:
                raw_data = staging.raw_data
                
                # Count interventions
                interventions = []
                if 'protocolSection' in raw_data:
                    protocol = raw_data.get('protocolSection', {})
                    arms_module = protocol.get('armsInterventionsModule', {})
                    interventions = arms_module.get('interventions', [])
                elif 'interventions' in raw_data:
                    interventions = raw_data.get('interventions', [])
                    if not isinstance(interventions, list):
                        interventions = [interventions]
                
                # Count drug-type interventions
                drug_interventions = [
                    i for i in interventions
                    if i.get('intervention_type', i.get('type', '')).lower() in 
                    ['drug', 'biological', 'biologic', 'combination product']
                ]
                
                if drug_interventions:
                    print(f"\n  Trial {trial.nct_id}:")
                    print(f"    Has {len(drug_interventions)} drug interventions in raw data")
                    print(f"    But 0 drug relationships created")
                    print(f"    → Likely issue: Relationship extraction or creation")
        
        # Step 6: Check processing logs for warnings
        print("\n6. CHECKING PROCESSING LOGS FOR ISSUES")
        print("-" * 70)
        
        failed_logs = session.query(SourceProcessingLog).filter_by(
            source_name='clinicaltrials_gov',
            processing_status='failed'
        ).limit(10).all()
        
        print(f"Failed processing logs: {len(failed_logs)}")
        for log in failed_logs[:5]:
            print(f"\n  {log.source_identifier}:")
            if log.errors:
                print(f"    Error: {log.errors[0] if isinstance(log.errors, list) else log.errors}")
        
        # Check for low relationship creation
        logs_with_low_rels = session.query(SourceProcessingLog).filter_by(
            source_name='clinicaltrials_gov',
            processing_status='success'
        ).filter(
            SourceProcessingLog.relationships_created < 2
        ).limit(10).all()
        
        print(f"\nSuccessful logs with <2 relationships: {len(logs_with_low_rels)}")
        for log in logs_with_low_rels[:5]:
            print(f"  {log.source_identifier}: {log.relationships_created or 0} relationships")
        
        # Step 7: Summary and recommendations
        print("\n" + "="*70)
        print("DIAGNOSTIC SUMMARY")
        print("="*70)
        
        issues_found = []
        
        if trials_with_interventions / len(staging_records) < 0.7:
            issues_found.append("Low intervention rate in raw data (<70%)")
        
        if len(drug_candidates) > 50:
            issues_found.append(f"Too many drugs in review queue ({len(drug_candidates)})")
        
        if total_drugs > drugs_in_trials * 2:
            issues_found.append("Drugs created but not linked to trials")
        
        if issues_found:
            print("\n⚠️  ISSUES FOUND:")
            for issue in issues_found:
                print(f"  - {issue}")
        else:
            print("\n✅ No obvious issues found in diagnostics")
            print("   Issue may be in relationship extraction logic")
        
        print("\nRECOMMENDATIONS:")
        print("  1. Check processor.extract_relationships() method")
        print("  2. Verify entity_stub_to_id mapping in pipeline")
        print("  3. Check if drugs are being extracted but not resolved")
        print("  4. Review relationship creation warnings in logs")


if __name__ == "__main__":
    diagnose_drug_coverage()

