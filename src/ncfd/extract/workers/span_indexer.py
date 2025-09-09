"""
Span Indexer Worker

Builds TF-IDF and dense indices over BaseSpans for efficient retrieval and span triage.
Note: BM25 functionality has been moved to bm25_indexer.py using Pyserini.
"""

import json
import pickle
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
    tfidf_max_features: int = 10000
    dense_dimension: int = 768
    dense_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    min_token_length: int = 2
    normalize_tokens: bool = True
    preserve_numerics: bool = True


class SpanIndexer(BaseWorker):
    """Worker for building and maintaining TF-IDF and dense span indices."""
    
    def __init__(self, config: Optional[IndexingConfig] = None):
        super().__init__(name="SpanIndexer", version="1.0.0")
        self.config = config or IndexingConfig()
        self.tfidf_index = None
        self.dense_index = None
        self.span_mapping = {}
        self.feature_names = []
        self._indexed_doc_id = None  # Track which document is currently indexed
        
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
        
        # Track the indexed document ID
        self._indexed_doc_id = doc_id
        
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
        
        # Build TF-IDF index
        self._build_tfidf_index(texts, span_ids, sections)
        
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
        self._build_tfidf_index(texts, span_ids, sections, doc_id)
        self._build_dense_index(texts, span_ids, sections, doc_id)
        
        # Update span mapping
        for i, span_id in enumerate(span_ids):
            self.span_mapping[span_id] = i
    
    def _build_tfidf_index(self, texts: List[str], span_ids: List[int], sections: List[str], doc_id: Optional[int] = None):
        """Build TF-IDF index using sklearn vectorizer."""
        # Preprocess texts
        processed_texts = [self._preprocess_text(text) for text in texts]
        
        # Create TF-IDF vectorizer
        vectorizer = TfidfVectorizer(
            max_features=self.config.tfidf_max_features,
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
        self.tfidf_index = {
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
        """Fallback dense index using TF-IDF and TruncatedSVD (LSA)."""
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import normalize
        
        # 1) Vectorize (keep negations; preserve numerics)
        vectorizer = TfidfVectorizer(
            max_features=self.config.tfidf_max_features,  # Use config, not len(texts)
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            stop_words=None,  # Don't drop 'no', 'not' for negation preservation
            lowercase=self.config.normalize_tokens,
            token_pattern=r'\b\w+\b' if self.config.preserve_numerics else r'\b[a-zA-Z]+\b'
        )
        X = vectorizer.fit_transform(texts)  # sparse (n_spans x vocab)
        
        # 2) Reduce with TruncatedSVD
        # Cap n_components to matrix rank-ish to avoid sklearn warnings/errors
        max_comps = min(self.config.dense_dimension, X.shape[1]-1, X.shape[0]-1)
        n_components = max(2, max_comps)  # At least 2 components
        svd = TruncatedSVD(n_components=n_components, random_state=0)
        Z = svd.fit_transform(X)  # dense (n_spans x n_components)
        
        # 3) L2-normalize → cosine via inner product
        Z = normalize(Z, norm="l2", axis=1)
        
        # 4) FAISS IP index
        index = faiss.IndexFlatIP(Z.shape[1])
        index.add(Z.astype('float32'))
        
        self.dense_index = {
            'model': None,  # Explicit: fallback mode
            'index': index,
            'embeddings': Z,  # Optional; can omit for memory
            'span_ids': span_ids,
            'sections': sections,
            'doc_id': doc_id,
            'vectorizer': vectorizer,
            'svd': svd  # Store SVD instead of PCA
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
               use_tfidf: bool = True, use_dense: bool = True, 
               use_rrf: bool = True, rrf_k: float = 60.0) -> List[Dict[str, Any]]:
        """Search spans using both TF-IDF and dense retrieval with RRF fusion."""
        results = []
        
        if use_tfidf and self.tfidf_index:
            tfidf_results = self._search_tfidf(query, section, top_k)
            results.extend(tfidf_results)
        
        if use_dense and self.dense_index:
            dense_results = self._search_dense(query, section, top_k)
            results.extend(dense_results)
        
        # Merge and deduplicate results using RRF
        merged_results = self._merge_search_results(results, top_k, use_rrf, rrf_k)
        
        return merged_results
    
    def _search_tfidf(self, query: str, section: Optional[str], top_k: int) -> List[Dict[str, Any]]:
        """Search using TF-IDF index."""
        if not self.tfidf_index:
            return []
        
        # Check if we have the matrix (might not be available after loading)
        if 'matrix' not in self.tfidf_index:
            print("Warning: TF-IDF matrix not available, cannot perform search")
            return []
        
        # Preprocess query
        processed_query = self._preprocess_text(query)
        
        # Transform query
        query_vector = self.tfidf_index['vectorizer'].transform([processed_query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vector, self.tfidf_index['matrix']).flatten()
        
        # Get top results
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0:
                # Filter by section if specified
                if section and self.tfidf_index['sections'][idx] != section:
                    continue
                
                results.append({
                    'span_id': self.tfidf_index['span_ids'][idx],
                    'score': float(similarities[idx]),
                    'method': 'tfidf',
                    'section': self.tfidf_index['sections'][idx]
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
            # Fallback: use TF-IDF + TruncatedSVD
            from sklearn.preprocessing import normalize
            qX = self.dense_index['vectorizer'].transform([query])  # sparse 1 x vocab
            qZ = self.dense_index['svd'].transform(qX)  # dense 1 x n_components
            query_vector = normalize(qZ, norm="l2", axis=1)
        
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
    
    def _merge_search_results(self, results: List[Dict[str, Any]], top_k: int, 
                            use_rrf: bool = True, rrf_k: float = 60.0) -> List[Dict[str, Any]]:
        """Merge and deduplicate search results using Reciprocal Rank Fusion (RRF)."""
        if not results:
            return []
        
        # Group by span_id and collect all results
        span_scores = {}
        for result in results:
            span_id = result['span_id']
            if span_id not in span_scores:
                span_scores[span_id] = {
                    'span_id': span_id,
                    'section': result['section'],
                    'tfidf_score': 0.0,
                    'dense_score': 0.0,
                    'combined_score': 0.0,
                    'tfidf_rank': float('inf'),
                    'dense_rank': float('inf')
                }
            
            if result['method'] == 'tfidf':
                span_scores[span_id]['tfidf_score'] = result['score']
            elif result['method'] == 'dense':
                span_scores[span_id]['dense_score'] = result['score']
        
        if use_rrf:
            # Use Reciprocal Rank Fusion (RRF)
            combined_results = self._apply_reciprocal_rank_fusion(results, span_scores, rrf_k)
        else:
            # Fallback to simple averaging (for backward compatibility)
            combined_results = self._apply_simple_averaging(span_scores)
        
        # Sort by combined score and return top_k
        sorted_results = sorted(
            combined_results, 
            key=lambda x: x['combined_score'], 
            reverse=True
        )
        
        return sorted_results[:top_k]
    
    def _apply_reciprocal_rank_fusion(self, results: List[Dict[str, Any]], 
                                     span_scores: Dict[int, Dict[str, Any]], 
                                     rrf_k: float) -> List[Dict[str, Any]]:
        """Apply Reciprocal Rank Fusion (RRF) for robust score combination."""
        # Separate results by method
        tfidf_results = [r for r in results if r['method'] == 'tfidf']
        dense_results = [r for r in results if r['method'] == 'dense']
        
        # Create rank mappings for each method
        tfidf_ranks = {}
        dense_ranks = {}
        
        # Assign ranks for TF-IDF results
        for rank, result in enumerate(tfidf_results, 1):
            tfidf_ranks[result['span_id']] = rank
        
        # Assign ranks for dense results
        for rank, result in enumerate(dense_results, 1):
            dense_ranks[result['span_id']] = rank
        
        # Calculate RRF scores
        combined_results = []
        for span_id, span_data in span_scores.items():
            # Get ranks (use infinity if not found in that method)
            tfidf_rank = tfidf_ranks.get(span_id, float('inf'))
            dense_rank = dense_ranks.get(span_id, float('inf'))
            
            # Calculate RRF score: 1/(k + rank)
            rrf_score = 0.0
            if tfidf_rank != float('inf'):
                rrf_score += 1.0 / (rrf_k + tfidf_rank)
            if dense_rank != float('inf'):
                rrf_score += 1.0 / (rrf_k + dense_rank)
            
            # Create combined result
            combined_result = {
                'span_id': span_id,
                'section': span_data['section'],
                'tfidf_score': span_data['tfidf_score'],
                'dense_score': span_data['dense_score'],
                'combined_score': rrf_score,
                'tfidf_rank': tfidf_rank if tfidf_rank != float('inf') else None,
                'dense_rank': dense_rank if dense_rank != float('inf') else None,
                'fusion_method': 'rrf'
            }
            
            combined_results.append(combined_result)
        
        return combined_results
    
    def _apply_simple_averaging(self, span_scores: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply simple averaging for backward compatibility."""
        combined_results = []
        for span_id, span_data in span_scores.items():
            # Calculate simple average
            combined_score = (
                span_data['tfidf_score'] * 0.5 + 
                span_data['dense_score'] * 0.5
            )
            
            combined_result = {
                'span_id': span_id,
                'section': span_data['section'],
                'tfidf_score': span_data['tfidf_score'],
                'dense_score': span_data['dense_score'],
                'combined_score': combined_score,
                'tfidf_rank': None,
                'dense_rank': None,
                'fusion_method': 'simple_average'
            }
            
            combined_results.append(combined_result)
        
        return combined_results
    
    def save_indices(self, filepath: str):
        """Save indices to disk with safe serialization."""
        # Create base directory
        base_path = Path(filepath).parent
        base_path.mkdir(parents=True, exist_ok=True)
        
        # Create manifest for safe serialization
        manifest = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'config': self.config.__dict__,
            'span_mapping': self.span_mapping,
            'feature_names': self.feature_names
        }
        
        # Save TF-IDF components safely
        if self.tfidf_index:
            tfidf_manifest = self._save_tfidf_safely(filepath)
            manifest['tfidf'] = tfidf_manifest
        
        # Save dense index components safely
        if self.dense_index:
            dense_manifest = self._save_dense_safely(filepath)
            manifest['dense'] = dense_manifest
        
        # Save manifest
        with open(filepath, 'wb') as f:
            pickle.dump(manifest, f)
    
    def load_indices(self, filepath: str):
        """Load indices from disk using manifest-based deserialization."""
        with open(filepath, 'rb') as f:
            manifest = pickle.load(f)
        
        # Load basic components
        self.span_mapping = manifest['span_mapping']
        self.feature_names = manifest['feature_names']
        
        # Load TF-IDF index if present
        if 'tfidf' in manifest:
            self.tfidf_index = self._load_tfidf_safely(manifest['tfidf'])
        
        # Load dense index if present
        if 'dense' in manifest:
            self.dense_index = self._load_dense_safely(manifest['dense'])
        
        # Note: config and timestamp are not restored
    
    def _save_tfidf_safely(self, base_filepath: str) -> Dict[str, Any]:
        """Save TF-IDF components safely (vocabulary + IDF + shape, not whole vectorizer)."""
        if not self.tfidf_index:
            return None
        
        vectorizer = self.tfidf_index['vectorizer']
        matrix = self.tfidf_index['matrix']
        
        # Extract safe components
        tfidf_data = {
            'vocabulary': vectorizer.vocabulary_,
            'idf': vectorizer.idf_,
            'matrix_shape': matrix.shape,
            'span_ids': self.tfidf_index['span_ids'],
            'sections': self.tfidf_index['sections'],
            'doc_id': self.tfidf_index.get('doc_id'),
            'vectorizer_params': {
                'max_features': vectorizer.max_features,
                'min_df': vectorizer.min_df,
                'max_df': vectorizer.max_df,
                'ngram_range': vectorizer.ngram_range,
                'stop_words': vectorizer.stop_words,
                'lowercase': vectorizer.lowercase,
                'token_pattern': vectorizer.token_pattern
            }
        }
        
        # Save TF-IDF data
        tfidf_path = base_filepath.replace('.pkl', '_tfidf.pkl')
        with open(tfidf_path, 'wb') as f:
            pickle.dump(tfidf_data, f)
        
        return {
            'path': tfidf_path,
            'type': 'tfidf',
            'shape': matrix.shape,
            'span_count': len(self.tfidf_index['span_ids'])
        }
    
    def _save_dense_safely(self, base_filepath: str) -> Dict[str, Any]:
        """Save dense index components safely."""
        if not self.dense_index:
            return None
        
        dense_manifest = {
            'span_ids': self.dense_index['span_ids'],
            'sections': self.dense_index['sections'],
            'doc_id': self.dense_index.get('doc_id'),
            'type': 'dense'
        }
        
        # Handle SentenceTransformer model
        if self.dense_index['model'] is not None:
            # Save model name, not the model instance
            dense_manifest['model_name'] = self.dense_index['model'].get_model_name()
            dense_manifest['model_type'] = 'sentence_transformer'
            
            # Save embeddings for reconstruction
            embeddings_path = base_filepath.replace('.pkl', '_embeddings.npy')
            np.save(embeddings_path, self.dense_index['embeddings'])
            dense_manifest['embeddings_path'] = embeddings_path
            dense_manifest['embeddings_shape'] = self.dense_index['embeddings'].shape
        
        # Handle fallback TF-IDF + SVD
        elif 'vectorizer' in self.dense_index:
            dense_manifest['model_type'] = 'tfidf_svd_fallback'
            
            # Save vectorizer components
            vectorizer = self.dense_index['vectorizer']
            svd = self.dense_index['svd']
            
            svd_data = {
                'vectorizer_vocabulary': vectorizer.vocabulary_,
                'vectorizer_idf': vectorizer.idf_,
                'vectorizer_params': {
                    'max_features': vectorizer.max_features,
                    'min_df': vectorizer.min_df,
                    'max_df': vectorizer.max_df,
                    'ngram_range': vectorizer.ngram_range,
                    'stop_words': vectorizer.stop_words,
                    'lowercase': vectorizer.lowercase,
                    'token_pattern': vectorizer.token_pattern
                },
                'svd_components': svd.components_,
                'svd_explained_variance': svd.explained_variance_,
                'svd_explained_variance_ratio': svd.explained_variance_ratio_,
                'svd_n_components': svd.n_components_,
                'svd_random_state': svd.random_state
            }
            
            svd_path = base_filepath.replace('.pkl', '_svd.pkl')
            with open(svd_path, 'wb') as f:
                pickle.dump(svd_data, f)
            
            dense_manifest['svd_path'] = svd_path
        
        # Save FAISS index separately
        if 'index' in self.dense_index:
            faiss_path = base_filepath.replace('.pkl', '_faiss.index')
            faiss.write_index(self.dense_index['index'], faiss_path)
            dense_manifest['faiss_path'] = faiss_path
        
        return dense_manifest
    
    def _load_tfidf_safely(self, tfidf_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Load TF-IDF components safely."""
        tfidf_path = tfidf_manifest['path']
        
        if not Path(tfidf_path).exists():
            print(f"Warning: TF-IDF file not found: {tfidf_path}")
            return None
        
        with open(tfidf_path, 'rb') as f:
            tfidf_data = pickle.load(f)
        
        # Reconstruct vectorizer from saved components
        vectorizer = TfidfVectorizer()
        vectorizer.vocabulary_ = tfidf_data['vocabulary']
        vectorizer.idf_ = tfidf_data['idf']
        vectorizer.max_features = tfidf_data['vectorizer_params']['max_features']
        vectorizer.min_df = tfidf_data['vectorizer_params']['min_df']
        vectorizer.max_df = tfidf_data['vectorizer_params']['max_df']
        vectorizer.ngram_range = tfidf_data['vectorizer_params']['ngram_range']
        vectorizer.stop_words = tfidf_data['vectorizer_params']['stop_words']
        vectorizer.lowercase = tfidf_data['vectorizer_params']['lowercase']
        vectorizer.token_pattern = tfidf_data['vectorizer_params']['token_pattern']
        
        # Reconstruct matrix (we'll need to rebuild this from original texts)
        # For now, create a placeholder - in practice, you'd need to store the original texts
        # or rebuild the matrix from the vocabulary and IDF
        matrix_shape = tfidf_data['matrix_shape']
        
        return {
            'vectorizer': vectorizer,
            'matrix_shape': matrix_shape,  # Placeholder - would need original texts to rebuild
            'span_ids': tfidf_data['span_ids'],
            'sections': tfidf_data['sections'],
            'doc_id': tfidf_data.get('doc_id')
        }
    
    def _load_dense_safely(self, dense_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Load dense index components safely."""
        dense_index = {
            'span_ids': dense_manifest['span_ids'],
            'sections': dense_manifest['sections'],
            'doc_id': dense_manifest.get('doc_id'),
            'type': dense_manifest['type']
        }
        
        # Load FAISS index if present
        if 'faiss_path' in dense_manifest:
            faiss_path = dense_manifest['faiss_path']
            if Path(faiss_path).exists():
                dense_index['index'] = faiss.read_index(faiss_path)
            else:
                print(f"Warning: FAISS index file not found: {faiss_path}")
        
        # Handle SentenceTransformer model
        if dense_manifest.get('model_type') == 'sentence_transformer':
            try:
                from sentence_transformers import SentenceTransformer
                model_name = dense_manifest['model_name']
                dense_index['model'] = SentenceTransformer(model_name)
                
                # Load embeddings if present
                if 'embeddings_path' in dense_manifest:
                    embeddings_path = dense_manifest['embeddings_path']
                    if Path(embeddings_path).exists():
                        dense_index['embeddings'] = np.load(embeddings_path)
                    else:
                        print(f"Warning: Embeddings file not found: {embeddings_path}")
                
            except ImportError:
                print("Warning: sentence-transformers not available, cannot load model")
                dense_index['model'] = None
        
        # Handle fallback TF-IDF + SVD
        elif dense_manifest.get('model_type') == 'tfidf_svd_fallback':
            if 'svd_path' in dense_manifest:
                svd_path = dense_manifest['svd_path']
                if Path(svd_path).exists():
                    with open(svd_path, 'rb') as f:
                        svd_data = pickle.load(f)
                    
                    # Reconstruct vectorizer
                    vectorizer = TfidfVectorizer()
                    vectorizer.vocabulary_ = svd_data['vectorizer_vocabulary']
                    vectorizer.idf_ = svd_data['vectorizer_idf']
                    vectorizer.max_features = svd_data['vectorizer_params']['max_features']
                    vectorizer.min_df = svd_data['vectorizer_params']['min_df']
                    vectorizer.max_df = svd_data['vectorizer_params']['max_df']
                    vectorizer.ngram_range = svd_data['vectorizer_params']['ngram_range']
                    vectorizer.stop_words = svd_data['vectorizer_params']['stop_words']
                    vectorizer.lowercase = svd_data['vectorizer_params']['lowercase']
                    vectorizer.token_pattern = svd_data['vectorizer_params']['token_pattern']
                    
                    # Reconstruct SVD
                    from sklearn.decomposition import TruncatedSVD
                    svd = TruncatedSVD(n_components=svd_data['svd_n_components'], 
                                      random_state=svd_data['svd_random_state'])
                    svd.components_ = svd_data['svd_components']
                    svd.explained_variance_ = svd_data['svd_explained_variance']
                    svd.explained_variance_ratio_ = svd_data['svd_explained_variance_ratio']
                    
                    dense_index['vectorizer'] = vectorizer
                    dense_index['svd'] = svd
                else:
                    print(f"Warning: SVD file not found: {svd_path}")
        
        return dense_index
