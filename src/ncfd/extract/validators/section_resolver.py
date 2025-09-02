"""
Section Resolver

Resolves the actual section for spans, handling tables, figures, and derived spans.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from ...db.models import BaseSpan, DerivedSpan
from ...db.session import get_session


@dataclass
class SectionMapping:
    """Mapping of span_id to resolved section."""
    span_id: str
    resolved_section: str
    confidence: float
    source: str  # "heading", "table_owner", "default", "unknown"


class SectionResolver:
    """Resolves sections for spans, especially tables and figures."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the section resolver.
        
        Args:
            config: Configuration with table/figure mapping rules
        """
        self.config = config or {}
        self._table_owner_cache: Dict[Tuple[int, int], str] = {}
        self._section_aliases: Dict[str, List[str]] = {}
        self._caption_keywords: Dict[str, List[str]] = {}
        
        # Load configuration
        self._load_config()
    
    def _load_config(self):
        """Load configuration from config dict."""
        # Section aliases
        self._section_aliases = self.config.get('section_aliases', {})
        
        # Table/figure mapping
        table_config = self.config.get('table_figure_mapping', {})
        self._default_table_section = table_config.get('default_table_section', 'results')
        self._default_figure_section = table_config.get('default_figure_section', 'results')
        self._caption_keywords = table_config.get('caption_keywords', {})
    
    def resolve_section(self, span: BaseSpan, doc_spans: Optional[List[BaseSpan]] = None) -> str:
        """
        Resolve the section for a span.
        
        Args:
            span: The span to resolve
            doc_spans: All spans in the document (for context)
            
        Returns:
            Resolved section name
        """
        # Handle table cells
        if span.is_table_cell:
            return self._resolve_table_section(span, doc_spans)
        
        # Handle figures
        if span.section.lower() in ['figure', 'fig']:
            return self._resolve_figure_section(span, doc_spans)
        
        # Handle regular spans
        return self._normalize_section(span.section)
    
    def resolve_derived_span_section(self, derived_span: DerivedSpan, 
                                   base_spans: List[BaseSpan]) -> str:
        """
        Resolve section for a derived span by looking at its parent spans.
        
        Args:
            derived_span: The derived span
            base_spans: List of base spans to search
            
        Returns:
            Resolved section name
        """
        # Find parent spans
        parent_sections = []
        for parent_id in derived_span.parent_span_ids:
            parent_span = next((s for s in base_spans if s.span_id == parent_id), None)
            if parent_span:
                resolved_section = self.resolve_section(parent_span, base_spans)
                parent_sections.append(resolved_section)
        
        if not parent_sections:
            return "unknown"
        
        # Return the most common section, or the first if tied
        from collections import Counter
        section_counts = Counter(parent_sections)
        return section_counts.most_common(1)[0][0]
    
    def _resolve_table_section(self, span: BaseSpan, doc_spans: Optional[List[BaseSpan]] = None) -> str:
        """
        Resolve section for a table cell by finding the table's owner section.
        
        Args:
            span: Table cell span
            doc_spans: All spans in the document
            
        Returns:
            Resolved section name
        """
        if not span.table_id:
            return self._default_table_section
        
        # Check cache first
        cache_key = (span.doc_id, span.table_id)
        if cache_key in self._table_owner_cache:
            return self._table_owner_cache[cache_key]
        
        # Try to find table owner by scanning for nearby headings
        if doc_spans:
            owner_section = self._find_table_owner_by_headings(span, doc_spans)
            if owner_section:
                self._table_owner_cache[cache_key] = owner_section
                return owner_section
        
        # Fallback to default
        self._table_owner_cache[cache_key] = self._default_table_section
        return self._default_table_section
    
    def _resolve_figure_section(self, span: BaseSpan, doc_spans: Optional[List[BaseSpan]] = None) -> str:
        """
        Resolve section for a figure by finding the figure's owner section.
        
        Args:
            span: Figure span
            doc_spans: All spans in the document
            
        Returns:
            Resolved section name
        """
        # Try to find figure owner by scanning for nearby headings
        if doc_spans:
            owner_section = self._find_figure_owner_by_headings(span, doc_spans)
            if owner_section:
                return owner_section
        
        # Fallback to default
        return self._default_figure_section
    
    def _find_table_owner_by_headings(self, table_span: BaseSpan, doc_spans: List[BaseSpan]) -> Optional[str]:
        """
        Find table owner by scanning for nearby headings.
        
        Args:
            table_span: The table span
            doc_spans: All spans in the document
            
        Returns:
            Owner section name or None
        """
        # Find headings near the table
        nearby_headings = []
        
        for span in doc_spans:
            if span.page != table_span.page:
                continue
            
            # Check if this is a heading
            if self._is_heading_span(span):
                # Calculate distance (simplified)
                distance = abs(span.char_start - table_span.char_start)
                if distance < 5000:  # Within reasonable distance
                    nearby_headings.append((span, distance))
        
        if not nearby_headings:
            return None
        
        # Sort by distance and take the closest
        nearby_headings.sort(key=lambda x: x[1])
        closest_heading = nearby_headings[0][0]
        
        return self._normalize_section(closest_heading.section)
    
    def _find_figure_owner_by_headings(self, figure_span: BaseSpan, doc_spans: List[BaseSpan]) -> Optional[str]:
        """
        Find figure owner by scanning for nearby headings.
        
        Args:
            figure_span: The figure span
            doc_spans: All spans in the document
            
        Returns:
            Owner section name or None
        """
        # Similar to table owner finding
        return self._find_table_owner_by_headings(figure_span, doc_spans)
    
    def _is_heading_span(self, span: BaseSpan) -> bool:
        """
        Check if a span is a heading.
        
        Args:
            span: The span to check
            
        Returns:
            True if it's a heading
        """
        # Check for ALL CAPS (common heading pattern)
        if span.text.isupper() and len(span.text.split()) <= 5:
            return True
        
        # Check for numbered headings
        if re.match(r'^\d+\.\s*[A-Z]', span.text):
            return True
        
        # Check for common heading keywords
        heading_keywords = ['methods', 'results', 'discussion', 'conclusion', 'abstract', 'introduction']
        text_lower = span.text.lower()
        return any(keyword in text_lower for keyword in heading_keywords)
    
    def _normalize_section(self, section: str) -> str:
        """
        Normalize section name using aliases.
        
        Args:
            section: Raw section name
            
        Returns:
            Normalized section name
        """
        section_lower = section.lower()
        
        # Check aliases
        for alias_group, aliases in self._section_aliases.items():
            if any(alias.lower() == section_lower for alias in aliases):
                return alias_group
        
        # Return original if no alias found
        return section
    
    def get_span_sections(self, span_ids: List[str], base_spans: List[BaseSpan]) -> List[str]:
        """
        Get resolved sections for a list of span IDs.
        
        Args:
            span_ids: List of span IDs
            base_spans: List of base spans to search
            
        Returns:
            List of resolved section names
        """
        sections = []
        
        for span_id in span_ids:
            # Find the span
            span = next((s for s in base_spans if s.span_id == span_id), None)
            if span:
                resolved_section = self.resolve_section(span, base_spans)
                sections.append(resolved_section)
            else:
                sections.append("unknown")
        
        return sections
    
    def clear_cache(self):
        """Clear the table owner cache."""
        self._table_owner_cache.clear()


def create_section_resolver(config_path: Optional[str] = None) -> SectionResolver:
    """
    Create a section resolver with configuration.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configured SectionResolver
    """
    import yaml
    
    config = {}
    if config_path:
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load section constraints config from {config_path}: {e}")
    
    return SectionResolver(config)
