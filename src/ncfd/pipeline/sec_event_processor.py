"""
SEC Event Processor for handling extracted information.

This module processes extracted SEC information and:
- Links trial events to existing trials
- Updates clinical development status
- Triggers signal evaluation
- Manages review queues
- Integrates with existing systems
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from ..ingest.sec_types import (
    EightKItem, TenKSection, FilingMetadata, ExtractionResult
)

logger = logging.getLogger(__name__)


@dataclass
class TrialEvent:
    """Processed trial event from SEC filing."""
    filing_id: str
    company_cik: int
    company_name: str
    filing_date: datetime
    
    # Event details
    event_type: str
    event_description: str
    trial_identifier: Optional[str] = None
    trial_phase: Optional[str] = None
    
    # Clinical details
    primary_endpoint_outcome: Optional[str] = None
    safety_events: List[str] = None
    enrollment_impact: Optional[str] = None
    
    # Processing metadata
    extracted_at: datetime = None
    confidence: float = 0.0
    requires_review: bool = False
    review_status: str = "pending"
    
    # Integration metadata
    linked_trial_id: Optional[str] = None
    signal_evaluation_triggered: bool = False
    entity_resolution_complete: bool = False
    
    def __post_init__(self):
        """Set default values."""
        if self.safety_events is None:
            self.safety_events = []
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()


@dataclass
class ClinicalDevelopmentUpdate:
    """Processed clinical development update from SEC filing."""
    filing_id: str
    company_cik: int
    company_name: str
    filing_date: datetime
    
    # Pipeline information
    pipeline_stage: Optional[str] = None
    pivotal_status: Optional[str] = None
    enrollment_target: Optional[str] = None
    enrollment_current: Optional[str] = None
    
    # Regulatory information
    fda_interactions: List[str] = None
    regulatory_milestones: List[str] = None
    
    # Clinical details
    primary_endpoints: List[str] = None
    secondary_endpoints: List[str] = None
    
    # Processing metadata
    extracted_at: datetime = None
    confidence: float = 0.0
    requires_review: bool = False
    review_status: str = "pending"
    
    # Integration metadata
    linked_trials: List[str] = None
    pipeline_updated: bool = False
    regulatory_monitoring_triggered: bool = False
    
    def __post_init__(self):
        """Set default values."""
        if self.fda_interactions is None:
            self.fda_interactions = []
        if self.regulatory_milestones is None:
            self.regulatory_milestones = []
        if self.primary_endpoints is None:
            self.primary_endpoints = []
        if self.secondary_endpoints is None:
            self.secondary_endpoints = []
        if self.linked_trials is None:
            self.linked_trials = []
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()


@dataclass
class ReviewItem:
    """Item flagged for human review."""
    item_id: str
    filing_id: str
    company_cik: int
    item_type: str  # "trial_event" or "clinical_update"
    
    # Review details
    reason: str
    confidence: float
    extracted_content: str
    evidence_spans: List[Dict[str, Any]]
    
    # Review metadata
    flagged_at: datetime
    assigned_to: Optional[str] = None
    review_status: str = "pending"
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class SecEventProcessor:
    """
    Processes extracted SEC information and integrates with existing systems.
    
    Features:
    - Trial event processing and linking
    - Clinical development updates
    - Signal evaluation triggering
    - Review queue management
    - Entity resolution
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the event processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Processing queues
        self.trial_events: List[TrialEvent] = []
        self.clinical_updates: List[ClinicalDevelopmentUpdate] = []
        self.review_queue: List[ReviewItem] = []
        
        # Integration flags
        self.auto_link_trials = config.get('integration', {}).get('auto_link_trials', True)
        self.auto_trigger_signals = config.get('integration', {}).get('auto_trigger_signals', True)
        self.auto_resolve_entities = config.get('integration', {}).get('auto_resolve_entities', True)
        
        # Review thresholds
        self.review_confidence_threshold = config.get('review', {}).get('confidence_threshold', 0.7)
        self.review_on_low_confidence = config.get('review', {}).get('review_on_low_confidence', True)
        
        self.logger.info("SEC Event Processor initialized")
    
    def process_extraction_result(
        self, 
        extraction_result: ExtractionResult,
        filing_metadata: FilingMetadata
    ) -> Dict[str, Any]:
        """
        Process extraction result and create structured events.
        
        Args:
            extraction_result: Result from LangExtract
            filing_metadata: Filing metadata
            
        Returns:
            Processing result summary
        """
        self.logger.info(f"Processing extraction result for {filing_metadata.accession}")
        
        processed_items = {
            'trial_events': 0,
            'clinical_updates': 0,
            'review_items': 0,
            'errors': []
        }
        
        try:
            for item in extraction_result.extracted_items:
                if isinstance(item, EightKItem):
                    # Process 8-K trial events
                    trial_event = self._process_trial_event(item, filing_metadata)
                    if trial_event:
                        self.trial_events.append(trial_event)
                        processed_items['trial_events'] += 1
                        
                        # Check if review is needed
                        if self._needs_review(trial_event):
                            review_item = self._create_review_item(trial_event, "trial_event")
                            self.review_queue.append(review_item)
                            processed_items['review_items'] += 1
                
                elif isinstance(item, TenKSection):
                    # Process 10-K clinical development
                    clinical_update = self._process_clinical_update(item, filing_metadata)
                    if clinical_update:
                        self.clinical_updates.append(clinical_update)
                        processed_items['clinical_updates'] += 1
                        
                        # Check if review is needed
                        if self._needs_review(clinical_update):
                            review_item = self._create_review_item(clinical_update, "clinical_update")
                            self.review_queue.append(review_item)
                            processed_items['review_items'] += 1
            
            # Process events if auto-processing is enabled
            if self.auto_link_trials:
                self._process_trial_events()
            
            if self.auto_trigger_signals:
                self._trigger_signal_evaluations()
            
            if self.auto_resolve_entities:
                self._resolve_entities()
            
            self.logger.info(
                f"Processed {processed_items['trial_events']} trial events, "
                f"{processed_items['clinical_updates']} clinical updates, "
                f"{processed_items['review_items']} review items"
            )
            
        except Exception as e:
            error_msg = f"Error processing extraction result: {e}"
            self.logger.error(error_msg)
            processed_items['errors'].append(error_msg)
        
        return processed_items
    
    def _process_trial_event(self, item: EightKItem, filing_metadata: FilingMetadata) -> Optional[TrialEvent]:
        """Process 8-K trial event item."""
        try:
            trial_event = TrialEvent(
                filing_id=filing_metadata.accession,
                company_cik=filing_metadata.cik,
                company_name=filing_metadata.company_name,
                filing_date=filing_metadata.filing_date,
                event_type=item.trial_events[0] if item.trial_events else "unknown",
                event_description=item.trial_events[0] if item.trial_events else "",
                trial_identifier=getattr(item, 'trial_identifier', None),
                trial_phase=getattr(item, 'trial_phase', None),
                primary_endpoint_outcome=item.endpoints_mentioned[0] if item.endpoints_mentioned else None,
                safety_events=item.safety_signals,
                enrollment_impact=getattr(item, 'enrollment_impact', None),
                confidence=item.confidence,
                requires_review=item.requires_review
            )
            
            return trial_event
            
        except Exception as e:
            self.logger.error(f"Error processing trial event: {e}")
            return None
    
    def _process_clinical_update(self, item: TenKSection, filing_metadata: FilingMetadata) -> Optional[ClinicalDevelopmentUpdate]:
        """Process 10-K clinical development update."""
        try:
            clinical_update = ClinicalDevelopmentUpdate(
                filing_id=filing_metadata.accession,
                company_cik=filing_metadata.cik,
                company_name=filing_metadata.company_name,
                filing_date=filing_metadata.filing_date,
                pipeline_stage=item.clinical_development[0] if item.clinical_development else None,
                pivotal_status=getattr(item, 'pivotal_status', None),
                enrollment_target=getattr(item, 'enrollment_target', None),
                enrollment_current=getattr(item, 'enrollment_current', None),
                fda_interactions=item.regulatory_updates,
                regulatory_milestones=item.regulatory_updates,
                primary_endpoints=item.primary_endpoints,
                secondary_endpoints=item.secondary_endpoints,
                confidence=item.confidence,
                requires_review=item.requires_review
            )
            
            return clinical_update
            
        except Exception as e:
            self.logger.error(f"Error processing clinical update: {e}")
            return None
    
    def _needs_review(self, item: Any) -> bool:
        """Check if item needs human review."""
        # Check confidence threshold
        if hasattr(item, 'confidence') and item.confidence < self.review_confidence_threshold:
            return True
        
        # Check if explicitly flagged
        if hasattr(item, 'requires_review') and item.requires_review:
            return True
        
        # Check for missing critical information
        if isinstance(item, TrialEvent):
            if not item.trial_identifier and item.event_type in ['endpoint_met', 'safety_signal']:
                return True
        
        return False
    
    def _create_review_item(self, item: Any, item_type: str) -> ReviewItem:
        """Create review item for flagged content."""
        review_item = ReviewItem(
            item_id=f"{item_type}_{len(self.review_queue)}",
            filing_id=item.filing_id,
            company_cik=item.company_cik,
            item_type=item_type,
            reason="Low confidence or validation issues",
            confidence=getattr(item, 'confidence', 0.0),
            extracted_content=str(item),
            evidence_spans=getattr(item, 'evidence_spans', []),
            flagged_at=datetime.utcnow()
        )
        
        return review_item
    
    def _process_trial_events(self):
        """Process trial events and link to existing trials."""
        self.logger.info(f"Processing {len(self.trial_events)} trial events")
        
        for event in self.trial_events:
            try:
                # TODO: Implement trial linking logic
                # - Search for trials by company and phase
                # - Match trial identifiers (NCT IDs)
                # - Update trial status and milestones
                
                event.entity_resolution_complete = True
                self.logger.info(f"Processed trial event: {event.event_type}")
                
            except Exception as e:
                self.logger.error(f"Error processing trial event: {e}")
    
    def _trigger_signal_evaluations(self):
        """Trigger signal evaluation for relevant events."""
        self.logger.info("Triggering signal evaluations")
        
        for event in self.trial_events:
            try:
                # Check if event should trigger signal evaluation
                if self._should_trigger_signals(event):
                    # TODO: Implement signal evaluation triggering
                    # - Create signal evaluation job
                    # - Update trial risk assessment
                    # - Trigger alerts if needed
                    
                    event.signal_evaluation_triggered = True
                    self.logger.info(f"Triggered signal evaluation for: {event.event_type}")
                
            except Exception as e:
                self.logger.error(f"Error triggering signal evaluation: {e}")
    
    def _should_trigger_signals(self, event: TrialEvent) -> bool:
        """Determine if event should trigger signal evaluation."""
        # High-impact events
        high_impact_types = [
            'endpoint_met', 'endpoint_missed', 'safety_signal', 
            'program_discontinuation', 'regulatory_hold'
        ]
        
        if event.event_type in high_impact_types:
            return True
        
        # Events with safety implications
        if event.safety_events:
            return True
        
        # Events affecting primary endpoints
        if event.primary_endpoint_outcome:
            return True
        
        return False
    
    def _resolve_entities(self):
        """Resolve company and trial entities."""
        self.logger.info("Resolving entities")
        
        # TODO: Implement entity resolution
        # - Link companies to existing company database
        # - Resolve trial sponsors and collaborators
        # - Update entity relationships
        
        pass
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get summary of processing status."""
        return {
            'trial_events_processed': len(self.trial_events),
            'clinical_updates_processed': len(self.clinical_updates),
            'review_queue_size': len(self.review_queue),
            'pending_reviews': len([r for r in self.review_queue if r.review_status == "pending"]),
            'auto_processing_enabled': {
                'trial_linking': self.auto_link_trials,
                'signal_triggering': self.auto_trigger_signals,
                'entity_resolution': self.auto_resolve_entities
            }
        }
    
    def get_review_queue(self, status: Optional[str] = None) -> List[ReviewItem]:
        """Get review queue items, optionally filtered by status."""
        if status:
            return [r for r in self.review_queue if r.review_status == status]
        return self.review_queue
    
    def update_review_status(self, item_id: str, status: str, notes: Optional[str] = None):
        """Update review item status."""
        for item in self.review_queue:
            if item.item_id == item_id:
                item.review_status = status
                item.review_notes = notes
                item.reviewed_at = datetime.utcnow()
                self.logger.info(f"Updated review status for {item_id} to {status}")
                break
    
    def clear_processed_events(self):
        """Clear processed events to free memory."""
        self.trial_events.clear()
        self.clinical_updates.clear()
        self.logger.info("Cleared processed events")
    
    def export_events(self, format: str = "json") -> str:
        """Export events in specified format."""
        if format == "json":
            import json
            data = {
                'trial_events': [vars(event) for event in self.trial_events],
                'clinical_updates': [vars(update) for update in self.clinical_updates],
                'exported_at': datetime.utcnow().isoformat()
            }
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
