"""
Test drug extraction directly from a sample publication.
"""
from database.config import get_db_session
from src.processors.pubmed_processor import PubMedProcessor
from sqlalchemy.orm import Session

def test_drug_extraction():
    """Test drug extraction from a sample publication."""
    print("\n" + "="*60)
    print("TESTING DRUG EXTRACTION FROM PUBLICATION")
    print("="*60)
    
    with get_db_session() as session:
        # Check how many drugs exist in database
        from database.models import Drug
        drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        print(f"\n✅ Drugs in database: {drug_count}")
        
        if drug_count == 0:
            print("\n⚠️  No drugs in database - extraction won't find anything")
            print("   Need to process trials or other sources first to populate drugs")
            return
        
        # Get a sample drug name
        sample_drug = session.query(Drug).filter(Drug.deleted_at.is_(None)).first()
        if sample_drug:
            print(f"✅ Sample drug: {sample_drug.primary_name or sample_drug.generic_name}")
        
        # Create a test publication with a drug mention
        test_publication = {
            'pmid': '99999999',
            'title': f'Clinical trial of {sample_drug.primary_name if sample_drug else "aspirin"} in cancer patients',
            'abstract': f'This study evaluates the efficacy of {sample_drug.primary_name if sample_drug else "aspirin"} in treating cancer.',
            'source': 'Test Journal'
        }
        
        # Test extraction
        processor = PubMedProcessor(session)
        entities = processor.extract_entities(test_publication)
        
        print(f"\n✅ Entities extracted:")
        print(f"   - Publications: {len(entities.get('publications', []))}")
        print(f"   - Drugs: {len(entities.get('drugs', []))}")
        print(f"   - Diseases: {len(entities.get('diseases', []))}")
        
        if entities.get('drugs'):
            print("\n✅ Drug extraction working! Found drugs:")
            for drug in entities['drugs']:
                print(f"   - {drug.name}")
        else:
            print("\n⚠️  No drugs extracted")
            print("   This might mean:")
            print("   - Drug name normalization isn't matching")
            print("   - Need to check _get_all_drug_names() method")

if __name__ == '__main__':
    test_drug_extraction()




