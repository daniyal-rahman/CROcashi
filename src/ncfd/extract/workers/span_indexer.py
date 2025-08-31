"""
Span Indexer Worker

Builds BM25 and dense indices over BaseSpans for efficient retrieval and span triage.
"""

import json
import pickle
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import faiss

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, Document
from ...db.session import get_session


@dataclass
class IndexingConfig:
    """Configuration for span indexing."""
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    dense_dimension: int = 768
    dense_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    min_token_length: int = 2
    max_features: int = 10000
    normalize_tokens: bool = True
    preserve_numerics: bool = True


class SpanIndexer(BaseWorker):
    """Worker for building and maintaining span indices."""
    
    def __init__(self, config: Optional[IndexingConfig] = None):
        super().__init__(name="SpanIndexer", version="1.0.0")
        self.config = config or IndexingConfig()
        self.bm25_index = None
        self.dense_index = None
        self.span_mapping = {}
        self.feature_names = []
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Build or update span indices."""
        doc_id = inputs.get("doc_id")
        rebuild_all = inputs.get("rebuild_all", False)
        
        try:
            with get_session() as session:
                if rebuild_all:
                    # Rebuild indices for all documents
                    result = self._rebuild_all_indices(session)
                elif doc_id:
                    # Build/update indices for specific document
                    result = self._build_document_indices(session, doc_id)
                else:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message="Either doc_id or rebuild_all must be specified"
                    )
                
                return result
                
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error building indices: {str(e)}"
            )
    
    def _rebuild_all_indices(self, session) -> WorkerResult:
        """Rebuild indices for all documents."""
        # Get all documents with spans
        documents = session.query(Document).join(BaseSpan).distinct().all()
        
        total_spans = 0
        for doc in documents:
            spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc.doc_id).all()
            total_spans += len(spans)
        
        # Build global indices
        self._build_global_indices(session)
        
        return WorkerResult(
            success=True,
            output={
                "indices_built": True,
                "documents_processed": len(documents),
                "total_spans_indexed": total_spans,
                "index_type": "global"
            }
        )
    
    def _build_document_indices(self, session, doc_id: int) -> WorkerResult:
        """Build indices for a specific document."""
        # Get document spans
        spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
        
        if not spans:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"No spans found for document {doc_id}"
            )
        
        # Build document-specific indices
        self._build_document_indices_internal(session, doc_id, spans)
        
        return WorkerResult(
            success=True,
            output={
                "indices_built": True,
                "document_id": doc_id,
                "spans_indexed": len(spans),
                "index_type": "document"
            }
        )
    
    def _build_global_indices(self, session):
        """Build global indices across all documents."""
        # Get all spans
        spans = session.query(BaseSpan).all()
        
        if not spans:
            return
        
        # Prepare text data
        texts = []
        span_ids = []
        sections = []
        
        for span in spans:
            texts.append(span.text)
            span_ids.append(span.span_id)
            sections.append(span.section)
        
        # Build BM25 index
        self._build_bm25_index(texts, span_ids, sections)
        
        # Build dense index
        self._build_dense_index(texts, span_ids, sections)
        
        # Store span mapping
        self.span_mapping = {span_id: i for i, span_id in enumerate(span_ids)}
    
    def _build_document_indices_internal(self, session, doc_id: int, spans: List[BaseSpan]):
        """Build indices for a specific document."""
        # Prepare text data
        texts = []
        span_ids = []
        sections = []
        
        for span in spans:
            texts.append(span.text)
            span_ids.append(span.span_id)
            sections.append(span.section)
        
        # Build document-specific indices
        self._build_bm25_index(texts, span_ids, sections, doc_id)
        self._build_dense_index(texts, span_ids, sections, doc_id)
        
        # Update span mapping
        for i, span_id in enumerate(span_ids):
            self.span_mapping[span_id] = i
    
    def _build_bm25_index(self, texts: List[str], span_ids: List[int], sections: List[str], doc_id: Optional[int] = None):
        """Build BM25 index using TF-IDF vectorizer."""
        # Preprocess texts
        processed_texts = [self._preprocess_text(text) for text in texts]
        
        # Create TF-IDF vectorizer
        vectorizer = TfidfVectorizer(
            max_features=self.config.max_features,
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            stop_words='english',
            lowercase=self.config.normalize_tokens,
            token_pattern=r'\b\w+\b' if self.config.preserve_numerics else r'\b[a-zA-Z]+\b'
        )
        
        # Fit and transform
        tfidf_matrix = vectorizer.fit_transform(processed_texts)
        
        # Store index components
        self.bm25_index = {
            'vectorizer': vectorizer,
            'matrix': tfidf_matrix,
            'span_ids': span_ids,
            'sections': sections,
            'doc_id': doc_id
        }
        
        # Store feature names for debugging
        self.feature_names = vectorizer.get_feature_names_out().tolist()
    
    def _build_dense_index(self, texts: List[str], span_ids: List[int], sections: List[str], doc_id: Optional[int] = None):
        """Build dense index using sentence transformers."""
        try:
            from sentence_transformers import SentenceTransformer
            
            # Load model
            model = SentenceTransformer(self.config.dense_model_name)
            
            # Generate embeddings
            embeddings = model.encode(texts, show_progress_bar=False)
            
            # Normalize embeddings
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            
            # Build FAISS index
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
            index.add(embeddings.astype('float32'))
            
            # Store index components
            self.dense_index = {
                'model': model,
                'index': index,
                'embeddings': embeddings,
                'span_ids': span_ids,
                'sections': sections,
                'doc_id': doc_id
            }
            
        except ImportError:
            # Fallback to simple TF-IDF if sentence-transformers not available
            self._build_dense_index_fallback(texts, span_ids, sections, doc_id)
    
    def _build_dense_index_fallback(self, texts: List[str], span_ids: List[int], sections: List[str], doc_id: Optional[int] = None):
        """Fallback dense index using TF-IDF and PCA."""
        from sklearn.decomposition import PCA
        
        # Use TF-IDF as base
        vectorizer = TfidfVectorizer(
            max_features=min(self.config.dense_dimension * 2, len(texts)),
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            stop_words='english'
        )
        
        tfidf_matrix = vectorizer.fit_transform(texts)
        
        # Reduce dimensionality with PCA
        pca = PCA(n_components=min(self.config.dense_dimension, tfidf_matrix.shape[1]))
        embeddings = pca.fit_transform(tfidf_matrix.toarray())
        
        # Normalize
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        # Build FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings.astype('float32'))
        
        self.dense_index = {
            'model': None,
            'index': index,
            'embeddings': embeddings,
            'span_ids': span_ids,
            'sections': sections,
            'doc_id': doc_id,
            'vectorizer': vectorizer,
            'pca': pca
        }
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for indexing."""
        # Convert to lowercase if configured
        if self.config.normalize_tokens:
            text = text.lower()
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def search(self, query: str, section: Optional[str] = None, top_k: int = 10, 
               use_bm25: bool = True, use_dense: bool = True) -> List[Dict[str, Any]]:
        """Search spans using both BM25 and dense retrieval."""
        results = []
        
        if use_bm25 and self.bm25_index:
            bm25_results = self._search_bm25(query, section, top_k)
            results.extend(bm25_results)
        
        if use_dense and self.dense_index:
            dense_results = self._search_dense(query, section, top_k)
            results.extend(dense_results)
        
        # Merge and deduplicate results
        merged_results = self._merge_search_results(results, top_k)
        
        return merged_results
    
    def _search_bm25(self, query: str, section: Optional[str], top_k: int) -> List[Dict[str, Any]]:
        """Search using BM25 index."""
        if not self.bm25_index:
            return []
        
        # Preprocess query
        processed_query = self._preprocess_text(query)
        
        # Transform query
        query_vector = self.bm25_index['vectorizer'].transform([processed_query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vector, self.bm25_index['matrix']).flatten()
        
        # Get top results
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0:
                # Filter by section if specified
                if section and self.bm25_index['sections'][idx] != section:
                    continue
                
                results.append({
                    'span_id': self.bm25_index['span_ids'][idx],
                    'score': float(similarities[idx]),
                    'method': 'bm25',
                    'section': self.bm25_index['sections'][idx]
                })
        
        return results
    
    def _search_dense(self, query: str, section: Optional[str], top_k: int) -> List[Dict[str, Any]]:
        """Search using dense index."""
        if not self.dense_index:
            return []
        
        # Encode query
        if self.dense_index['model']:
            query_vector = self.dense_index['model'].encode([query])
        else:
            # Fallback: use TF-IDF + PCA
            query_vector = self.dense_index['vectorizer'].transform([query])
            query_vector = self.dense_index['pca'].transform(query_vector.toarray())
        
        # Normalize query vector
        query_vector = query_vector / np.linalg.norm(query_vector, axis=1, keepdims=True)
        
        # Search FAISS index
        scores, indices = self.dense_index['index'].search(
            query_vector.astype('float32'), top_k
        )
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and score > 0:
                # Filter by section if specified
                if section and self.dense_index['sections'][idx] != section:
                    continue
                
                results.append({
                    'span_id': self.dense_index['span_ids'][idx],
                    'score': float(score),
                    'method': 'dense',
                    'section': self.dense_index['sections'][idx]
                })
        
        return results
    
    def _merge_search_results(self, results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Merge and deduplicate search results."""
        # Group by span_id
        span_scores = {}
        for result in results:
            span_id = result['span_id']
            if span_id not in span_scores:
                span_scores[span_id] = {
                    'span_id': span_id,
                    'section': result['section'],
                    'bm25_score': 0.0,
                    'dense_score': 0.0,
                    'combined_score': 0.0
                }
            
            if result['method'] == 'bm25':
                span_scores[span_id]['bm25_score'] = result['score']
            elif result['method'] == 'dense':
                span_scores[span_id]['dense_score'] = result['score']
        
        # Calculate combined scores
        for span_data in span_scores.values():
            span_data['combined_score'] = (
                span_data['bm25_score'] * 0.5 + 
                span_data['dense_score'] * 0.5
            )
        
        # Sort by combined score and return top_k
        sorted_results = sorted(
            span_scores.values(), 
            key=lambda x: x['combined_score'], 
            reverse=True
        )
        
        return sorted_results[:top_k]
    
    def save_indices(self, filepath: str):
        """Save indices to disk."""
        index_data = {
            'bm25_index': self.bm25_index,
            'dense_index': self.dense_index,
            'span_mapping': self.span_mapping,
            'feature_names': self.feature_names,
            'config': self.config.__dict__,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(index_data, f)
    
    def load_indices(self, filepath: str):
        """Load indices from disk."""
        with open(filepath, 'rb') as f:
            index_data = pickle.load(f)
        
        self.bm25_index = index_data['bm25_index']
        self.dense_index = index_data['dense_index']
        self.span_mapping = index_data['span_mapping']
        self.feature_names = index_data['feature_names']
        
        # Note: config and timestamp are not restored
