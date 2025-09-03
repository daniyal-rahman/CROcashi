"""
LLM Results Drafter Worker

Implements Phase A of the LLM-first, provenance-second architecture.
Reads raw paper text and produces draft results with verbatim quotes.
Does NOT attach spans - that's handled by the Provenance Backtracer.
"""

import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict
import logging

from ..base_worker import BaseWorker, WorkerResult
from ...models.llm_extraction_draft import LLMResultsDraft, EvidenceKind, EvidenceStatus
from ....utils.study_card_utils import (
    extract_numeric_value, 
    extract_confidence_interval,
    extract_p_value,
    normalize_units,
    normalize_endpoint_name
)


class LLMResultsDrafter(BaseWorker):
    """
    Worker for drafting results from raw paper text using LLM.
    
    Implements Phase A of the LLM-first, provenance-second architecture:
    - Reads raw paper text (not pre-triaged spans)
    - Extracts results with verbatim quotes
    - Does NOT attach spans (handled by Provenance Backtracer)
    
    Outputs draft results that will be processed by Provenance Backtracer.
    """
    
    def __init__(self, max_text_chunks: int = 20):
        super().__init__("LLMResultsDrafter", "1.0.0")
        self.max_text_chunks = max_text_chunks
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.logger.addHandler(h)
        self.logger.setLevel(logging.INFO)
        
        # Section patterns for text chunking
        self.section_patterns = {
            'results': r'\b(?:results?|outcomes?|efficacy|effectiveness)\b',
            'abstract': r'\b(?:abstract|summary|conclusion)\b',
            'methods': r'\b(?:methods?|materials|protocol|design)\b',
            'tables': r'\b(?:table|figure|supplementary)\b'
        }
        
        # Metric patterns for fallback extraction
        self.metric_patterns = {
            'median_os': r'(median\s+overall\s+survival|median\s+OS|OS\s+median|overall\s+survival\s+median|overall\s+survival|OS)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'median_ttp': r'(median\s+time\s+to\s+progression|median\s+TTP|TTP\s+median|time\s+to\s+progression|TTP)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'median_pfs': r'(median\s+progression\s*-\s*free\s+survival|median\s+PFS|PFS\s+median|progression\s*-\s*free\s+survival|PFS)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'orr_recist': r'(overall\s+response\s+rate|ORR|response\s+rate|objective\s+response\s+rate)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*%',
            'ca125_response': r'(CA-125\s+response|CA125\s+response|CA\s*-\s*125\s+response).*?([0-9.]+)\s*%',
            'grade3_ae_rate': r'(grade\s*3\+?\s*adverse\s+events?|grade\s*3\+?\s*AE)\s+(?:occurred\s+in|reported\s+in|was|were)\s*([0-9.]+)\s*%',
            'serious_ae_rate': r'(serious\s+adverse\s+events?|serious\s+AE)\s+(?:occurred\s+in|reported\s+in|was|were)\s*([0-9.]+)\s*%',
            'os_fixed_time': r'(overall\s+survival|OS)\s+at\s+(\d+)\s*(weeks?|months?)\s+(?:was|showed|revealed)?\s*([0-9.]+)\s*%',
            'pfs_fixed_time': r'(progression\s*-\s*free\s+survival|PFS)\s+at\s+(\d+)\s*(weeks?|months?)\s+(?:was|showed|revealed)?\s*([0-9.]+)\s*%',
            'hr': r'(hazard\s+ratio|HR)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)'
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required fields."""
        required_keys = ['raw_doc_text', 'doc_id']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['raw_doc_text'], str):
            return False
            
        if not isinstance(inputs['doc_id'], str):
            return False
            
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process raw document text to draft results with verbatim quotes.
        
        Args:
            inputs: Dict containing:
                - raw_doc_text: str - Raw document text
                - doc_id: str - Document identifier
                - trial_context: Dict - Trial context information (optional)
                
        Returns:
            WorkerResult containing LLMResultsDraft with verbatim quotes
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required raw_doc_text or doc_id",
                    output={}
                )
            
            raw_doc_text = inputs['raw_doc_text']
            doc_id = inputs['doc_id']
            trial_context = inputs.get('trial_context', {})
            
            start_time = time.time()
            self.logger.info(f"Processing LLM results draft for doc_id: {doc_id}")
            
            # Create LLM results draft
            results_draft = LLMResultsDraft(doc_id=doc_id)
            
            # Extract results using LLM prompts with verbatim quotes
            llm_results = self._extract_results_with_llm(raw_doc_text, trial_context)
            
            # Add results to draft
            for result in llm_results:
                results_draft.add_result(
                    metric=result.get('metric', ''),
                    value=result.get('value'),
                    units=result.get('units'),
                    summary_statistic=result.get('summary_statistic'),
                    verbatim_quote=result.get('verbatim_quote', ''),
                    evidence_kind=result.get('evidence_kind', EvidenceKind.TEXT),
                    section_hint=result.get('section_hint', ''),
                    table_hint=result.get('table_hint'),
                    page_hint=result.get('page_hint'),
                    confidence_llm=result.get('confidence_llm', 0.8)
                )
            
            self.logger.info(f"Drafted {len(results_draft.results)} results with verbatim quotes")
            
            return WorkerResult(
                success=True,
                output={'results_draft': results_draft},
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"LLM results drafting failed: {str(e)}")
            return WorkerResult(
                success=False,
                error_message=f"LLM results drafting failed: {str(e)}",
                output={}
            )

    def _extract_results_with_llm(self, raw_doc_text: str, trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use LLM to extract results with verbatim quotes from raw document text.
        
        This is the core LLM extraction logic that reads the full paper.
        """
        results = []
        
        # For now, implement a hybrid approach that uses both LLM and regex
        # In a full implementation, this would call an LLM API with prompts
        
        # Split text into chunks for processing
        text_chunks = self._chunk_text_by_sections(raw_doc_text)
        
        for chunk_text, section_info in text_chunks:
            # Extract results from this chunk
            chunk_results = self._extract_from_chunk(chunk_text, section_info, trial_context)
            results.extend(chunk_results)
        
        # Deduplicate results by metric and value
        deduplicated_results = self._deduplicate_results(results)
        
        return deduplicated_results

    def _chunk_text_by_sections(self, raw_doc_text: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Split raw text into chunks by sections."""
        chunks = []
        
        # Simple section-based chunking using string matching instead of regex
        lines = raw_doc_text.split('\n')
        current_chunk = []
        current_section = 'unknown'
        
        self.logger.debug(f"Chunking text with {len(lines)} lines")
        
        for line in lines:
            # Detect section headers using simple string matching
            line_lower = line.lower().strip()
            
            # Check for section keywords without regex
            if any(keyword in line_lower for keyword in ['results', 'outcomes', 'efficacy', 'effectiveness']):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), {'section': current_section}))
                current_chunk = [line]
                current_section = 'results'
            elif any(keyword in line_lower for keyword in ['abstract', 'summary', 'conclusion']):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), {'section': current_section}))
                current_chunk = [line]
                current_section = 'abstract'
            elif any(keyword in line_lower for keyword in ['methods', 'materials', 'protocol', 'design']):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), {'section': current_section}))
                current_chunk = [line]
                current_section = 'methods'
            elif any(keyword in line_lower for keyword in ['table', 'figure', 'supplementary']):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), {'section': current_section}))
                current_chunk = [line]
                current_section = 'table'
            else:
                current_chunk.append(line)
        
        # Add final chunk
        if current_chunk:
            chunks.append(('\n'.join(current_chunk), {'section': current_section}))
        
        self.logger.debug(f"Created {len(chunks)} chunks")
        return chunks[:self.max_text_chunks]

    def _extract_from_chunk(self, chunk_text: str, section_info: Dict[str, Any], 
                           trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract results from a text chunk using LLM prompts."""
        results = []
        
        # Use regex patterns as fallback for now, but with proper error handling
        # In a full implementation, this would call an LLM API with structured JSON output
        for metric_name, pattern in self.metric_patterns.items():
            try:
                matches = re.finditer(pattern, chunk_text, re.IGNORECASE)
                
                for match in matches:
                    # Extract value and units
                    if metric_name in ['os_fixed_time', 'pfs_fixed_time']:
                        timepoint_value = match.group(2)
                        timepoint_unit = match.group(3)
                        metric_value = float(match.group(4))
                        units = 'percent'
                    else:
                        metric_value = float(match.group(2))
                        units = match.group(3) if len(match.groups()) > 2 else self._get_default_units(metric_name)
                    
                    # Create verbatim quote from matched text (≤30 words)
                    quote_start = max(0, match.start() - 100)
                    quote_end = min(len(chunk_text), match.end() + 100)
                    full_quote = chunk_text[quote_start:quote_end].strip()
                    
                    # Truncate to ≤30 words
                    words = full_quote.split()
                    if len(words) > 30:
                        verbatim_quote = ' '.join(words[:30]) + '...'
                    else:
                        verbatim_quote = full_quote
                    
                    # Determine evidence kind
                    evidence_kind = EvidenceKind.TEXT
                    if section_info.get('section') == 'table':
                        evidence_kind = EvidenceKind.TABLE
                    
                    # Determine confidence based on match quality and section
                    confidence_llm = self._calculate_confidence_llm(
                        metric_name, metric_value, verbatim_quote, section_info
                    )
                    
                    result = {
                        'metric': metric_name,
                        'value': metric_value,
                        'units': units,
                        'summary_statistic': self._get_summary_statistic(metric_name),
                        'verbatim_quote': verbatim_quote,
                        'evidence_kind': evidence_kind,
                        'section_hint': section_info.get('section', 'unknown').title(),
                        'table_hint': None if section_info.get('section') != 'table' else 'table_data',
                        'page_hint': None,
                        'confidence_llm': confidence_llm
                    }
                    
                    results.append(result)
            except Exception as e:
                self.logger.error(f"Error processing metric {metric_name}: {e}")
                continue
        
        return results

    def _calculate_confidence_llm(self, metric_name: str, value: float, 
                                 verbatim_quote: str, section_info: Dict[str, Any]) -> float:
        """Calculate LLM confidence score for a result."""
        confidence = 0.8  # Base confidence
        
        # Boost confidence for longer, more specific quotes
        if len(verbatim_quote.split()) >= 10:
            confidence += 0.1
        
        # Boost confidence for results section
        if section_info.get('section') == 'results':
            confidence += 0.05
        
        # Boost confidence for table data
        if section_info.get('section') == 'table':
            confidence += 0.05
        
        # Reduce confidence for abstract (less reliable)
        if section_info.get('section') == 'abstract':
            confidence -= 0.1
        
        # Boost confidence for common metrics
        if metric_name in ['orr_recist', 'median_os', 'median_ttp']:
            confidence += 0.05
        
        return min(1.0, max(0.3, confidence))

    def _get_default_units(self, metric_name: str) -> str:
        """Get default units for a metric."""
        if metric_name == 'median_ttp':
            return 'weeks'
        elif metric_name == 'median_os':
            return 'months'
        elif metric_name.startswith('median_'):
            return 'months'
        elif metric_name in ['orr_recist', 'ca125_response', 'response_rate']:
            return 'percent'
        elif metric_name == 'hr':
            return 'ratio'
        else:
            return 'months'

    def _get_summary_statistic(self, metric_name: str) -> str:
        """Get summary statistic for a metric."""
        if metric_name.startswith('median_'):
            return 'median'
        elif metric_name in ['orr_recist', 'ca125_response', 'response_rate']:
            return 'proportion'
        elif metric_name == 'hr':
            return 'ratio'
        else:
            return 'not_specified'

    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate results by metric and value."""
        seen = set()
        deduplicated = []
        
        for result in results:
            # Create unique key for deduplication
            key = (result.get('metric'), result.get('value'), result.get('units'))
            
            if key not in seen:
                seen.add(key)
                deduplicated.append(result)
        
        return deduplicated
