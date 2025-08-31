"""
BaseSpan Ingest Worker

Generates sentence-level and table-cell spans from document text with stable location anchors.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, Document, DocumentTextPage, DocumentTable
from ...db.session import get_session


@dataclass
class SpanGenerationConfig:
    """Configuration for span generation."""
    min_sentence_length: int = 50
    max_sentence_length: int = 400
    min_table_cell_length: int = 10
    max_table_cell_length: int = 200
    preserve_hyphens: bool = False
    normalize_whitespace: bool = True
    include_paragraph_spans: bool = False


class BaseSpanIngestWorker(BaseWorker):
    """Worker for ingesting BaseSpans from document text and tables."""
    
    def __init__(self, config: Optional[SpanGenerationConfig] = None):
        super().__init__(name="BaseSpanIngestWorker", version="1.0.0")
        self.config = config or SpanGenerationConfig()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process document and generate BaseSpans."""
        doc_id = inputs.get("doc_id")
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        try:
            with get_session() as session:
                # Get document
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message=f"Document {doc_id} not found"
                    )
                
                # Generate spans from text pages
                text_spans = self._generate_text_spans(session, document)
                
                # Generate spans from tables
                table_spans = self._generate_table_spans(session, document)
                
                # Combine all spans
                all_spans = text_spans + table_spans
                
                # Save to database
                saved_spans = self._save_spans(session, all_spans)
                
                return WorkerResult(
                    success=True,
                    output={
                        "spans_generated": len(all_spans),
                        "text_spans": len(text_spans),
                        "table_spans": len(table_spans),
                        "spans": saved_spans
                    },
                    metadata={
                        "doc_id": doc_id,
                        "config": self.config.__dict__
                    }
                )
                
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error processing document {doc_id}: {str(e)}"
            )
    
    def _generate_text_spans(self, session, document: Document) -> List[BaseSpan]:
        """Generate spans from document text pages."""
        spans = []
        
        # Get text pages
        text_pages = session.query(DocumentTextPage).filter(
            DocumentTextPage.doc_id == document.doc_id
        ).order_by(DocumentTextPage.page_no).all()
        
        for page in text_pages:
            # Generate sentence spans
            sentence_spans = self._extract_sentences(
                page.text, 
                document.doc_id, 
                page.page_no
            )
            spans.extend(sentence_spans)
            
            # Optionally generate paragraph spans
            if self.config.include_paragraph_spans:
                paragraph_spans = self._extract_paragraphs(
                    page.text,
                    document.doc_id,
                    page.page_no
                )
                spans.extend(paragraph_spans)
        
        return spans
    
    def _extract_sentences(self, text: str, doc_id: int, page_no: int) -> List[BaseSpan]:
        """Extract sentence-level spans from text."""
        spans = []
        
        # Use biomedical sentence splitter pattern
        # Split on sentence endings followed by whitespace and capital letter
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, text)
        
        current_pos = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                current_pos += len(sentence) + 1  # +1 for the split character
                continue
            
            # Clean and normalize sentence
            cleaned_sentence = self._clean_text(sentence)
            
            # Check length constraints
            if (self.config.min_sentence_length <= len(cleaned_sentence) <= 
                self.config.max_sentence_length):
                
                # Find the actual position in original text
                start_pos = text.find(sentence, current_pos)
                if start_pos != -1:
                    end_pos = start_pos + len(sentence)
                    
                    # Determine section based on content patterns
                    section = self._classify_section(cleaned_sentence)
                    
                    span = BaseSpan(
                        doc_id=doc_id,
                        section=section,
                        page=page_no,
                        char_start=start_pos,
                        char_end=end_pos,
                        text=cleaned_sentence,
                        is_table_cell=False
                    )
                    spans.append(span)
                    
                    current_pos = end_pos
                else:
                    current_pos += len(sentence) + 1
            else:
                current_pos += len(sentence) + 1
        
        return spans
    
    def _extract_paragraphs(self, text: str, doc_id: int, page_no: int) -> List[BaseSpan]:
        """Extract paragraph-level spans from text."""
        spans = []
        
        # Split on double newlines or significant whitespace
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_pos = 0
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph or len(paragraph) < 100:  # Skip very short paragraphs
                current_pos += len(paragraph) + 2  # +2 for \n\n
                continue
            
            # Clean paragraph
            cleaned_paragraph = self._clean_text(paragraph)
            
            # Find position in original text
            start_pos = text.find(paragraph, current_pos)
            if start_pos != -1:
                end_pos = start_pos + len(paragraph)
                
                section = self._classify_section(cleaned_paragraph)
                
                span = BaseSpan(
                    doc_id=doc_id,
                    section=section,
                    page=page_no,
                    char_start=start_pos,
                    char_end=end_pos,
                    text=cleaned_paragraph,
                    is_table_cell=False
                )
                spans.append(span)
                
                current_pos = end_pos
            else:
                current_pos += len(paragraph) + 2
        
        return spans
    
    def _generate_table_spans(self, session, document: Document) -> List[BaseSpan]:
        """Generate spans from document tables."""
        spans = []
        
        # Get tables
        tables = session.query(DocumentTable).filter(
            DocumentTable.doc_id == document.doc_id
        ).order_by(DocumentTable.table_idx).all()
        
        for table in tables:
            if table.table_jsonb:
                table_spans = self._extract_table_cells(
                    table.table_jsonb,
                    document.doc_id,
                    table.page_no,
                    table.table_idx
                )
                spans.extend(table_spans)
        
        return spans
    
    def _extract_table_cells(self, table_data: Dict, doc_id: int, page_no: int, table_idx: int) -> List[BaseSpan]:
        """Extract cell-level spans from table data."""
        spans = []
        
        # Handle different table formats
        if isinstance(table_data, dict):
            # Extract rows and cells
            rows = table_data.get('rows', [])
            headers = table_data.get('headers', [])
            
            # Process headers
            for col_idx, header in enumerate(headers):
                if header and len(str(header)) >= self.config.min_table_cell_length:
                    header_text = self._clean_text(str(header))
                    if len(header_text) <= self.config.max_table_cell_length:
                        span = BaseSpan(
                            doc_id=doc_id,
                            section="Table",
                            page=page_no,
                            char_start=0,  # Table cells don't have char positions
                            char_end=len(header_text),
                            text=header_text,
                            is_table_cell=True,
                            table_id=table_idx,
                            row=0,  # Headers are row 0
                            col=col_idx
                        )
                        spans.append(span)
            
            # Process data rows
            for row_idx, row in enumerate(rows):
                for col_idx, cell in enumerate(row):
                    if cell and len(str(cell)) >= self.config.min_table_cell_length:
                        cell_text = self._clean_text(str(cell))
                        if len(cell_text) <= self.config.max_table_cell_length:
                            span = BaseSpan(
                                doc_id=doc_id,
                                section="Table",
                                page=page_no,
                                char_start=0,
                                char_end=len(cell_text),
                                text=cell_text,
                                is_table_cell=True,
                                table_id=table_idx,
                                row=row_idx + 1,  # +1 because headers are row 0
                                col=col_idx
                            )
                            spans.append(span)
        
        return spans
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not self.config.preserve_hyphens:
            # Remove hyphens at line breaks
            text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        
        if self.config.normalize_whitespace:
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
        
        return text
    
    def _classify_section(self, text: str) -> str:
        """Classify text into document sections based on content patterns."""
        text_lower = text.lower()
        
        # Methods section patterns
        if any(pattern in text_lower for pattern in [
            'methods', 'materials and methods', 'study design', 'protocol',
            'statistical analysis', 'sample size', 'randomization'
        ]):
            return "Methods"
        
        # Results section patterns
        if any(pattern in text_lower for pattern in [
            'results', 'outcomes', 'efficacy', 'response rate', 'survival',
            'median', 'progression-free', 'overall survival'
        ]):
            return "Results"
        
        # Abstract patterns
        if any(pattern in text_lower for pattern in [
            'abstract', 'background', 'objective', 'conclusion'
        ]):
            return "Abstract"
        
        # Discussion patterns
        if any(pattern in text_lower for pattern in [
            'discussion', 'interpretation', 'clinical implications'
        ]):
            return "Discussion"
        
        # Default to Methods if uncertain
        return "Methods"
    
    def _save_spans(self, session, spans: List[BaseSpan]) -> List[BaseSpan]:
        """Save spans to database."""
        saved_spans = []
        
        for span in spans:
            # Check if span already exists (avoid duplicates)
            existing = session.query(BaseSpan).filter(
                BaseSpan.doc_id == span.doc_id,
                BaseSpan.section == span.section,
                BaseSpan.page == span.page,
                BaseSpan.char_start == span.char_start,
                BaseSpan.char_end == span.char_end
            ).first()
            
            if not existing:
                session.add(span)
                saved_spans.append(span)
        
        session.commit()
        return saved_spans
