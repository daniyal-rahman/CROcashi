"""
Script to count all relationships in the database.
"""
import sys
from database.config import get_db_session
from database.models import (
    CompanyDrug, CompanyOwnershipHistory, DrugIndication, DrugTarget, DrugMechanism,
    TrialSponsor, TrialDrug, TrialDisease, PublicationDrug, PublicationTrial,
    PublicationCompany, RegulatoryDrugEvent, RegulatoryCompanyEvent,
    FilingCompany, FilingDrug, PatentDrug, PatentCompany,
    PresentationDrug, PresentationCompany, PresentationTrial,
    DrugOwnershipHistory, TrialFunding
)

def count_relationships():
    """Count all relationships in the database."""
    relationship_models = {
        'CompanyDrug': CompanyDrug,
        'CompanyOwnershipHistory': CompanyOwnershipHistory,
        'DrugOwnershipHistory': DrugOwnershipHistory,
        'DrugIndication': DrugIndication,
        'DrugTarget': DrugTarget,
        'DrugMechanism': DrugMechanism,
        'TrialSponsor': TrialSponsor,
        'TrialFunding': TrialFunding,
        'TrialDrug': TrialDrug,
        'TrialDisease': TrialDisease,
        'PublicationDrug': PublicationDrug,
        'PublicationTrial': PublicationTrial,
        'PublicationCompany': PublicationCompany,
        'RegulatoryDrugEvent': RegulatoryDrugEvent,
        'RegulatoryCompanyEvent': RegulatoryCompanyEvent,
        'FilingCompany': FilingCompany,
        'FilingDrug': FilingDrug,
        'PatentDrug': PatentDrug,
        'PatentCompany': PatentCompany,
        'PresentationDrug': PresentationDrug,
        'PresentationCompany': PresentationCompany,
        'PresentationTrial': PresentationTrial,
    }
    
    print("=" * 80)
    print("RELATIONSHIP COUNT REPORT")
    print("=" * 80)
    print()
    
    total = 0
    results = {}
    
    try:
        with get_db_session() as session:
            for name, model in relationship_models.items():
                try:
                    count = session.query(model).count()
                    results[name] = count
                    total += count
                    status = "✓" if count > 0 else "✗"
                    print(f"{status} {name:35} {count:>10,}")
                except Exception as e:
                    print(f"✗ {name:35} ERROR: {e}")
                    results[name] = None
        
        print()
        print("=" * 80)
        print(f"TOTAL RELATIONSHIPS: {total:,}")
        print("=" * 80)
        print()
        
        # Show breakdown
        if total == 0:
            print("⚠️  WARNING: No relationships found in database!")
            print()
            print("This could indicate:")
            print("  1. Data hasn't been ingested yet")
            print("  2. Relationship extraction is failing")
            print("  3. Entity resolution is failing (entities not being resolved)")
            print("  4. Relationship creation logic has issues")
        elif total < 100:
            print("⚠️  WARNING: Very low relationship count!")
            print()
            print("This suggests:")
            print("  1. Limited data ingestion")
            print("  2. Relationship extraction may not be working properly")
            print("  3. Entity resolution may be failing")
        else:
            print("✓ Relationship count looks reasonable")
        
        return results, total
        
    except Exception as e:
        print(f"ERROR connecting to database: {e}")
        import traceback
        traceback.print_exc()
        return None, 0

if __name__ == '__main__':
    results, total = count_relationships()
    sys.exit(0 if total > 0 else 1)


