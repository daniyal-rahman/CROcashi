"""
Abstract span indexer for creating base_spans from document text.

This module provides functionality to index abstracts and full text into
sentence-level base_spans for downstream processing.
"""

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ...db.models import Document, DocumentText, Span as DBSpan
from ...db.session import session_scope

logger = logging.getLogger(__name__)


class AbstractSpanIndexer:
    """Indexes document abstracts into sentence-level base_spans."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the span indexer.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Sentence splitting configuration
        self.min_sentence_length = self.config.get('min_sentence_length', 10)
        self.max_sentence_length = self.config.get('max_sentence_length', 2000)
        self.sentence_endings = self.config.get('sentence_endings', r'[.!?]+')
        
        # Span creation configuration
        self.section_name = self.config.get('section_name', 'Abstract')
        self.enable_table_detection = self.config.get('enable_table_detection', False)
        
        logger.info(f"AbstractSpanIndexer initialized with min_length={self.min_sentence_length}, "
                   f"max_length={self.max_sentence_length}")
    
    def index_document_abstract(self, doc_id: int, force_reindex: bool = False) -> Dict[str, Any]:
        """
        Index abstract text for a document into base_spans.
        
        Args:
            doc_id: Document ID to index
            force_reindex: Whether to reindex even if spans already exist
            
        Returns:
            Dictionary with indexing results
        """
        result = {
            'doc_id': doc_id,
            'success': False,
            'spans_created': 0,
            'spans_skipped': 0,
            'error_message': None,
            'abstract_length': 0
        }
        
        try:
            with session_scope() as session:
                # Check if document exists
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    result['error_message'] = f"Document {doc_id} not found"
                    return result
                
                # Check if abstract text exists
                doc_text = session.query(DocumentText).filter(DocumentText.doc_id == doc_id).first()
                if not doc_text or not doc_text.abstract_text:
                    result['error_message'] = f"No abstract text found for document {doc_id}"
                    return result
                
                abstract_text = doc_text.abstract_text.strip()
                result['abstract_length'] = len(abstract_text)
                
                if not abstract_text:
                    result['error_message'] = f"Empty abstract text for document {doc_id}"
                    return result
                
                # Check if spans already exist
                existing_spans = session.query(Span).filter(
                    Span.doc_id == doc_id,
                    Span.section == self.section_name
                ).count()
                
                if existing_spans > 0 and not force_reindex:
                    result['spans_skipped'] = existing_spans
                    result['success'] = True
                    logger.info(f"Document {doc_id} already has {existing_spans} abstract spans, skipping")
                    return result
                
                # Clear existing spans if force reindex
                if force_reindex and existing_spans > 0:
                    session.query(Span).filter(
                        Span.doc_id == doc_id,
                        Span.section == self.section_name
                    ).delete()
                    logger.info(f"Cleared {existing_spans} existing spans for document {doc_id}")
                
                # Split abstract into sentences
                sentences = self._split_into_sentences(abstract_text)
                
                # Create base spans
                spans_created = 0
                char_offset = 0
                
                for i, sentence in enumerate(sentences):
                    if not sentence.strip():
                        continue
                    
                    # Calculate character positions
                    char_start = abstract_text.find(sentence, char_offset)
                    if char_start == -1:
                        char_start = char_offset
                    char_end = char_start + len(sentence)
                    
                    # Create span using current schema
                    db_span = DBSpan(
                        doc_id=doc_id,
                        quote=sentence.strip(),  # Use 'quote' field instead of 'text'
                        section=self.section_name,
                        page=None,  # Abstracts don't have page numbers
                        char_start=char_start,
                        char_end=char_end,
                        confidence=1.0,  # Default confidence for abstract spans
                        created_at=datetime.now(timezone.utc)
                    )
                    
                    session.add(db_span)
                    spans_created += 1
                    char_offset = char_end
                
                # Commit the transaction
                session.commit()
                
                result['success'] = True
                result['spans_created'] = spans_created
                
                logger.info(f"Successfully indexed document {doc_id}: {spans_created} spans created "
                           f"from {len(abstract_text)} character abstract")
                
                return result
                
        except IntegrityError as e:
            logger.error(f"Integrity error indexing document {doc_id}: {e}")
            result['error_message'] = f"Database integrity error: {str(e)}"
            return result
        except Exception as e:
            logger.error(f"Error indexing document {doc_id}: {e}")
            result['error_message'] = f"Unexpected error: {str(e)}"
            return result
    
    def index_multiple_documents(self, doc_ids: List[int], force_reindex: bool = False) -> Dict[str, Any]:
        """
        Index abstracts for multiple documents.
        
        Args:
            doc_ids: List of document IDs to index
            force_reindex: Whether to reindex even if spans already exist
            
        Returns:
            Dictionary with batch indexing results
        """
        results = {
            'total_documents': len(doc_ids),
            'successful': 0,
            'failed': 0,
            'total_spans_created': 0,
            'total_spans_skipped': 0,
            'errors': []
        }
        
        for doc_id in doc_ids:
            result = self.index_document_abstract(doc_id, force_reindex)
            
            if result['success']:
                results['successful'] += 1
                results['total_spans_created'] += result['spans_created']
                results['total_spans_skipped'] += result['spans_skipped']
            else:
                results['failed'] += 1
                results['errors'].append({
                    'doc_id': doc_id,
                    'error': result['error_message']
                })
        
        logger.info(f"Batch indexing completed: {results['successful']}/{results['total_documents']} successful, "
                   f"{results['total_spans_created']} spans created, {results['total_spans_skipped']} skipped")
        
        return results
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using simple heuristics.
        
        Args:
            text: Text to split
            
        Returns:
            List of sentences
        """
        if not text:
            return []
        
        # Clean up the text
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Split on sentence endings, but be careful about abbreviations
        # This is a simple approach - could be enhanced with NLP libraries
        sentences = re.split(f'({self.sentence_endings})\s+', text)
        
        # Recombine sentences with their punctuation
        result = []
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                sentence = sentences[i] + sentences[i + 1]
            else:
                sentence = sentences[i]
            
            sentence = sentence.strip()
            
            # Filter by length
            if self.min_sentence_length <= len(sentence) <= self.max_sentence_length:
                result.append(sentence)
            elif len(sentence) > self.max_sentence_length:
                # Split long sentences further
                sub_sentences = self._split_long_sentence(sentence)
                result.extend(sub_sentences)
        
        return result
    
    def _split_long_sentence(self, sentence: str) -> List[str]:
        """
        Split a sentence that's too long into smaller parts.
        
        Args:
            sentence: Long sentence to split
            
        Returns:
            List of shorter sentence parts
        """
        # Split on common delimiters
        parts = re.split(r'[,;]\s+', sentence)
        
        result = []
        for part in parts:
            part = part.strip()
            if self.min_sentence_length <= len(part) <= self.max_sentence_length:
                result.append(part)
            elif len(part) > self.max_sentence_length:
                # Further split if still too long
                sub_parts = re.split(r'\s+', part)
                current_part = ""
                
                for sub_part in sub_parts:
                    if len(current_part + " " + sub_part) <= self.max_sentence_length:
                        current_part += (" " + sub_part) if current_part else sub_part
                    else:
                        if current_part and len(current_part) >= self.min_sentence_length:
                            result.append(current_part)
                        current_part = sub_part
                
                if current_part and len(current_part) >= self.min_sentence_length:
                    result.append(current_part)
        
        return result
    
    def get_document_stats(self, doc_id: int) -> Dict[str, Any]:
        """
        Get statistics about spans for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Dictionary with document span statistics
        """
        stats = {
            'doc_id': doc_id,
            'has_abstract': False,
            'abstract_length': 0,
            'span_count': 0,
            'sections': []
        }
        
        try:
            with session_scope() as session:
                # Check abstract
                doc_text = session.query(DocumentText).filter(DocumentText.doc_id == doc_id).first()
                if doc_text and doc_text.abstract_text:
                    stats['has_abstract'] = True
                    stats['abstract_length'] = len(doc_text.abstract_text)
                
                # Count spans by section
                spans = session.query(Span).filter(Span.doc_id == doc_id).all()
                stats['span_count'] = len(spans)
                
                sections = {}
                for span in spans:
                    section = span.section
                    if section not in sections:
                        sections[section] = 0
                    sections[section] += 1
                
                stats['sections'] = sections
                
        except Exception as e:
            logger.error(f"Error getting stats for document {doc_id}: {e}")
            stats['error'] = str(e)
        
        return stats
