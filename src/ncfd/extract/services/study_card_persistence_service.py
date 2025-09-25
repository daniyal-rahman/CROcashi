"""
Study Card Persistence Service for Study Card Pipeline.

Handles database persistence of study cards, factsheets, and patterns.
This service extracts the persistence logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
from datetime import datetime, timezone

from ncfd.ingest.pubmed.document_manager import DocumentManager
from ncfd.db.session import session_scope
from ncfd.db.models import StudyCard, Factsheet, Trial, Document, PatternDetection

logger = logging.getLogger(__name__)


@dataclass
class PersistenceResult:
    """Result of persistence operations."""
    study_cards_saved: int
    factsheets_saved: int
    patterns_saved: int
    quotes_saved: int
    total_saved: int
    persistence_errors: List[str]


class StudyCardPersistenceService:
    """
    Service for persisting study card pipeline results to database.
    
    This service handles:
    - Study card persistence
    - Factsheet persistence
    - Pattern persistence
    - Quote persistence
    - Error handling and validation
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the persistence service.
        
        Args:
            config: Configuration dictionary with persistence settings
        """
        self.config = config
        self.persistence_config = config.get('persistence', {})
        
        # Initialize document manager
        self.document_manager = DocumentManager()
        
        # Configuration values
        self.batch_size = self.persistence_config.get('batch_size', 100)
        self.max_retries = self.persistence_config.get('max_retries', 3)
    
    async def persist_results(
        self, 
        study_cards: List[Dict[str, Any]], 
        factsheets: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        quotes: List[Dict[str, Any]],
        trial_id: str
    ) -> PersistenceResult:
        """
        Persist all pipeline results to database.
        
        Args:
            study_cards: List of study cards to persist
            factsheets: List of factsheets to persist
            patterns: List of patterns to persist
            quotes: List of quotes to persist
            trial_id: Trial ID for context
            
        Returns:
            PersistenceResult with persistence statistics
        """
        logger.info(f"💾 Starting persistence for trial {trial_id}: {len(study_cards)} study cards, {len(factsheets)} factsheets, {len(patterns)} patterns, {len(quotes)} quotes")
        
        persistence_errors = []
        study_cards_saved = 0
        factsheets_saved = 0
        patterns_saved = 0
        quotes_saved = 0
        
        try:
            # Persist study cards
            if study_cards:
                study_cards_saved = await self._persist_study_cards(study_cards, trial_id)
                logger.info(f"Saved {study_cards_saved} study cards")
            
            # Persist factsheets
            if factsheets:
                factsheets_saved = await self._persist_factsheets(factsheets, trial_id)
                logger.info(f"Saved {factsheets_saved} factsheets")
            
            # Persist patterns
            if patterns:
                patterns_saved = await self._persist_patterns(patterns, trial_id)
                logger.info(f"Saved {patterns_saved} patterns")
            
            # Persist quotes
            if quotes:
                quotes_saved = await self._persist_quotes(quotes, trial_id)
                logger.info(f"Saved {quotes_saved} quotes")
            
            total_saved = study_cards_saved + factsheets_saved + patterns_saved + quotes_saved
            
            logger.info(f"✅ Persistence completed for trial {trial_id}: {study_cards_saved} study cards, {factsheets_saved} factsheets, {patterns_saved} patterns, {quotes_saved} quotes saved")
            
            return PersistenceResult(
                study_cards_saved=study_cards_saved,
                factsheets_saved=factsheets_saved,
                patterns_saved=patterns_saved,
                quotes_saved=quotes_saved,
                total_saved=total_saved,
                persistence_errors=persistence_errors
            )
            
        except Exception as e:
            error_msg = f"Error in persistence for trial {trial_id}: {str(e)}"
            persistence_errors.append(error_msg)
            logger.error(error_msg)
            
            return PersistenceResult(
                study_cards_saved=study_cards_saved,
                factsheets_saved=factsheets_saved,
                patterns_saved=patterns_saved,
                quotes_saved=quotes_saved,
                total_saved=study_cards_saved + factsheets_saved + patterns_saved + quotes_saved,
                persistence_errors=persistence_errors
            )
    
    async def _persist_study_cards(self, study_cards: List[Dict[str, Any]], trial_id: str) -> int:
        """Persist study cards to database."""
        saved_count = 0
        
        try:
            with session_scope() as session:
                for study_card in study_cards:
                    try:
                        # Create study card record
                        study_card_record = StudyCard(
                            doc_id=study_card.get('document_id'),
                            summary_text=study_card.get('summary', ''),
                            risks_text=study_card.get('risks', ''),
                            methods_text=study_card.get('methods', ''),
                            gates_json=study_card.get('gates', {}),
                            p_fail=study_card.get('p_fail'),
                            model_name=study_card.get('model_name', 'refactored_pipeline'),
                            authored_by=study_card.get('authored_by', 'llm'),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        
                        session.add(study_card_record)
                        saved_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error saving study card {study_card.get('document_id')}: {e}")
                        continue
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error in study card persistence: {e}")
            raise
        
        return saved_count
    
    def _safe_numeric_value(self, value: Any) -> Optional[float]:
        """Convert value to numeric, returning None for non-numeric strings."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Check if it's a numeric string
            try:
                return float(value)
            except ValueError:
                # Non-numeric string like "Not reported in document"
                return None
        return None
    
    async def _persist_factsheets(self, factsheets: List[Dict[str, Any]], trial_id: str) -> int:
        """Persist factsheets to database."""
        saved_count = 0
        
        try:
            with session_scope() as session:
                for factsheet in factsheets:
                    try:
                        # Create factsheet record with new JSONB schema
                        factsheet_record = Factsheet(
                            doc_id=factsheet.get('document_id'),
                            # New JSONB-based fields
                            study_type=factsheet.get('study_type'),
                            factsheet_sections=factsheet.get('factsheet_sections', {}),
                            provenance=factsheet.get('provenance', {}),
                            normalized_facts=factsheet.get('normalized_facts', {}),
                            # Legacy fields for backward compatibility
                            results=factsheet.get('results', {}),
                            primary_endpoint_results=factsheet.get('primary_endpoint_results', {}),
                            secondary_endpoint_results=factsheet.get('secondary_endpoint_results', {}),
                            safety_results=factsheet.get('safety_results', {}),
                            primary_analysis_set=factsheet.get('primary_analysis_set'),
                            secondary_analysis_sets=factsheet.get('secondary_analysis_sets', {}),
                            total_enrolled=self._safe_numeric_value(factsheet.get('total_enrolled')),
                            completed_primary_endpoint=self._safe_numeric_value(factsheet.get('completed_primary_endpoint')),
                            dropout_rate=self._safe_numeric_value(factsheet.get('dropout_rate')),
                            follow_up_completion=self._safe_numeric_value(factsheet.get('follow_up_completion')),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        
                        session.add(factsheet_record)
                        saved_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error saving factsheet {factsheet.get('document_id')}: {e}")
                        continue
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error in factsheet persistence: {e}")
            raise
        
        return saved_count
    
    async def _persist_patterns(self, patterns: List[Dict[str, Any]], trial_id: str) -> int:
        """Persist patterns to database."""
        if not patterns:
            return 0
        
        try:
            with session_scope() as session:
                patterns_saved = 0
                for pattern in patterns:
                    pattern_record = PatternDetection(
                        trial_id=int(trial_id),
                        run_id=pattern.get('run_id', 'refactored_pipeline'),
                        family_id=pattern.get('family_id', 'XX'),
                        pattern_id=pattern.get('pattern_id', 'XXXX'),
                        severity=pattern.get('severity', 0),
                        confidence=pattern.get('confidence', 0.0),
                        rationale=pattern.get('rationale', ''),
                        evidence_spans=pattern.get('evidence_spans', {})
                    )
                    session.add(pattern_record)
                    patterns_saved += 1
                
                session.commit()
                logger.info(f"Persisted {patterns_saved} patterns for trial {trial_id}")
                return patterns_saved
                
        except Exception as e:
            logger.error(f"Error persisting patterns for trial {trial_id}: {e}")
            return 0
    
    async def _persist_quotes(self, quotes: List[Dict[str, Any]], trial_id: str) -> int:
        """Persist quotes to database."""
        if not quotes:
            return 0
            
        try:
            from ncfd.db.session import session_scope
            from ncfd.db.models import EvidenceSpan
            
            persisted_count = 0
            
            with session_scope() as session:
                for quote in quotes:
                    try:
                        evidence_span = EvidenceSpan(
                            doc_id=quote.get('doc_id'),
                            trial_id=trial_id,
                            field_name=quote.get('field_name', 'unknown'),
                            field_value=quote.get('field_value'),
                            quote_text=quote.get('quote_text', ''),
                            start_char=quote.get('start_char'),
                            end_char=quote.get('end_char'),
                            page_number=quote.get('page_number'),
                            confidence=quote.get('confidence'),
                            extraction_method=quote.get('extraction_method', 'llm')
                        )
                        
                        session.add(evidence_span)
                        persisted_count += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to persist quote: {e}")
                        continue
                
                session.commit()
                logger.info(f"Persisted {persisted_count} quotes for trial {trial_id}")
                
        except Exception as e:
            logger.error(f"Error persisting quotes for trial {trial_id}: {e}")
            return 0
            
        return persisted_count
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
