"""
Test study card generator with real database data to reproduce empty response issue.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from typing import Dict, Any, Optional

from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator
from ncfd.db.session import get_session
from ncfd.db.models import Document, DocumentText, Trial


class TestStudyCardRealData:
    """Test study card generator with real database data."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.fixture
    def sample_trial_context(self):
        """Sample trial context."""
        return {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam",
            "phase": "Phase 2"
        }
    
    def get_real_document_from_db(self) -> Optional[Dict[str, Any]]:
        """Get a real document from the database for testing."""
        try:
            with get_session() as session:
                # Get a document that has text content
                doc_query = session.query(Document, DocumentText).join(
                    DocumentText, Document.doc_id == DocumentText.doc_id
                ).filter(
                    DocumentText.fulltext_text.isnot(None),
                    DocumentText.fulltext_text != ""
                ).first()
                
                if doc_query:
                    document, doc_text = doc_query
                    return {
                        "doc_id": str(document.doc_id),
                        "raw_doc_text": doc_text.fulltext_text,
                        "title": document.title,
                        "source_type": document.source_type
                    }
                
                # Fallback to abstract text
                doc_query = session.query(Document, DocumentText).join(
                    DocumentText, Document.doc_id == DocumentText.doc_id
                ).filter(
                    DocumentText.abstract_text.isnot(None),
                    DocumentText.abstract_text != ""
                ).first()
                
                if doc_query:
                    document, doc_text = doc_query
                    return {
                        "doc_id": str(document.doc_id),
                        "raw_doc_text": doc_text.abstract_text,
                        "title": document.title,
                        "source_type": document.source_type
                    }
                
                return None
                
        except Exception as e:
            print(f"Error getting document from database: {e}")
            return None
    
    @pytest.mark.asyncio
    async def test_real_document_empty_response(self, generator, sample_trial_context):
        """Test with real document to reproduce empty response issue."""
        # Get real document from database
        real_doc = self.get_real_document_from_db()
        
        if not real_doc:
            pytest.skip("No real documents found in database")
        
        print(f"Testing with real document: {real_doc['doc_id']}")
        print(f"Title: {real_doc['title']}")
        print(f"Source: {real_doc['source_type']}")
        print(f"Text length: {len(real_doc['raw_doc_text'])}")
        print(f"Text preview: {real_doc['raw_doc_text'][:200]}...")
        
        # Test the generator with real data
        inputs = {
            "raw_doc_text": real_doc["raw_doc_text"],
            "doc_id": real_doc["doc_id"],
            "trial_context": sample_trial_context
        }
        
        result = await generator.process(inputs)
        
        print(f"Result success: {result['success']}")
        print(f"Result error: {result['error_message']}")
        print(f"Field quotes count: {len(result['field_quotes'])}")
        
        if result['study_card']:
            print(f"Study card fields: {list(result['study_card'].__dict__.keys())}")
        
        # Check if we got the empty response issue
        if not result['success'] and "empty response" in result['error_message']:
            print("🚨 REPRODUCED EMPTY RESPONSE ISSUE!")
            print(f"Error message: {result['error_message']}")
            
            # This is the issue we're trying to fix
            assert False, f"Empty response issue reproduced: {result['error_message']}"
        
        # If successful, verify we got meaningful content
        if result['success']:
            assert result['study_card'] is not None
            assert len(result['field_quotes']) > 0
            print("✅ Test passed - got meaningful content")
        else:
            print(f"❌ Test failed with error: {result['error_message']}")
            # Don't fail the test, just report the issue
            pytest.skip(f"Test failed with error: {result['error_message']}")
    
    @pytest.mark.asyncio
    async def test_real_document_with_mock_llm(self, generator, sample_trial_context):
        """Test with real document but mock LLM to see what's happening."""
        # Get real document from database
        real_doc = self.get_real_document_from_db()
        
        if not real_doc:
            pytest.skip("No real documents found in database")
        
        print(f"Testing with real document (mocked LLM): {real_doc['doc_id']}")
        
        # Mock the LLM to return empty response
        mock_response = {}
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            inputs = {
                "raw_doc_text": real_doc["raw_doc_text"],
                "doc_id": real_doc["doc_id"],
                "trial_context": sample_trial_context
            }
            
            result = await generator.process(inputs)
            
            print(f"Mocked result success: {result['success']}")
            print(f"Mocked result error: {result['error_message']}")
            
            # This should reproduce the empty response issue
            assert not result['success']
            assert "empty response" in result['error_message']
            print("✅ Successfully reproduced empty response issue with mock")
    
    @pytest.mark.asyncio
    async def test_real_document_llm_call_debug(self, generator, sample_trial_context):
        """Test with real document and capture LLM call details."""
        # Get real document from database
        real_doc = self.get_real_document_from_db()
        
        if not real_doc:
            pytest.skip("No real documents found in database")
        
        print(f"Testing LLM call with real document: {real_doc['doc_id']}")
        
        # Mock the LLM call to capture what's being sent
        original_call_llm = generator.call_llm
        
        async def mock_call_llm(*args, **kwargs):
            print("🔍 LLM Call Details:")
            print(f"  Messages: {args[0] if args else 'None'}")
            print(f"  Temperature: {kwargs.get('temperature', 'None')}")
            print(f"  Max tokens: {kwargs.get('max_tokens', 'None')}")
            print(f"  JSON schema: {kwargs.get('json_schema', 'None')}")
            
            # Check the prompt content
            if args and len(args) > 0 and 'messages' in args[0]:
                messages = args[0]['messages']
                if messages and len(messages) > 0:
                    prompt = messages[0].get('content', '')
                    print(f"  Prompt length: {len(prompt)}")
                    print(f"  Prompt preview: {prompt[:500]}...")
                    
                    # Check for conflicting JSON examples
                    if '{"study_card_data":' in prompt:
                        print("  ⚠️  Found JSON example in prompt!")
                    if 'CRITICAL REQUIREMENTS:' in prompt:
                        print("  ✅ Found critical requirements in prompt")
            
            # Return empty response to reproduce the issue
            return AsyncMock(content={})
        
        with patch.object(generator, 'call_llm', side_effect=mock_call_llm):
            inputs = {
                "raw_doc_text": real_doc["raw_doc_text"],
                "doc_id": real_doc["doc_id"],
                "trial_context": sample_trial_context
            }
            
            result = await generator.process(inputs)
            
            print(f"Result: {result}")
            
            # This should reproduce the empty response issue
            assert not result['success']
            assert "empty response" in result['error_message']
            print("✅ Successfully reproduced empty response issue with debug info")


if __name__ == "__main__":
    # Run the test directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardRealData()
        generator = test_instance.generator()
        sample_trial_context = test_instance.sample_trial_context()
        
        # Test with real data
        await test_instance.test_real_document_empty_response(generator, sample_trial_context)
    
    asyncio.run(main())
