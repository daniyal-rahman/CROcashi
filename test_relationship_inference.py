#!/usr/bin/env python3
"""
Test script for relationship inference.

Tests the relationship inference service to verify it creates relationships correctly.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from src.services.relationship_inference import RelationshipInferenceService
from database.models import (
    Publication, ClinicalTrial, Drug, SECFiling,
    PublicationTrial, PublicationDrug, FilingDrug
)

def test_relationship_inference():
    """Test relationship inference methods."""
    print("=" * 80)
    print("RELATIONSHIP INFERENCE TEST")
    print("=" * 80)
    print()
    
    try:
        with get_db_session() as session:
            # Get initial counts
            print("1. Initial Relationship Counts")
            print("-" * 80)
            initial_pub_trial = session.query(PublicationTrial).count()
            initial_pub_drug = session.query(PublicationDrug).count()
            initial_filing_drug = session.query(FilingDrug).count()
            
            print(f"  PublicationTrial: {initial_pub_trial:,}")
            print(f"  PublicationDrug: {initial_pub_drug:,}")
            print(f"  FilingDrug: {initial_filing_drug:,}")
            print()
            
            # Check entity counts
            print("2. Entity Counts")
            print("-" * 80)
            pub_count = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
            trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
            drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
            filing_count = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
            
            print(f"  Publications: {pub_count:,}")
            print(f"  Trials: {trial_count:,}")
            print(f"  Drugs: {drug_count:,}")
            print(f"  SEC Filings: {filing_count:,}")
            print()
            
            # Run inference
            print("3. Running Relationship Inference")
            print("-" * 80)
            service = RelationshipInferenceService(session)
            
            # Test individual methods
            print("\n  Testing publication-trial inference...")
            result_pt = service.infer_publication_trial_relationships()
            print(f"    Status: {result_pt.get('status')}")
            print(f"    Created: {result_pt.get('relationships_created', 0):,}")
            
            print("\n  Testing publication-drug inference...")
            result_pd = service.infer_publication_drug_relationships()
            print(f"    Status: {result_pd.get('status')}")
            print(f"    Created: {result_pd.get('relationships_created', 0):,}")
            
            print("\n  Testing filing-drug inference...")
            result_fd = service.infer_filing_drug_relationships()
            print(f"    Status: {result_fd.get('status')}")
            print(f"    Created: {result_fd.get('relationships_created', 0):,}")
            print()
            
            # Get final counts
            print("4. Final Relationship Counts")
            print("-" * 80)
            final_pub_trial = session.query(PublicationTrial).count()
            final_pub_drug = session.query(PublicationDrug).count()
            final_filing_drug = session.query(FilingDrug).count()
            
            print(f"  PublicationTrial: {final_pub_trial:,} (change: {final_pub_trial - initial_pub_trial:+,})")
            print(f"  PublicationDrug: {final_pub_drug:,} (change: {final_pub_drug - initial_pub_drug:+,})")
            print(f"  FilingDrug: {final_filing_drug:,} (change: {final_filing_drug - initial_filing_drug:+,})")
            print()
            
            # Verify results match
            print("5. Verification")
            print("-" * 80)
            pt_created = result_pt.get('relationships_created', 0)
            pd_created = result_pd.get('relationships_created', 0)
            fd_created = result_fd.get('relationships_created', 0)
            
            pt_match = (final_pub_trial - initial_pub_trial) == pt_created
            pd_match = (final_pub_drug - initial_pub_drug) == pd_created
            fd_match = (final_filing_drug - initial_filing_drug) == fd_created
            
            print(f"  PublicationTrial: {'✓' if pt_match else '✗'} (expected {pt_created}, got {final_pub_trial - initial_pub_trial})")
            print(f"  PublicationDrug: {'✓' if pd_match else '✗'} (expected {pd_created}, got {final_pub_drug - initial_pub_drug})")
            print(f"  FilingDrug: {'✓' if fd_match else '✗'} (expected {fd_created}, got {final_filing_drug - initial_filing_drug})")
            print()
            
            # Sample relationships
            if final_pub_trial > initial_pub_trial:
                print("6. Sample Publication-Trial Relationships")
                print("-" * 80)
                samples = session.query(PublicationTrial).join(Publication).join(ClinicalTrial).limit(5).all()
                for rel in samples:
                    print(f"  {rel.publication.title[:60]}... → {rel.trial.nct_id}")
                print()
            
            if final_pub_drug > initial_pub_drug:
                print("7. Sample Publication-Drug Relationships")
                print("-" * 80)
                samples = session.query(PublicationDrug).join(Publication).join(Drug).limit(5).all()
                for rel in samples:
                    print(f"  {rel.publication.title[:60]}... → {rel.drug.primary_name}")
                print()
            
            print("=" * 80)
            print("TEST COMPLETE")
            print("=" * 80)
            
            return pt_match and pd_match and fd_match
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_relationship_inference()
    sys.exit(0 if success else 1)

