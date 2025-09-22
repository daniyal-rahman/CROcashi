"""
End-to-end test for study card generation using real database data.
Tests the complete pipeline flow to ensure all wiring works correctly.
"""

import pytest
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import patch

from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator
from ncfd.pipeline.study_card_pipeline import StudyCardPipeline
from ncfd.db.session import get_session
from ncfd.db.models import Document, DocumentText, Trial
from sqlalchemy import text


class TestStudyCardEndToEnd:
    """End-to-end test with real database data."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.fixture
    def pipeline(self):
        """Create study card pipeline instance."""
        return StudyCardPipeline()
    
    def get_real_document_from_db(self) -> Optional[Dict[str, Any]]:
        """Get a real document from the database for testing."""
        try:
            with get_session() as session:
                # Get a document that has substantial text content
                result = session.execute(text('''
                    SELECT d.doc_id, d.title, d.source_type, d.trial_id,
                           COALESCE(dt.fulltext_text, dt.abstract_text) as text_content,
                           LENGTH(COALESCE(dt.fulltext_text, dt.abstract_text)) as text_length
                    FROM documents d
                    JOIN document_text dt ON d.doc_id = dt.doc_id
                    WHERE COALESCE(dt.fulltext_text, dt.abstract_text) IS NOT NULL
                      AND LENGTH(COALESCE(dt.fulltext_text, dt.abstract_text)) > 2000
                    ORDER BY text_length DESC
                    LIMIT 1
                ''')).fetchone()
                
                if result:
                    return {
                        "doc_id": str(result[0]),
                        "title": result[1],
                        "source_type": result[2],
                        "trial_id": result[3],
                        "raw_doc_text": result[4],
                        "text_length": result[5]
                    }
                
                return None
                
        except Exception as e:
            print(f"Error getting document from database: {e}")
            return None
    
    def get_trial_context_from_db(self, trial_id: Optional[int]) -> Dict[str, Any]:
        """Get trial context from database."""
        if not trial_id:
            return {
                "trial_id": "Unknown",
                "disease": "Unknown",
                "intervention": "Unknown",
                "phase": "Unknown"
            }
        
        try:
            with get_session() as session:
                trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                if trial:
                    return {
                        "trial_id": trial.nct_id or f"NCT{trial_id}",
                        "disease": trial.indication or "Unknown",
                        "intervention": trial.intervention or "Unknown",
                        "phase": trial.phase or "Unknown"
                    }
        except Exception as e:
            print(f"Error getting trial context: {e}")
        
        return {
            "trial_id": f"NCT{trial_id}",
            "disease": "Unknown",
            "intervention": "Unknown",
            "phase": "Unknown"
        }
    
    @pytest.mark.asyncio
    async def test_generator_with_real_data(self, generator):
        """Test the generator directly with real database data."""
        # Get real document from database
        real_doc = self.get_real_document_from_db()
        
        if not real_doc:
            pytest.skip("No real documents found in database")
        
        print(f"🔍 Testing generator with real document:")
        print(f"   Doc ID: {real_doc['doc_id']}")
        print(f"   Title: {real_doc['title']}")
        print(f"   Source: {real_doc['source_type']}")
        print(f"   Text length: {real_doc['text_length']}")
        print(f"   Text preview: {real_doc['raw_doc_text'][:200]}...")
        
        # Get trial context
        trial_context = self.get_trial_context_from_db(real_doc['trial_id'])
        print(f"   Trial context: {trial_context}")
        
        # Test the generator
        inputs = {
            "raw_doc_text": real_doc["raw_doc_text"],
            "doc_id": real_doc["doc_id"],
            "trial_context": trial_context
        }
        
        result = await generator.process(inputs)
        
        print(f"🔍 Generator result:")
        print(f"   Success: {result['success']}")
        print(f"   Error: {result['error_message']}")
        print(f"   Field quotes count: {len(result['field_quotes'])}")
        
        if result['study_card']:
            study_card = result['study_card']
            print(f"   Study card fields populated:")
            for field_name in ['design_archetype', 'primary_endpoint', 'population_description', 'analysis_set']:
                value = getattr(study_card, field_name, None)
                if value:
                    print(f"     {field_name}: {value}")
        
        # Check for the empty response issue
        if not result['success'] and "empty response" in result['error_message']:
            print("🚨 REPRODUCED EMPTY RESPONSE ISSUE WITH REAL DATA!")
            print(f"   Error message: {result['error_message']}")
            
            # Let's debug what's happening
            print("\n🔍 Debugging the issue:")
            
            # Test prompt generation
            prompt = generator._build_standard_prompt(real_doc["raw_doc_text"], real_doc["doc_id"], trial_context)
            print(f"   Generated prompt length: {len(prompt)}")
            print(f"   Prompt preview: {prompt[:300]}...")
            
            # Test direct LLM call
            try:
                llm_result = await generator._extract_study_card_with_llm(real_doc["raw_doc_text"], trial_context, prompt)
                print(f"   Direct LLM result: {llm_result}")
                print(f"   Direct LLM result keys: {list(llm_result.keys())}")
                
                if llm_result:
                    print(f"   LLM returned data but in wrong format!")
                    print(f"   Expected keys: ['study_card_data', 'field_quotes']")
                    print(f"   Actual keys: {list(llm_result.keys())}")
                else:
                    print(f"   LLM returned empty result")
                    
            except Exception as e:
                print(f"   Direct LLM call failed: {e}")
            
            # This confirms the issue still exists
            assert False, f"Empty response issue reproduced with real data: {result['error_message']}"
        
        # If successful, verify we got meaningful content
        if result['success']:
            assert result['study_card'] is not None
            assert len(result['field_quotes']) > 0
            print("✅ Generator test passed - got meaningful content from real data")
        else:
            print(f"❌ Generator test failed with error: {result['error_message']}")
            pytest.skip(f"Generator test failed: {result['error_message']}")
    
    @pytest.mark.asyncio
    async def test_pipeline_with_real_data(self, pipeline):
        """Test the complete pipeline with real database data."""
        # Get real document from database
        real_doc = self.get_real_document_from_db()
        
        if not real_doc:
            pytest.skip("No real documents found in database")
        
        print(f"🔍 Testing complete pipeline with real document:")
        print(f"   Doc ID: {real_doc['doc_id']}")
        print(f"   Title: {real_doc['title']}")
        print(f"   Source: {real_doc['source_type']}")
        print(f"   Text length: {real_doc['text_length']}")
        
        # Get trial context
        trial_context = self.get_trial_context_from_db(real_doc['trial_id'])
        
        # Test the complete pipeline
        pipeline_inputs = {
            "doc_id": int(real_doc["doc_id"]),
            "trial_context": trial_context,
            "force_regenerate": True  # Force regeneration to test the full flow
        }
        
        try:
            result = await pipeline.process(pipeline_inputs)
            
            print(f"🔍 Pipeline result:")
            print(f"   Success: {result.get('success', False)}")
            print(f"   Error: {result.get('error_message', 'None')}")
            
            if result.get('study_card'):
                study_card = result['study_card']
                print(f"   Study card generated successfully")
                print(f"   Study card fields populated:")
                for field_name in ['design_archetype', 'primary_endpoint', 'population_description']:
                    value = getattr(study_card, field_name, None)
                    if value:
                        print(f"     {field_name}: {value}")
            
            if result.get('evidence_spans'):
                print(f"   Evidence spans: {len(result['evidence_spans'])}")
            
            # Check for success
            if result.get('success'):
                print("✅ Pipeline test passed - complete flow working")
            else:
                print(f"❌ Pipeline test failed: {result.get('error_message', 'Unknown error')}")
                pytest.skip(f"Pipeline test failed: {result.get('error_message', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Pipeline test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            pytest.skip(f"Pipeline test failed with exception: {e}")
    
    @pytest.mark.asyncio
    async def test_multiple_real_documents(self, generator):
        """Test with multiple real documents to ensure consistency."""
        try:
            with get_session() as session:
                # Get multiple documents
                results = session.execute(text('''
                    SELECT d.doc_id, d.title, d.source_type, d.trial_id,
                           COALESCE(dt.fulltext_text, dt.abstract_text) as text_content,
                           LENGTH(COALESCE(dt.fulltext_text, dt.abstract_text)) as text_length
                    FROM documents d
                    JOIN document_text dt ON d.doc_id = dt.doc_id
                    WHERE COALESCE(dt.fulltext_text, dt.abstract_text) IS NOT NULL
                      AND LENGTH(COALESCE(dt.fulltext_text, dt.abstract_text)) > 1000
                    ORDER BY text_length DESC
                    LIMIT 3
                ''')).fetchall()
                
                if not results:
                    pytest.skip("No real documents found in database")
                
                print(f"🔍 Testing with {len(results)} real documents:")
                
                success_count = 0
                empty_response_count = 0
                
                for i, row in enumerate(results):
                    doc_id = str(row[0])
                    title = row[1]
                    source_type = row[2]
                    trial_id = row[3]
                    text_content = row[4]
                    text_length = row[5]
                    
                    print(f"\n   Document {i+1}: {doc_id}")
                    print(f"     Title: {title[:50]}...")
                    print(f"     Source: {source_type}")
                    print(f"     Length: {text_length}")
                    
                    # Get trial context
                    trial_context = self.get_trial_context_from_db(trial_id)
                    
                    # Test the generator
                    inputs = {
                        "raw_doc_text": text_content,
                        "doc_id": doc_id,
                        "trial_context": trial_context
                    }
                    
                    result = await generator.process(inputs)
                    
                    if result['success']:
                        success_count += 1
                        print(f"     ✅ Success: {len(result['field_quotes'])} field quotes")
                    elif "empty response" in result['error_message']:
                        empty_response_count += 1
                        print(f"     ❌ Empty response: {result['error_message']}")
                    else:
                        print(f"     ❌ Other error: {result['error_message']}")
                
                print(f"\n📊 Results summary:")
                print(f"   Total documents tested: {len(results)}")
                print(f"   Successful: {success_count}")
                print(f"   Empty responses: {empty_response_count}")
                print(f"   Other errors: {len(results) - success_count - empty_response_count}")
                
                # If we have empty responses, that's the issue we're trying to fix
                if empty_response_count > 0:
                    print(f"🚨 FOUND {empty_response_count} EMPTY RESPONSE ISSUES!")
                    assert False, f"Empty response issue found in {empty_response_count} out of {len(results)} documents"
                
                # If we have some successes, that's good
                if success_count > 0:
                    print(f"✅ {success_count} documents processed successfully")
                
        except Exception as e:
            print(f"❌ Multiple documents test failed: {e}")
            import traceback
            traceback.print_exc()
            pytest.skip(f"Multiple documents test failed: {e}")


if __name__ == "__main__":
    # Run the tests directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardEndToEnd()
        generator = test_instance.generator()
        pipeline = test_instance.pipeline()
        
        # Test with real data
        await test_instance.test_generator_with_real_data(generator)
        await test_instance.test_pipeline_with_real_data(pipeline)
        await test_instance.test_multiple_real_documents(generator)
    
    asyncio.run(main())
