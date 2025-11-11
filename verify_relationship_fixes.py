"""
Verification script for relationship generation fixes.

Tests:
1. Company-drug inference from trial sponsorships
2. Publication-drug relationships
3. SEC filing-drug relationships
"""
import sys
from sqlalchemy import text
from database.config import get_db_session

def verify_company_drug_inference():
    """Verify company-drug relationships were inferred from trials."""
    print("\n" + "="*60)
    print("VERIFICATION 1: Company-Drug Inference")
    print("="*60)
    
    with get_db_session() as session:
        # Count inferred relationships
        query = text("""
            SELECT COUNT(*) as count
            FROM company_drugs
            WHERE data_sources->>'source' = 'inferred_from_trial'
            AND deleted_at IS NULL
        """)
        result = session.execute(query).fetchone()
        inferred_count = result[0] if result else 0
        
        # Count total company-drug relationships
        query_total = text("""
            SELECT COUNT(*) as count
            FROM company_drugs
            WHERE deleted_at IS NULL
        """)
        result_total = session.execute(query_total).fetchone()
        total_count = result_total[0] if result_total else 0
        
        # Sample relationships
        query_sample = text("""
            SELECT c.name as company_name, d.primary_name as drug_name, cd.relationship_type
            FROM company_drugs cd
            JOIN companies c ON cd.company_id = c.company_id
            JOIN drugs d ON cd.drug_id = d.drug_id
            WHERE cd.data_sources->>'source' = 'inferred_from_trial'
            AND cd.deleted_at IS NULL
            AND c.deleted_at IS NULL
            AND d.deleted_at IS NULL
            LIMIT 10
        """)
        samples = session.execute(query_sample).fetchall()
        
        print(f"\n✅ Total company-drug relationships: {total_count}")
        print(f"✅ Inferred from trials: {inferred_count}")
        
        if inferred_count > 0:
            print(f"\n✅ SUCCESS: Found {inferred_count} inferred relationships")
            print("\nSample relationships:")
            for row in samples[:5]:
                print(f"  - {row[0]} → {row[1]} ({row[2]})")
        else:
            print("\n⚠️  WARNING: No inferred relationships found")
            print("   This might be expected if:")
            print("   - No trials have been processed yet")
            print("   - Trials don't have both sponsors and drugs")
            print("   - Inference hasn't been run yet")
        
        return inferred_count > 0


def verify_publication_drug_relationships():
    """Verify publication-drug relationships exist."""
    print("\n" + "="*60)
    print("VERIFICATION 2: Publication-Drug Relationships")
    print("="*60)
    
    with get_db_session() as session:
        # Count publication-drug relationships
        query = text("""
            SELECT COUNT(*) as count
            FROM publication_drugs
            WHERE deleted_at IS NULL
        """)
        result = session.execute(query).fetchone()
        count = result[0] if result else 0
        
        # Count publications
        query_pubs = text("""
            SELECT COUNT(*) as count
            FROM publications
            WHERE deleted_at IS NULL
        """)
        result_pubs = session.execute(query_pubs).fetchone()
        pub_count = result_pubs[0] if result_pubs else 0
        
        # Sample relationships
        query_sample = text("""
            SELECT p.title, d.primary_name as drug_name
            FROM publication_drugs pd
            JOIN publications p ON pd.pub_id = p.pub_id
            JOIN drugs d ON pd.drug_id = d.drug_id
            WHERE pd.deleted_at IS NULL
            AND p.deleted_at IS NULL
            AND d.deleted_at IS NULL
            LIMIT 10
        """)
        samples = session.execute(query_sample).fetchall()
        
        print(f"\n✅ Total publications: {pub_count}")
        print(f"✅ Publication-drug relationships: {count}")
        
        if count > 0:
            print(f"\n✅ SUCCESS: Found {count} publication-drug relationships")
            print("\nSample relationships:")
            for row in samples[:5]:
                title = row[0][:60] + "..." if row[0] and len(row[0]) > 60 else (row[0] or "No title")
                print(f"  - {title}")
                print(f"    → {row[1]}")
        else:
            print("\n⚠️  WARNING: No publication-drug relationships found")
            print("   This might be expected if:")
            print("   - Publications haven't been reprocessed yet")
            print("   - No drugs exist in database to match against")
            print("   - Publications don't mention any known drugs")
        
        return count > 0


def verify_sec_filing_drug_relationships():
    """Verify SEC filing-drug relationships exist."""
    print("\n" + "="*60)
    print("VERIFICATION 3: SEC Filing-Drug Relationships")
    print("="*60)
    
    with get_db_session() as session:
        # Count filing-drug relationships
        query = text("""
            SELECT COUNT(*) as count
            FROM filing_drugs
            WHERE deleted_at IS NULL
        """)
        result = session.execute(query).fetchone()
        count = result[0] if result else 0
        
        # Count SEC filings
        query_filings = text("""
            SELECT COUNT(*) as count
            FROM sec_filings
            WHERE deleted_at IS NULL
        """)
        result_filings = session.execute(query_filings).fetchone()
        filing_count = result_filings[0] if result_filings else 0
        
        # Sample relationships
        query_sample = text("""
            SELECT sf.accession_number, d.primary_name as drug_name, fd.mention_type
            FROM filing_drugs fd
            JOIN sec_filings sf ON fd.filing_id = sf.filing_id
            JOIN drugs d ON fd.drug_id = d.drug_id
            WHERE fd.deleted_at IS NULL
            AND sf.deleted_at IS NULL
            AND d.deleted_at IS NULL
            LIMIT 10
        """)
        samples = session.execute(query_sample).fetchall()
        
        print(f"\n✅ Total SEC filings: {filing_count}")
        print(f"✅ Filing-drug relationships: {count}")
        
        if count > 0:
            print(f"\n✅ SUCCESS: Found {count} filing-drug relationships")
            print("\nSample relationships:")
            for row in samples[:5]:
                print(f"  - Filing {row[0]} → {row[1]} ({row[2] or 'N/A'})")
        else:
            print("\n⚠️  WARNING: No filing-drug relationships found")
            print("   This might be expected if:")
            print("   - SEC filings haven't been reprocessed yet")
            print("   - No drugs exist in database to match against")
            print("   - Filings don't mention any known drugs")
        
        # Check for program discontinuation events
        query_events = text("""
            SELECT COUNT(*) as count
            FROM regulatory_events
            WHERE event_type = 'withdrawal'
            AND data_sources->>'source' = 'sec_edgar'
            AND deleted_at IS NULL
        """)
        result_events = session.execute(query_events).fetchone()
        event_count = result_events[0] if result_events else 0
        
        print(f"\n✅ Program discontinuation events from SEC: {event_count}")
        
        return count > 0


def run_inference():
    """Run relationship inference if needed."""
    print("\n" + "="*60)
    print("RUNNING RELATIONSHIP INFERENCE")
    print("="*60)
    
    try:
        from src.services.relationship_inference import RelationshipInferenceService
        
        with get_db_session() as session:
            inference_service = RelationshipInferenceService(session)
            results = inference_service.infer_all_relationships()
            
            company_drug_result = results.get('company_drug', {})
            if company_drug_result.get('status') == 'success':
                count = company_drug_result.get('relationships_inferred', 0)
                print(f"\n✅ Inference completed: {count} company-drug relationships inferred")
                return True
            else:
                error = company_drug_result.get('error', 'Unknown error')
                print(f"\n❌ Inference failed: {error}")
                return False
    except Exception as e:
        print(f"\n❌ Error running inference: {e}")
        return False


def main():
    """Run all verification checks."""
    print("\n" + "="*60)
    print("RELATIONSHIP GENERATION FIXES - VERIFICATION")
    print("="*60)
    
    # Option to run inference first
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--run-inference':
        run_inference()
    
    # Run verifications
    results = {
        'company_drug': verify_company_drug_inference(),
        'publication_drug': verify_publication_drug_relationships(),
        'sec_filing_drug': verify_sec_filing_drug_relationships()
    }
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for check, passed in results.items():
        status = "✅ PASS" if passed else "⚠️  NEEDS DATA"
        print(f"{status}: {check}")
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("\nIf relationships are missing:")
    print("1. Run inference: python verify_relationship_fixes.py --run-inference")
    print("2. Reprocess sources: python -m src.processing.pipeline (for each source)")
    print("3. Check logs for extraction errors")
    print("\n" + "="*60)


if __name__ == '__main__':
    main()


