# src/ncfd/extract/workers/base_span_ingest.py
"""
BaseSpan Ingest Worker

Generates sentence-level and table-cell spans from document text with stable location anchors.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, Document, DocumentText, DocumentTable
from ...db.session import get_session
from ..sentencizer import get_sentencizer, SentenceSpan


@dataclass
class SpanGenerationConfig:
    """Configuration for span generation."""
    min_sentence_length: int = 12
    max_sentence_length: int = 400
    min_table_cell_length: int = 1  # Reduced from 10 to capture short numeric values
    max_table_cell_length: int = 500  # Increased from 200 to allow longer cells
    preserve_hyphens: bool = False
    normalize_whitespace: bool = True
    include_paragraph_spans: bool = False
    
    # Short-sentence allowlist patterns for critical results
    short_sentence_allowlist: List[str] = None
    
    # Table cell content patterns for post-processing filtering
    table_cell_allowlist: List[str] = None
    
    def __post_init__(self):
        if self.short_sentence_allowlist is None:
            self.short_sentence_allowlist = [
                r'%',  # Percentage values
                r'median',  # Median values
                r'weeks?|months?|years?',  # Time units
                r'n\s*=',  # Sample sizes
                r'\d+\.\d+',  # Decimal numbers
                r'hr\s*[=<>]',  # Hazard ratios
                r'or\s*[=<>]',  # Odds ratios
                r'rr\s*[=<>]',  # Risk ratios
                r'p\s*[=<>]',  # P-values
                r'ci\s*[=<>]',  # Confidence intervals
                r'response',  # Response rates
                r'survival',  # Survival data
                r'progression',  # Progression data
                r'objective',  # Objective response
                r'complete',  # Complete response
                r'partial',  # Partial response
                r'stable',  # Stable disease
                r'progressive',  # Progressive disease
            ]
        
        if self.table_cell_allowlist is None:
            self.table_cell_allowlist = [
                r'^\d+$',  # Pure numbers (e.g., "22", "13.1")
                r'^\d+\.\d+$',  # Decimal numbers
                r'^\d+\.?\d*%$',  # Percentages (e.g., "15.8%", "22%")
                r'^n\s*=\s*\d+$',  # Sample sizes (e.g., "n=22")
                r'^\d+\s*/\s*\d+$',  # Fractions (e.g., "19/22")
                r'^\d+\s*\(\d+%\)$',  # Count with percentage (e.g., "19 (86%)")
                r'^\d+\.\d+\s*(weeks?|months?|years?)$',  # Time values
                r'^(median|mean|median\s+os|median\s+pfs)$',  # Statistical terms
                r'^(orr|cr|pr|sd|pd)$',  # Response abbreviations
                r'^(os|pfs|ttp|dfs)$',  # Endpoint abbreviations
                r'^(hr|or|rr)$',  # Ratio abbreviations
                r'^p\s*[=<>]\s*\d+\.?\d*$',  # P-values
                r'^ci\s*[=<>]\s*\d+\.?\d*$',  # Confidence intervals
                r'^\d+\.?\d*\s*[-–]\s*\d+\.?\d*$',  # Ranges
                r'^(yes|no|na|n/a|not\s+reported)$',  # Categorical values
            ]


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
        """Generate spans from document text."""
        spans = []
        
        # Get document text (fulltext or abstract)
        doc_text = session.query(DocumentText).filter(
            DocumentText.doc_id == document.doc_id
        ).first()
        
        if doc_text:
            # Use fulltext if available, otherwise abstract
            text_content = doc_text.fulltext_text or doc_text.abstract_text
            if text_content:
                # Generate sentence spans
                sentence_spans = self._extract_sentences(
                    text_content, 
                    document.doc_id, 
                    1  # Use page 1 as default since we don't have pages anymore
                )
                spans.extend(sentence_spans)
                
                # Optionally generate paragraph spans
                if self.config.include_paragraph_spans:
                    paragraph_spans = self._extract_paragraphs(
                        text_content,
                        document.doc_id,
                        1  # Use page 1 as default since we don't have pages anymore
                    )
                    spans.extend(paragraph_spans)
        
        return spans
    
    def _extract_sentences(self, text: str, doc_id: int, page_no: int) -> List[BaseSpan]:
        """Extract sentence-level spans from text using advanced sentencizer."""
        spans = []
        
        # Use advanced sentencizer with accurate character offsets
        sentencizer = get_sentencizer()
        sentence_spans = sentencizer.split_sentences(text)
        
        for sentence_span in sentence_spans:
            # Check length constraints with allowlist for short sentences
            sentence_length = len(sentence_span.cleaned_text)
            is_allowed = True
            
            if sentence_length < self.config.min_sentence_length:
                # Check if short sentence should be allowed based on content
                is_allowed = self._is_short_sentence_allowed(sentence_span.cleaned_text)
            
            if is_allowed and sentence_length <= self.config.max_sentence_length:
                # Determine section based on content patterns
                section = self._classify_section(sentence_span.cleaned_text)
                
                span = BaseSpan(
                    doc_id=doc_id,
                    section=section,
                    page=page_no,
                    char_start=sentence_span.start_char,
                    char_end=sentence_span.end_char,
                    text=sentence_span.cleaned_text,
                    is_table_cell=False
                )
                spans.append(span)
        
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
                    text=cleaned_paragraph,  # Cleaned/normalized text
                    text_original=paragraph,  # Original text slice
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
                        # Apply post-processing filter for table cells
                        if self._is_table_cell_allowed(header_text):
                            span = BaseSpan(
                                doc_id=doc_id,
                                section="Table",
                                page=page_no,
                                char_start=0,  # Table cells don't have char positions
                                char_end=len(header_text),
                                text=header_text,  # Cleaned/normalized text
                                text_original=str(header),  # Original cell content
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
                            # Apply post-processing filter for table cells
                            if self._is_table_cell_allowed(cell_text):
                                span = BaseSpan(
                                    doc_id=doc_id,
                                    section="Table",
                                    page=page_no,
                                    char_start=0,
                                    char_end=len(cell_text),
                                    text=cell_text,  # Cleaned/normalized text
                                    text_original=str(cell),  # Original cell content
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
    
    def _is_short_sentence_allowed(self, sentence: str) -> bool:
        """
        Check if a short sentence should be allowed based on allowlist patterns.
        
        Args:
            sentence: The sentence to check
            
        Returns:
            True if sentence matches allowlist patterns, False otherwise
        """
        sentence_lower = sentence.lower()
        
        for pattern in self.config.short_sentence_allowlist:
            if re.search(pattern, sentence_lower, re.IGNORECASE):
                return True
        
        return False
    
    def _is_table_cell_allowed(self, cell_text: str) -> bool:
        """
        Check if a table cell should be allowed based on content patterns.
        
        This method filters table cells to keep only those containing:
        - Numeric values (e.g., "13.1", "22")
        - Sample sizes (e.g., "n=22")
        - Percentages (e.g., "15.8%")
        - Statistical terms (e.g., "median", "ORR")
        - Method keywords (e.g., "Kaplan-Meier", "RECIST")
        
        Args:
            cell_text: The cleaned table cell text to check
            
        Returns:
            True if cell matches allowlist patterns, False otherwise
        """
        cell_text = cell_text.strip()
        
        # Always allow cells that are longer than the old minimum (10 chars)
        # This preserves existing behavior for longer cells
        if len(cell_text) >= 10:
            return True
        
        # For short cells, check against allowlist patterns
        for pattern in self.config.table_cell_allowlist:
            if re.search(pattern, cell_text, re.IGNORECASE):
                return True
        
        return False
    
    def _classify_section(self, text: str) -> str:
        """Classify text into document sections based on content patterns."""
        text_lower = text.lower()
        
        # Check for heading patterns first (ALL CAPS lines)
        if self._is_heading(text):
            heading_text = text.strip().upper()
            if 'ABSTRACT' in heading_text:
                return "Abstract"
            elif 'RESULTS' in heading_text:
                return "Results"
            elif 'METHODS' in heading_text or 'MATERIALS' in heading_text:
                return "Methods"
            elif 'DISCUSSION' in heading_text:
                return "Discussion"
            elif 'CONCLUSION' in heading_text:
                return "Discussion"
            elif 'INTRODUCTION' in heading_text or 'BACKGROUND' in heading_text:
                return "Abstract"
        
        # Methods section patterns (high confidence)
        methods_patterns = [
            'methods', 'materials and methods', 'study design', 'protocol',
            'statistical analysis', 'sample size', 'randomization'
        ]
        if any(pattern in text_lower for pattern in methods_patterns):
            return "Methods"
        
        # Discussion patterns (check before Results to avoid conflicts)
        discussion_patterns = [
            'discussion', 'interpretation', 'clinical implications'
        ]
        if any(pattern in text_lower for pattern in discussion_patterns):
            return "Discussion"
        
        # Results section patterns (high confidence)
        results_patterns = [
            'results', 'outcomes', 'efficacy', 'response rate', 'survival',
            'median', 'progression-free', 'overall survival'
        ]
        if any(pattern in text_lower for pattern in results_patterns):
            return "Results"
        
        # Abstract patterns (high confidence)
        abstract_patterns = [
            'abstract', 'background', 'objective', 'conclusion'
        ]
        if any(pattern in text_lower for pattern in abstract_patterns):
            return "Abstract"
        
        # Default to Unknown if uncertain - better than misclassifying
        return "Unknown"
    
    def _is_heading(self, text: str) -> bool:
        """Detect if text is likely a heading (ALL CAPS, short, etc.)."""
        text = text.strip()
        
        # Exclude common short words that shouldn't be headings
        common_words = {'YES', 'NO', 'OK', 'USA', 'DNA', 'RNA', 'FDA', 'NCI', 'WHO'}
        if text in common_words:
            return False
        
        # Check if text is ALL CAPS (excluding common words)
        if text.isupper() and len(text.split()) <= 5 and len(text) >= 3:
            return True
        
        # Check for common heading patterns (but exclude single words)
        heading_patterns = [
            r'^\d+\.\s*[A-Z]',  # Numbered headings
            r'^[A-Z][A-Z\s]+$',  # Title case with some caps
        ]
        
        for pattern in heading_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def _save_spans(self, session, spans: List[BaseSpan]) -> List[BaseSpan]:
        """Save spans to database."""
        saved_spans = []
        
        for span in spans:
            # Check if span already exists (avoid duplicates)
            q = session.query(BaseSpan).filter(
                BaseSpan.doc_id == span.doc_id,
                BaseSpan.section == span.section,
                BaseSpan.page == span.page,
                BaseSpan.is_table_cell == span.is_table_cell,
            )
            
            if span.is_table_cell:
                q = q.filter(
                    BaseSpan.table_id == span.table_id,
                    BaseSpan.row == span.row,
                    BaseSpan.col == span.col,
                )
            else:
                q = q.filter(
                    BaseSpan.char_start == span.char_start,
                    BaseSpan.char_end == span.char_end,
                )
            
            existing = q.first()
            
            if not existing:
                session.add(span)
                saved_spans.append(span)
        
        session.commit()
        return saved_spans
