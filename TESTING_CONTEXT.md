# Complete Testing Context for CROcashi Pipeline

## Current System State

### Database Status
- **Trial**: NCT05515666 (Cassava Sciences Simufilam Phase 2 study)
- **Documents**: 9 test documents created and linked to trial
- **Company**: Cassava Sciences, Inc. with aliases configured
- **Trial Doc Candidates**: All 9 documents marked as selected for processing

### Recent Enhancements
- ✅ Enhanced logging system with detailed LLM call tracking
- ✅ JATS XML implementation for comprehensive fulltext retrieval
- ✅ Text normalization for consistent character counting
- ✅ Database sequence fixes for document insertion
- ✅ Document linking via NCT IDs

## Critical Issues Requiring Resolution

### 1. LLM Provider Configuration Failure
**Problem**: LLM calls failing with `'OpenAIProvider' object has no attribute 'model_name'`

**Root Cause Analysis**:
- The model configuration from `config/llm_models.yaml` is not being properly passed to the LLM provider
- Worker-specific model assignments are not being applied correctly
- The provider initialization doesn't receive the correct model name from the worker config

**Files to Investigate**:
- `src/ncfd/llm/providers/openai_provider.py` (lines 27-31)
- `src/ncfd/llm/config.py` (worker configuration loading)
- `config/llm_models.yaml` (worker-specific model assignments)

**Expected Configuration**:
```yaml
workers:
  LLMMethodCardGenerator:
    provider: openai
    model: gpt-5-mini
  LLMResultsFactsheetGenerator:
    provider: openai
    model: gpt-5-mini
  LLMGateAssessmentGenerator:
    provider: openai
    model: gpt-5-mini
```

### 2. Text Length Validation Issues
**Problem**: Pipeline reports "Fulltext too short (998 chars)" and "Abstract too short (66 chars)"

**Current Test Data**:
- Documents have 998-character fulltext (below threshold)
- Abstracts have 66 characters (below threshold)
- Retriever requires longer content for quality processing

**Files to Check**:
- `src/ncfd/extract/workers/retriever_enhanced.py` (minimum length thresholds)
- `src/ncfd/ingest/pubmed/oa_worker.py` (text storage logic)

**Potential Solutions**:
1. Increase test document fulltext to 2000+ characters
2. Lower minimum text length thresholds in retriever
3. Use JATS XML method to get more complete content

### 3. Pipeline Execution Hanging
**Problem**: Pipeline starts but may hang during LLM processing

**Symptoms**:
- Multiple failed LLM calls with model_name errors
- Pipeline processes 0 documents despite 9 being available
- Execution time around 10 seconds with no successful completions

## Detailed Testing Protocol

### Phase 1: Configuration Verification

#### Test 1.1: LLM Provider Initialization
```python
# Test script: test_llm_provider_config.py
import sys
sys.path.append('src')
from ncfd.llm.providers.openai_provider import OpenAIProvider
from ncfd.config import get_config

def test_llm_provider_config():
    config = get_config('config/llm_models.yaml')
    
    # Test worker-specific config
    worker_config = config.get('workers', {}).get('LLMMethodCardGenerator', {})
    print(f"Worker config: {worker_config}")
    
    # Test provider initialization
    provider_config = {
        'model': worker_config.get('model', 'gpt-5-mini'),
        'api_key_env': 'OPENAI_API_KEY'
    }
    
    provider = OpenAIProvider(provider_config)
    print(f"Provider model_name: {provider.model_name}")
    print(f"Provider name: {provider.provider_name}")
    
    return provider.model_name == 'gpt-5-mini'

if __name__ == "__main__":
    success = test_llm_provider_config()
    print(f"Configuration test: {'PASS' if success else 'FAIL'}")
```

#### Test 1.2: Worker Configuration Loading
```python
# Test script: test_worker_config_loading.py
import sys
sys.path.append('src')
from ncfd.extract.workers.llm.llm_method_card_generator import LLMMethodCardGenerator
from ncfd.config import get_config

def test_worker_config_loading():
    config = get_config('config/single_trial_test.yaml')
    
    # Test worker initialization
    worker = LLMMethodCardGenerator(config)
    
    print(f"Worker LLM provider: {worker.llm_provider}")
    print(f"Provider model_name: {getattr(worker.llm_provider, 'model_name', 'NOT_FOUND')}")
    print(f"Provider name: {worker.llm_provider.provider_name}")
    
    return hasattr(worker.llm_provider, 'model_name')

if __name__ == "__main__":
    success = test_worker_config_loading()
    print(f"Worker config test: {'PASS' if success else 'FAIL'}")
```

### Phase 2: Text Length Resolution

#### Test 2.1: Current Text Lengths
```python
# Test script: test_text_lengths.py
import sys
sys.path.append('src')
from ncfd.db.session import get_session
from sqlalchemy import text

def check_text_lengths():
    with get_session() as session:
        result = session.execute(text('''
            SELECT doc_id, 
                   LENGTH(fulltext_text) as fulltext_len,
                   LENGTH(abstract_text) as abstract_len,
                   char_count_fulltext,
                   char_count_abstract
            FROM document_text 
            ORDER BY doc_id
        '''))
        
        texts = result.fetchall()
        print("Current text lengths:")
        for text in texts:
            print(f"  Doc {text.doc_id}: fulltext={text.fulltext_len}, abstract={text.abstract_len}")
            print(f"    Stored counts: fulltext={text.char_count_fulltext}, abstract={text.char_count_abstract}")
        
        return texts

if __name__ == "__main__":
    check_text_lengths()
```

#### Test 2.2: Retriever Thresholds
```python
# Test script: test_retriever_thresholds.py
import sys
sys.path.append('src')
from ncfd.extract.workers.retriever_enhanced import EnhancedRetriever

def test_retriever_thresholds():
    retriever = EnhancedRetriever()
    
    # Check minimum length requirements
    print(f"Retriever max_span_length: {retriever.max_span_length}")
    print(f"Retriever min_confidence: {retriever.min_confidence}")
    
    # Test with current document
    trial_context = {
        'trial_id': 1,
        'nct_id': 'NCT05515666',
        'brief_title': 'A Phase 2 Study of Simufilam in Patients with Alzheimer Disease',
        'indication': 'Alzheimer Disease',
        'date_window': '2020-2024'
    }
    
    result = retriever.process(trial_context)
    print(f"Retriever result: {result.success}")
    print(f"Documents found: {len(result.output.get('document_cards', []))}")
    
    return result

if __name__ == "__main__":
    test_retriever_thresholds()
```

### Phase 3: Complete Pipeline Testing

#### Test 3.1: Single Document Processing
```python
# Test script: test_single_document_processing.py
import asyncio
import sys
sys.path.append('src')
from ncfd.ingest.pubmed.studycard_worker import StudyCardWorker
from ncfd.config import get_config
from ncfd.ingest.pubmed.queue_service import TaskQueueService

async def test_single_document_processing():
    print("=== TESTING SINGLE DOCUMENT PROCESSING ===")
    
    config = get_config('config/single_trial_test.yaml')
    queue_service = TaskQueueService(config)
    worker = StudyCardWorker(queue_service, config)
    
    # Test with just one document first
    result = await worker.process_studycard_task({
        'id': 1,
        'task_type': 'STUDYCARD',
        'task_key': 'test_single_doc',
        'trial_id': 1,
        'company_id': 1,
        'payload': {'source': 'single_doc_test', 'trial_id': 1}
    })
    
    print(f"Single document result:")
    print(f"  Success: {result.success}")
    print(f"  Documents processed: {result.documents_processed}")
    print(f"  Method cards: {result.method_cards}")
    print(f"  Results cards: {result.results_cards}")
    print(f"  Gates passed: {result.gates_passed}")
    print(f"  Gates failed: {result.gates_failed}")
    print(f"  Execution time: {result.execution_time:.2f}s")
    print(f"  Error message: {result.error_message}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_single_document_processing())
```

#### Test 3.2: Full Pipeline with Enhanced Logging
```python
# Test script: test_full_pipeline_with_logging.py
import asyncio
import sys
sys.path.append('src')
from ncfd.ingest.pubmed.studycard_worker import StudyCardWorker
from ncfd.config import get_config
from ncfd.ingest.pubmed.queue_service import TaskQueueService

async def test_full_pipeline_with_logging():
    print("=== TESTING FULL PIPELINE WITH ENHANCED LOGGING ===")
    
    config = get_config('config/single_trial_test.yaml')
    queue_service = TaskQueueService(config)
    worker = StudyCardWorker(queue_service, config)
    
    # Process all documents with detailed logging
    result = await worker.process_studycard_task({
        'id': 1,
        'task_type': 'STUDYCARD',
        'task_key': 'test_full_pipeline_logging',
        'trial_id': 1,
        'company_id': 1,
        'payload': {'source': 'full_pipeline_logging_test', 'trial_id': 1}
    })
    
    print(f"\n=== FULL PIPELINE RESULTS ===")
    print(f"Success: {result.success}")
    print(f"Documents processed: {result.documents_processed}")
    print(f"Study cards generated: {result.study_cards_generated}")
    print(f"Method cards: {result.method_cards}")
    print(f"Results cards: {result.results_cards}")
    print(f"Gates passed: {result.gates_passed}")
    print(f"Gates failed: {result.gates_failed}")
    print(f"Execution time: {result.execution_time:.2f}s")
    print(f"Error message: {result.error_message}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_full_pipeline_with_logging())
```

### Phase 4: Results Verification

#### Test 4.1: Database State Verification
```python
# Test script: verify_database_results.py
import sys
sys.path.append('src')
from ncfd.db.session import get_session
from sqlalchemy import text

def verify_database_results():
    with get_session() as session:
        print("=== DATABASE RESULTS VERIFICATION ===")
        
        # Check method cards
        result = session.execute(text('SELECT COUNT(*) as count FROM method_cards'))
        method_count = result.fetchone().count
        print(f"Method Cards: {method_count}")
        
        # Check results factsheets
        result = session.execute(text('SELECT COUNT(*) as count FROM results_factsheets'))
        results_count = result.fetchone().count
        print(f"Results Factsheets: {results_count}")
        
        # Check gate assessments
        result = session.execute(text('SELECT COUNT(*) as count FROM gate_assessments'))
        gates_count = result.fetchone().count
        print(f"Gate Assessments: {gates_count}")
        
        # Check evidence spans
        result = session.execute(text('SELECT COUNT(*) as count FROM evidence_spans'))
        spans_count = result.fetchone().count
        print(f"Evidence Spans: {spans_count}")
        
        # Check documents
        result = session.execute(text('SELECT doc_id, pmid, title FROM documents ORDER BY doc_id'))
        docs = result.fetchall()
        print(f"\nDocuments: {len(docs)}")
        for doc in docs:
            print(f"  Doc {doc.doc_id}: PMID {doc.pmid} - {doc.title[:50]}...")
        
        # Expected results
        expected_method_cards = 9
        expected_results_cards = 9
        expected_gate_assessments = 36  # 4 gates × 9 docs
        expected_evidence_spans = 50+  # Multiple spans per document
        
        print(f"\n=== EXPECTED vs ACTUAL ===")
        print(f"Method Cards: {method_count}/{expected_method_cards} {'✓' if method_count == expected_method_cards else '✗'}")
        print(f"Results Cards: {results_count}/{expected_results_cards} {'✓' if results_count == expected_results_cards else '✗'}")
        print(f"Gate Assessments: {gates_count}/{expected_gate_assessments} {'✓' if gates_count == expected_gate_assessments else '✗'}")
        print(f"Evidence Spans: {spans_count}/{expected_evidence_spans} {'✓' if spans_count >= expected_evidence_spans else '✗'}")
        
        return {
            'method_cards': method_count,
            'results_cards': results_count,
            'gate_assessments': gates_count,
            'evidence_spans': spans_count,
            'documents': len(docs)
        }

if __name__ == "__main__":
    verify_database_results()
```

## Expected Test Outcomes

### Successful Test Results
- **Method Cards**: 9 (one per document)
- **Results Factsheets**: 9 (one per document)
- **Gate Assessments**: 36 (4 gates × 9 documents)
- **Evidence Spans**: 50+ (multiple spans per document with quotes)
- **Execution Time**: < 60 seconds for all documents
- **LLM Calls**: All successful with proper model names logged

### Failure Indicators
- **LLM Provider Errors**: `'OpenAIProvider' object has no attribute 'model_name'`
- **Text Length Errors**: "Fulltext too short" or "Abstract too short"
- **Zero Results**: 0 method cards, 0 results cards, 0 gate assessments
- **Hanging**: Pipeline runs indefinitely without completion
- **Database Errors**: Primary key violations or constraint errors

## Key Files to Monitor

### Configuration Files
- `config/llm_models.yaml` - LLM provider and model configuration
- `config/single_trial_test.yaml` - Test environment configuration

### Core Implementation Files
- `src/ncfd/llm/providers/openai_provider.py` - LLM provider implementation
- `src/ncfd/extract/workers/base_llm_worker.py` - Base LLM worker with logging
- `src/ncfd/extract/workers/retriever_enhanced.py` - Document retrieval logic
- `src/ncfd/ingest/pubmed/studycard_worker.py` - Main study card worker
- `src/ncfd/pipeline/direct_study_card_pipeline.py` - Pipeline orchestration

### Database Files
- `src/ncfd/db/models.py` - Database schema definitions
- `src/ncfd/db/session.py` - Database session management

## Troubleshooting Guide

### If LLM Provider Fails
1. Check `config/llm_models.yaml` worker configurations
2. Verify model names match between config and provider
3. Ensure API key is set in environment variables
4. Check provider initialization in worker constructors

### If Text Length Validation Fails
1. Increase test document fulltext to 2000+ characters
2. Check retriever minimum length thresholds
3. Verify JATS XML implementation is working
4. Test with real PMC documents if available

### If Pipeline Hangs
1. Check LLM API rate limits and timeouts
2. Verify all required environment variables are set
3. Test with single document first
4. Check database connection and transaction handling

### If Results Are Incomplete
1. Verify all 9 documents are properly linked to trial
2. Check document text content and length
3. Ensure all LLM workers are properly configured
4. Verify database schema and constraints

## Success Criteria

The pipeline test is considered successful when:
1. All 9 documents are processed without errors
2. Complete study cards are generated (method, results, gates)
3. Evidence spans are created with proper quotes and positions
4. All LLM calls complete successfully with proper logging
5. Database contains expected counts of all card types
6. Total execution time is reasonable (< 2 minutes)

This comprehensive testing protocol will identify and resolve all remaining issues in the CROcashi pipeline system.
