"""
Patent Query Builder for Trial-Specific Patent Searches

This module provides trial-specific patent query building functionality,
extracting relevant keywords and building search queries from trial data.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging
from datetime import datetime, timezone

from .patent_types import PatentSearchQuery

logger = logging.getLogger(__name__)


@dataclass
class TrialPatentContext:
    """Context for building patent queries from trial data."""
    trial_id: str
    title: Optional[str] = None
    interventions: List[Dict[str, Any]] = None
    conditions: List[Dict[str, Any]] = None
    companies: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.interventions is None:
            self.interventions = []
        if self.conditions is None:
            self.conditions = []
        if self.companies is None:
            self.companies = []


class PatentQueryBuilder:
    """Builds patent search queries from trial data."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the patent query builder.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.max_title_keywords = self.config.get('max_title_keywords', 5)
        self.max_abstract_keywords = self.config.get('max_abstract_keywords', 5)
        self.max_results = self.config.get('max_results', 100)
        self.pharmaceutical_only = self.config.get('pharmaceutical_only', True)
        
        # Stop words for keyword extraction
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'study', 'trial', 'phase', 'randomized', 
            'controlled', 'clinical', 'evaluation', 'assessment', 'safety',
            'efficacy', 'treatment', 'therapy', 'drug', 'medication'
        }
    
    def build_query_from_trial(self, trial_context: TrialPatentContext) -> PatentSearchQuery:
        """
        Build a patent search query from trial context.
        
        Args:
            trial_context: Trial context with data for query building
            
        Returns:
            PatentSearchQuery object
        """
        self.logger.info(f"Building patent query for trial {trial_context.trial_id}")
        
        # Extract keywords from trial data
        title_keywords = self._extract_title_keywords(trial_context)
        abstract_keywords = self._extract_abstract_keywords(trial_context)
        assignees = self._extract_assignees(trial_context)
        
        # Build search query
        query = PatentSearchQuery(
            title_keywords=title_keywords[:self.max_title_keywords],
            abstract_keywords=abstract_keywords[:self.max_abstract_keywords],
            assignee=assignees[0] if assignees else None,
            pharmaceutical_only=self.pharmaceutical_only,
            max_results=self.max_results
        )
        
        self.logger.info(f"Built patent query: {len(title_keywords)} title keywords, {len(abstract_keywords)} abstract keywords, {len(assignees)} assignees")
        
        return query
    
    def _extract_title_keywords(self, trial_context: TrialPatentContext) -> List[str]:
        """Extract keywords from trial title and interventions."""
        keywords = []
        
        # Extract from title
        if trial_context.title:
            title_keywords = self._extract_keywords_from_text(trial_context.title)
            keywords.extend(title_keywords)
        
        # Extract from interventions
        for intervention in trial_context.interventions:
            if 'name' in intervention:
                intervention_keywords = self._extract_keywords_from_text(intervention['name'])
                keywords.extend(intervention_keywords)
        
        return keywords
    
    def _extract_abstract_keywords(self, trial_context: TrialPatentContext) -> List[str]:
        """Extract keywords from trial conditions."""
        keywords = []
        
        for condition in trial_context.conditions:
            if 'name' in condition:
                condition_keywords = self._extract_keywords_from_text(condition['name'])
                keywords.extend(condition_keywords)
        
        return keywords
    
    def _extract_assignees(self, trial_context: TrialPatentContext) -> List[str]:
        """Extract company names for assignee search."""
        assignees = []
        
        for company in trial_context.companies:
            if 'name' in company:
                assignees.append(company['name'])
        
        return assignees
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """
        Extract patent-relevant keywords from text.
        
        Args:
            text: Text to extract keywords from
            
        Returns:
            List of patent-relevant keywords
        """
        if not text:
            return []
        
        # Simple extraction - could be enhanced with NLP
        words = text.lower().split()
        
        # Filter out common words and focus on technical terms
        technical_terms = [
            word for word in words 
            if word not in self.stop_words and len(word) > 3
        ]
        
        return technical_terms


class PatentResultProcessor:
    """Processes patent search results for trial context."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def process_patent_results(self, patent_results: List[Any], trial_id: str, search_query: PatentSearchQuery) -> Dict[str, Any]:
        """
        Process patent search results for trial context.
        
        Args:
            patent_results: List of patent records
            trial_id: Trial identifier
            search_query: Original search query
            
        Returns:
            Processed results dictionary
        """
        processed_patents = []
        
        for patent in patent_results:
            processed_patent = {
                'patent_number': patent.patent_number,
                'title': patent.title,
                'abstract': patent.abstract,
                'inventors': patent.inventors,
                'assignees': patent.assignees,
                'grant_date': patent.grant_date.isoformat() if patent.grant_date else None,
                'application_date': patent.application_date.isoformat() if patent.application_date else None,
                'cpc_classes': patent.cpc_classes,
                'patent_status': patent.patent_status,
                'is_pharmaceutical': patent.is_pharmaceutical
            }
            processed_patents.append(processed_patent)
        
        return {
            'trial_id': trial_id,
            'search_query': search_query.to_uspto_query(),
            'patents_found': len(processed_patents),
            'processed_patents': processed_patents,
            'searched_at': datetime.now(timezone.utc)
        }
