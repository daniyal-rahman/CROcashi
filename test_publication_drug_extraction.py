"""
Test script to verify publication-drug extraction is working.
"""
import sys
from database.config import get_db_session
from src.processing.pipeline import ProcessingPipeline

def test_publication_drug_extraction():
    """Test reprocessing a small batch of PubMed publications."""
    print("\n" + "="*60)
    print("TESTING PUBLICATION-DRUG EXTRACTION")
    print("="*60)
    
    pipeline = ProcessingPipeline(batch_size=10)
    
    print("\nReprocessing 10 PubMed publications...")
    stats = pipeline.process_source('pubmed', limit=10)
    
    print(f"\n✅ Processing completed:")
    print(f"   - Records processed: {stats.get('records_processed', 0)}")
    print(f"   - Entities created: {stats.get('entities_created', 0)}")
    print(f"   - Relationships created: {stats.get('relationships_created', 0)}")
    
    # Check results
    with get_db_session() as session:
        from sqlalchemy import text
        
        # Count publication-drug relationships
        query = text("""
            SELECT COUNT(*) as count
            FROM publication_drugs
            WHERE deleted_at IS NULL
        """)
        result = session.execute(query).fetchone()
        count = result[0] if result else 0
        
        print(f"\n✅ Total publication-drug relationships: {count}")
        
        if count > 0:
            # Sample relationships
            query_sample = text("""
                SELECT p.title, d.primary_name as drug_name
                FROM publication_drugs pd
                JOIN publications p ON pd.pub_id = p.pub_id
                JOIN drugs d ON pd.drug_id = d.drug_id
                WHERE pd.deleted_at IS NULL
                AND p.deleted_at IS NULL
                AND d.deleted_at IS NULL
                LIMIT 5
            """)
            samples = session.execute(query_sample).fetchall()
            
            print("\n✅ Sample relationships:")
            for row in samples:
                title = (row[0] or "No title")[:60] + "..." if row[0] and len(row[0]) > 60 else (row[0] or "No title")
                print(f"   - {title}")
                print(f"     → {row[1]}")
        else:
            print("\n⚠️  No relationships found yet")
            print("   This might mean:")
            print("   - Publications don't mention known drugs")
            print("   - Drug names in publications don't match database")
            print("   - Need to check extraction logs")

if __name__ == '__main__':
    test_publication_drug_extraction()


