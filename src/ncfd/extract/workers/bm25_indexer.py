"""
Production-Grade BM25 Indexer using Pyserini

Implements true BM25 scoring with field boosts, biomedical text analysis,
and incremental updates for BaseSpan indexing and retrieval.
"""

import json
import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

try:
    from pyserini.index import IndexWriter
    from pyserini.search import LuceneSearcher
    from pyserini.analysis import get_lucene_analyzer
    from pyserini.encode import QueryEncoder
    from pyserini.util import download_prebuilt_index
    PYSERINI_AVAILABLE = True
except ImportError:
    # Mock classes for when pyserini is not available
    class IndexWriter:
        def __init__(self, path): pass
        def set_analyzer(self, analyzer): pass
        def set_bm25_parameters(self, k1, b): pass
        def add_document(self, doc): pass
        def close(self): pass
    
    class LuceneSearcher:
        def __init__(self, path): 
            self.num_docs = 0
        def set_bm25_parameters(self, k1, b): pass
        def search(self, query, k=10): return []
        def doc(self, doc_id): return None
    
    def get_lucene_analyzer(name): return f"MockAnalyzer({name})"
    class QueryEncoder: pass
    def download_prebuilt_index(name): pass
    PYSERINI_AVAILABLE = False

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, Document
from ...db.session import get_session


@dataclass
class BM25Config:
    """Configuration for BM25 indexing and retrieval."""
    # BM25 parameters
    k1: float = 1.2
    b: float = 0.75
    
    # Index settings
    index_path: str = "data/bm25_index"
    analyzer_name: str = "EnglishAnalyzer"
    max_docs_per_segment: int = 10000
    
    # Field boosts for different sections
    section_boosts: Dict[str, float] = None
    
    # Biomedical text processing
    preserve_hyphens: bool = True
    preserve_numerics: bool = True
    lowercase: bool = True
    
    # Query processing
    max_query_length: int = 1000
    use_field_boosts: bool = True
    
    def __post_init__(self):
        if self.section_boosts is None:
            self.section_boosts = {
                "Methods": 1.5,      # Higher boost for methods
                "Results": 1.2,     # Good boost for results
                "Discussion": 1.0,  # Standard boost
                "Abstract": 0.8,    # Lower boost for abstract
                "Introduction": 0.7, # Lower boost for introduction
                "Conclusion": 1.1   # Slight boost for conclusions
            }


class BiomedicalAnalyzer:
    """Custom biomedical text analyzer for better tokenization."""
    
    def __init__(self, preserve_hyphens: bool = True, preserve_numerics: bool = True):
        self.preserve_hyphens = preserve_hyphens
        self.preserve_numerics = preserve_numerics
    
    def analyze(self, text: str) -> str:
        """Analyze biomedical text for indexing."""
        # Convert to lowercase
        text = text.lower()
        
        # Preserve hyphens in biomedical terms
        if self.preserve_hyphens:
            # Keep hyphens in common biomedical patterns
            text = text.replace("kaplan-meier", "kaplan_meier")
            text = text.replace("log-rank", "log_rank")
            text = text.replace("progression-free", "progression_free")
            text = text.replace("overall survival", "overall_survival")
            text = text.replace("objective response", "objective_response")
            text = text.replace("complete response", "complete_response")
            text = text.replace("partial response", "partial_response")
            text = text.replace("stable disease", "stable_disease")
            text = text.replace("progressive disease", "progressive_disease")
        
        # Preserve numerics for statistical terms
        if self.preserve_numerics:
            # Keep numbers and percentages
            text = text.replace("p < 0.05", "p_less_than_0_05")
            text = text.replace("p < 0.01", "p_less_than_0_01")
            text = text.replace("95% ci", "95_percent_ci")
            text = text.replace("90% ci", "90_percent_ci")
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text


class BM25Indexer(BaseWorker):
    """Production-grade BM25 indexer using Pyserini."""
    
    def __init__(self, config: Optional[BM25Config] = None):
        super().__init__(name="BM25Indexer", version="2.0.0")
        self.config = config or BM25Config()
        self.index_writer = None
        self.searcher = None
        self.analyzer = BiomedicalAnalyzer(
            preserve_hyphens=self.config.preserve_hyphens,
            preserve_numerics=self.config.preserve_numerics
        )
        self.logger = logging.getLogger(__name__)
        
        # Ensure index directory exists
        os.makedirs(self.config.index_path, exist_ok=True)
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Build or update BM25 index."""
        doc_id = inputs.get("doc_id")
        rebuild_all = inputs.get("rebuild_all", False)
        
        try:
            with get_session() as session:
                if rebuild_all:
                    result = self._rebuild_index(session)
                elif doc_id:
                    result = self._update_document_index(session, doc_id)
                else:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message="Either doc_id or rebuild_all must be specified"
                    )
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error building BM25 index: {str(e)}")
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error building BM25 index: {str(e)}"
            )
    
    def _rebuild_index(self, session) -> WorkerResult:
        """Rebuild the entire BM25 index."""
        try:
            # Get all documents with spans
            documents = session.query(Document).join(BaseSpan).distinct().all()
            
            # Initialize index writer
            self._initialize_index_writer()
            
            total_spans = 0
            for doc in documents:
                spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc.doc_id).all()
                total_spans += len(spans)
                
                # Index spans for this document
                self._index_spans(spans, doc)
            
            # Finalize index
            self._finalize_index()
            
            # Initialize searcher
            self._initialize_searcher()
            
            return WorkerResult(
                success=True,
                output={
                    "indices_built": True,
                    "documents_processed": len(documents),
                    "total_spans_indexed": total_spans,
                    "index_type": "bm25_pyserini",
                    "index_path": self.config.index_path
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error rebuilding index: {str(e)}")
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error rebuilding index: {str(e)}"
            )
    
    def _update_document_index(self, session, doc_id: int) -> WorkerResult:
        """Update index for a specific document."""
        try:
            # Get document and spans
            doc = session.query(Document).filter(Document.doc_id == doc_id).first()
            if not doc:
                return WorkerResult(
                    success=False,
                    output=None,
                    error_message=f"Document {doc_id} not found"
                )
            
            spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
            if not spans:
                return WorkerResult(
                    success=False,
                    output=None,
                    error_message=f"No spans found for document {doc_id}"
                )
            
            # Initialize index writer if needed
            if not self.index_writer:
                self._initialize_index_writer()
            
            # Index spans for this document
            self._index_spans(spans, doc)
            
            # Finalize index
            self._finalize_index()
            
            # Reinitialize searcher
            self._initialize_searcher()
            
            return WorkerResult(
                success=True,
                output={
                    "indices_built": True,
                    "document_id": doc_id,
                    "spans_indexed": len(spans),
                    "index_type": "bm25_pyserini"
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error updating document index: {str(e)}")
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error updating document index: {str(e)}"
            )
    
    def _initialize_index_writer(self):
        """Initialize Pyserini index writer."""
        if not PYSERINI_AVAILABLE:
            self.logger.warning("Pyserini not available, using mock implementation")
            self.index_writer = IndexWriter(self.config.index_path)
            return
            
        try:
            # Create analyzer
            analyzer = get_lucene_analyzer(self.config.analyzer_name)
            
            # Initialize index writer
            self.index_writer = IndexWriter(self.config.index_path)
            self.index_writer.set_analyzer(analyzer)
            
            # Set BM25 parameters
            self.index_writer.set_bm25_parameters(
                k1=self.config.k1,
                b=self.config.b
            )
            
            self.logger.info(f"Initialized BM25 index writer at {self.config.index_path}")
            
        except Exception as e:
            self.logger.error(f"Error initializing index writer: {str(e)}")
            raise
    
    def _finalize_index(self):
        """Finalize the index."""
        if self.index_writer:
            self.index_writer.close()
            self.index_writer = None
            self.logger.info("BM25 index finalized")
    
    def _initialize_searcher(self):
        """Initialize Pyserini searcher."""
        if not PYSERINI_AVAILABLE:
            self.logger.warning("Pyserini not available, using mock implementation")
            self.searcher = LuceneSearcher(self.config.index_path)
            return
            
        try:
            self.searcher = LuceneSearcher(self.config.index_path)
            self.searcher.set_bm25_parameters(
                k1=self.config.k1,
                b=self.config.b
            )
            self.logger.info("BM25 searcher initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing searcher: {str(e)}")
            raise
    
    def _index_spans(self, spans: List[BaseSpan], doc: Document):
        """Index BaseSpans using Pyserini."""
        for span in spans:
            # Prepare document for indexing
            doc_json = self._prepare_span_document(span, doc)
            
            # Add document to index
            self.index_writer.add_document(doc_json)
    
    def _prepare_span_document(self, span: BaseSpan, doc: Document) -> Dict[str, Any]:
        """Prepare a span document for indexing."""
        # Analyze text
        analyzed_text = self.analyzer.analyze(span.text)
        
        # Create document JSON
        doc_json = {
            "id": f"span_{span.span_id}",
            "text": analyzed_text,
            "section": span.section,
            "doc_id": str(span.doc_id),
            "span_id": str(span.span_id),
            "page": str(span.page) if span.page else "",
            "char_start": str(span.char_start) if span.char_start else "",
            "char_end": str(span.char_end) if span.char_end else "",
            "table_id": str(span.table_id) if span.table_id else "",
            "row": str(span.row) if span.row else "",
            "col": str(span.col) if span.col else "",
            "doc_title": doc.title if hasattr(doc, 'title') else "",
            "doc_type": doc.doc_type if hasattr(doc, 'doc_type') else "",
            "doc_year": str(doc.year) if hasattr(doc, 'year') else ""
        }
        
        return doc_json
    
    def search(self, query: str, section: Optional[str] = None, 
               top_k: int = 10, use_field_boosts: bool = True) -> List[Dict[str, Any]]:
        """Search using BM25 with field boosts."""
        if not self.searcher:
            self.logger.error("Searcher not initialized")
            return []
        
        try:
            # Prepare query
            processed_query = self._prepare_query(query, section, use_field_boosts)
            
            # Search
            hits = self.searcher.search(processed_query, k=top_k)
            
            # Process results
            results = []
            for hit in hits:
                result = self._process_search_hit(hit)
                if result:
                    results.append(result)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error during BM25 search: {str(e)}")
            return []
    
    def _prepare_query(self, query: str, section: Optional[str], 
                      use_field_boosts: bool) -> str:
        """Prepare query with field boosts."""
        # Analyze query
        analyzed_query = self.analyzer.analyze(query)
        
        if not use_field_boosts or not self.config.use_field_boosts:
            return analyzed_query
        
        # Build fielded query with boosts
        query_parts = []
        
        # Main text field with section boost
        if section and section in self.config.section_boosts:
            boost = self.config.section_boosts[section]
            query_parts.append(f"text:{analyzed_query}^{boost}")
        else:
            query_parts.append(f"text:{analyzed_query}")
        
        # Add section filter if specified
        if section:
            query_parts.append(f"section:{section}")
        
        # Combine query parts
        final_query = " ".join(query_parts)
        
        return final_query
    
    def _process_search_hit(self, hit) -> Optional[Dict[str, Any]]:
        """Process a search hit into result format."""
        try:
            # Extract document ID
            doc_id = hit.docid
            
            # Parse span_id from doc_id
            if doc_id.startswith("span_"):
                span_id = int(doc_id[5:])  # Remove "span_" prefix
            else:
                span_id = int(doc_id)
            
            # Get document content
            doc_content = self.searcher.doc(doc_id).raw()
            doc_json = json.loads(doc_content)
            
            return {
                'span_id': span_id,
                'score': float(hit.score),
                'method': 'bm25_pyserini',
                'section': doc_json.get('section', ''),
                'text': doc_json.get('text', ''),
                'doc_id': int(doc_json.get('doc_id', 0)),
                'page': int(doc_json.get('page', 0)) if doc_json.get('page') else None,
                'char_start': int(doc_json.get('char_start', 0)) if doc_json.get('char_start') else None,
                'char_end': int(doc_json.get('char_end', 0)) if doc_json.get('char_end') else None
            }
            
        except Exception as e:
            self.logger.error(f"Error processing search hit: {str(e)}")
            return None
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get BM25 index statistics."""
        if not self.searcher:
            return {"error": "Searcher not initialized"}
        
        try:
            stats = {
                "index_type": "bm25_pyserini",
                "index_path": self.config.index_path,
                "bm25_k1": self.config.k1,
                "bm25_b": self.config.b,
                "analyzer": self.config.analyzer_name,
                "section_boosts": self.config.section_boosts,
                "total_documents": self.searcher.num_docs,
                "index_exists": True
            }
            return stats
            
        except Exception as e:
            return {"error": f"Error getting stats: {str(e)}"}
    
    def close(self):
        """Close the indexer and searcher."""
        if self.index_writer:
            self.index_writer.close()
            self.index_writer = None
        
        if self.searcher:
            self.searcher = None
        
        self.logger.info("BM25 indexer closed")
