"""
Asset Ownership Timeline Reconstruction

Builds comprehensive ownership timelines for assets by combining evidence from:
1. Patent assignment records
2. SEC filings (8-K Item 1.01, licensing deals)
3. Press releases mentioning asset transfers
4. Clinical trial sponsor changes
5. Corporate transaction records

Provides reconciliation of conflicting evidence and confidence scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.models import Asset, Company, Patent, PatentAssignment, Study, Trial

logger = logging.getLogger(__name__)


@dataclass
class OwnershipPeriod:
    """Represents a period of asset ownership."""
    start_date: date
    end_date: Optional[date]
    owner_company_id: int
    owner_company_name: str
    ownership_type: str  # "assignee", "licensee", "co_owner", "inventor"
    ownership_percentage: Optional[Decimal] = None
    confidence_score: Decimal = Decimal("0.0")
    
    # Supporting evidence
    evidence_events: List['OwnershipEvent'] = field(default_factory=list)
    
    @property
    def is_current(self) -> bool:
        """Check if this ownership period is current."""
        return self.end_date is None or self.end_date >= date.today()
    
    @property
    def duration_days(self) -> Optional[int]:
        """Get duration in days."""
        if not self.end_date:
            return None
        return (self.end_date - self.start_date).days


@dataclass
class OwnershipEvent:
    """Represents a single ownership change event."""
    event_date: date
    event_type: str  # "patent_assignment", "sec_filing", "press_release", "clinical_trial"
    
    # Ownership change details
    from_company_id: Optional[int] = None
    from_company_name: Optional[str] = None
    to_company_id: Optional[int] = None
    to_company_name: Optional[str] = None
    
    # Event details
    ownership_type: str = ""
    consideration_amount: Optional[Decimal] = None
    consideration_type: Optional[str] = None
    
    # Evidence
    evidence_source: str = ""
    evidence_url: Optional[str] = None
    confidence_score: Decimal = Decimal("0.0")
    description: Optional[str] = None
    
    # Metadata
    source_record_id: Optional[str] = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OwnershipTimeline:
    """Complete ownership timeline for an asset."""
    asset_id: int
    asset_name: str
    
    # Timeline periods
    ownership_periods: List[OwnershipPeriod] = field(default_factory=list)
    
    # All events (for audit trail)
    all_events: List[OwnershipEvent] = field(default_factory=list)
    
    # Timeline metadata
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None
    total_ownership_changes: int = 0
    
    # Reconciliation info
    conflicting_events: List[Tuple[OwnershipEvent, OwnershipEvent]] = field(default_factory=list)
    confidence_gaps: List[str] = field(default_factory=list)
    
    def get_current_owner(self) -> Optional[OwnershipPeriod]:
        """Get current owner of the asset."""
        current_periods = [p for p in self.ownership_periods if p.is_current]
        if not current_periods:
            return None
        
        # Return highest confidence current owner
        return max(current_periods, key=lambda p: p.confidence_score)
    
    def get_owner_at_date(self, target_date: date) -> Optional[OwnershipPeriod]:
        """Get owner at a specific date."""
        for period in self.ownership_periods:
            if (period.start_date <= target_date and 
                (period.end_date is None or period.end_date >= target_date)):
                return period
        return None


class OwnershipTimelineBuilder:
    """
    Builds asset ownership timelines from multiple evidence sources.
    
    Combines data from:
    - Patent assignments
    - SEC filings
    - Press releases
    - Clinical trial sponsor changes
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize timeline builder.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Confidence weights for different evidence types
        self.evidence_weights = self.config.get("evidence_weights", {
            "patent_assignment": 0.90,
            "sec_filing": 0.85,
            "press_release": 0.75,
            "clinical_trial": 0.60,
            "manual": 1.0
        })
        
        # Minimum confidence for including events
        self.min_confidence = self.config.get("min_confidence", 0.40)
        
        # Maximum gap between events for consolidation
        self.max_consolidation_gap_days = self.config.get("max_consolidation_gap_days", 30)
        
        logger.info("Initialized ownership timeline builder")
    
    def build_timeline(self, session: Session, asset_id: int) -> OwnershipTimeline:
        """
        Build complete ownership timeline for an asset.
        
        Args:
            session: Database session
            asset_id: Asset ID to build timeline for
            
        Returns:
            Complete ownership timeline
        """
        logger.info(f"Building ownership timeline for asset {asset_id}")
        
        # Get asset info
        asset = session.query(Asset).filter(Asset.asset_id == asset_id).first()
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        
        asset_name = self._get_asset_display_name(asset)
        
        # Collect all ownership events
        all_events = []
        
        # 1. Patent assignment events
        patent_events = self._extract_patent_assignment_events(session, asset_id)
        all_events.extend(patent_events)
        logger.debug(f"Found {len(patent_events)} patent assignment events")
        
        # 2. SEC filing events
        sec_events = self._extract_sec_filing_events(session, asset_id)
        all_events.extend(sec_events)
        logger.debug(f"Found {len(sec_events)} SEC filing events")
        
        # 3. Press release events
        pr_events = self._extract_press_release_events(session, asset_id)
        all_events.extend(pr_events)
        logger.debug(f"Found {len(pr_events)} press release events")
        
        # 4. Clinical trial sponsor changes
        trial_events = self._extract_trial_sponsor_events(session, asset_id)
        all_events.extend(trial_events)
        logger.debug(f"Found {len(trial_events)} trial sponsor events")
        
        # 5. Existing ownership records
        existing_events = self._extract_existing_ownership_events(session, asset_id)
        all_events.extend(existing_events)
        logger.debug(f"Found {len(existing_events)} existing ownership events")
        
        # Filter by confidence
        valid_events = [e for e in all_events if e.confidence_score >= self.min_confidence]
        logger.debug(f"Filtered to {len(valid_events)} valid events")
        
        # Sort by date
        valid_events.sort(key=lambda e: e.event_date)
        
        # Reconcile conflicting events
        reconciled_events, conflicts = self._reconcile_ownership_events(valid_events)
        
        # Build ownership periods
        ownership_periods = self._build_ownership_periods(reconciled_events)
        
        # Create timeline
        timeline = OwnershipTimeline(
            asset_id=asset_id,
            asset_name=asset_name,
            ownership_periods=ownership_periods,
            all_events=valid_events,
            conflicting_events=conflicts,
            total_ownership_changes=len(reconciled_events)
        )
        
        # Set date bounds
        if valid_events:
            timeline.earliest_date = min(e.event_date for e in valid_events)
            timeline.latest_date = max(e.event_date for e in valid_events)
        
        logger.info(f"Built timeline with {len(ownership_periods)} ownership periods")
        return timeline
    
    def build_timelines_batch(self, session: Session, asset_ids: List[int]) -> Dict[int, OwnershipTimeline]:
        """Build timelines for multiple assets in batch."""
        timelines = {}
        
        for asset_id in asset_ids:
            try:
                timeline = self.build_timeline(session, asset_id)
                timelines[asset_id] = timeline
            except Exception as e:
                logger.error(f"Error building timeline for asset {asset_id}: {e}")
                # Create empty timeline
                timelines[asset_id] = OwnershipTimeline(
                    asset_id=asset_id,
                    asset_name=f"Asset {asset_id}",
                    confidence_gaps=[f"Error building timeline: {e}"]
                )
        
        return timelines
    
    def _extract_patent_assignment_events(self, session: Session, asset_id: int) -> List[OwnershipEvent]:
        """Extract ownership events from patent assignments."""
        events = []
        
        try:
            # Get patents linked to this asset
            query = text("""
                SELECT DISTINCT p.patent_id, p.number, p.earliest_priority_date
                FROM patents p
                JOIN asset_patent_links apl ON p.patent_id = apl.patent_id
                WHERE apl.asset_id = :asset_id
                AND apl.link_confidence > 0.6
            """)
            
            patent_results = session.execute(query, {"asset_id": asset_id}).fetchall()
            
            for patent_id, patent_number, priority_date in patent_results:
                # Get assignments for this patent
                assignments = session.query(PatentAssignment).filter(
                    PatentAssignment.patent_id == patent_id
                ).order_by(PatentAssignment.recorded_date).all()
                
                for assignment in assignments:
                    if not assignment.recorded_date:
                        continue
                    
                    # Resolve assignor and assignee to companies
                    assignor_company = self._resolve_assignee_to_company(session, assignment.assignor)
                    assignee_company = self._resolve_assignee_to_company(session, assignment.assignee)
                    
                    # Calculate confidence based on assignment details
                    confidence = self._calculate_assignment_confidence(assignment)
                    
                    event = OwnershipEvent(
                        event_date=assignment.recorded_date,
                        event_type="patent_assignment",
                        from_company_id=assignor_company[0] if assignor_company else None,
                        from_company_name=assignor_company[1] if assignor_company else assignment.assignor,
                        to_company_id=assignee_company[0] if assignee_company else None,
                        to_company_name=assignee_company[1] if assignee_company else assignment.assignee,
                        ownership_type=self._determine_ownership_type(assignment.type),
                        consideration_amount=assignment.execution_amount,
                        consideration_type=assignment.consideration_type,
                        evidence_source="patent_assignment",
                        evidence_url=assignment.source_url,
                        confidence_score=Decimal(str(confidence)),
                        description=f"Patent assignment {assignment.reel_frame}",
                        source_record_id=str(assignment.assignment_id)
                    )
                    events.append(event)
                    
        except Exception as e:
            logger.error(f"Error extracting patent assignment events for asset {asset_id}: {e}")
        
        return events
    
    def _extract_sec_filing_events(self, session: Session, asset_id: int) -> List[OwnershipEvent]:
        """Extract ownership events from SEC filings."""
        events = []
        
        try:
            # This would integrate with SEC filing extraction
            # For now, check existing asset ownership from assets table
            asset = session.query(Asset).filter(Asset.asset_id == asset_id).first()
            ownership_records = []
            if asset and asset.owner_company_id:
                # Create a simple ownership record from the asset
                ownership_records = [type('OwnershipRecord', (), {
                    'company_id': asset.owner_company_id,
                    'start_date': None,
                    'end_date': None,
                    'source': 'direct_ownership'
                })()]
            
            for record in ownership_records:
                confidence = self.evidence_weights.get("sec_filing", 0.85)
                
                event = OwnershipEvent(
                    event_date=record.start_date or date.today(),
                    event_type="sec_filing",
                    to_company_id=record.company_id,
                    to_company_name=self._get_company_name(session, record.company_id),
                    ownership_type="assignee",  # Default for SEC filings
                    evidence_source="sec_filing",
                    evidence_url=record.evidence_url,
                    confidence_score=Decimal(str(confidence)),
                    description="SEC filing ownership disclosure"
                )
                events.append(event)
                
        except Exception as e:
            logger.error(f"Error extracting SEC filing events for asset {asset_id}: {e}")
        
        return events
    
    def _extract_press_release_events(self, session: Session, asset_id: int) -> List[OwnershipEvent]:
        """Extract ownership events from press releases."""
        events = []
        
        try:
            # This would integrate with press release extraction
            # Look for studies that mention asset transfers
            
            # Get studies related to this asset that mention transfers
            query = text("""
                SELECT s.study_id, s.year, s.url, s.extracted_jsonb, t.sponsor_company_id
                FROM studies s
                LEFT JOIN trials t ON s.trial_id = t.trial_id
                WHERE s.asset_id = :asset_id
                AND s.doc_type = 'PR'
                AND (s.extracted_jsonb->>'description' ILIKE '%acquir%' 
                     OR s.extracted_jsonb->>'description' ILIKE '%licens%'
                     OR s.extracted_jsonb->>'description' ILIKE '%transfer%')
                ORDER BY s.year DESC
            """)
            
            pr_results = session.execute(query, {"asset_id": asset_id}).fetchall()
            
            for study_id, year, url, extracted_data, sponsor_company_id in pr_results:
                if not year:
                    continue
                
                # Extract transfer details from press release
                transfer_details = self._parse_transfer_from_pr(extracted_data or {})
                
                if transfer_details:
                    confidence = self.evidence_weights.get("press_release", 0.75)
                    
                    event = OwnershipEvent(
                        event_date=date(year, 1, 1),  # Approximate date
                        event_type="press_release",
                        to_company_id=sponsor_company_id,
                        to_company_name=self._get_company_name(session, sponsor_company_id) if sponsor_company_id else None,
                        ownership_type=transfer_details.get("type", "assignee"),
                        consideration_amount=transfer_details.get("amount"),
                        evidence_source="press_release",
                        evidence_url=url,
                        confidence_score=Decimal(str(confidence * 0.8)),  # Lower confidence for PR
                        description=transfer_details.get("description", "Press release ownership transfer"),
                        source_record_id=str(study_id)
                    )
                    events.append(event)
                    
        except Exception as e:
            logger.error(f"Error extracting press release events for asset {asset_id}: {e}")
        
        return events
    
    def _extract_trial_sponsor_events(self, session: Session, asset_id: int) -> List[OwnershipEvent]:
        """Extract ownership events from clinical trial sponsor changes."""
        events = []
        
        try:
            # Get trials for this asset
            trials = session.query(Trial).filter(Trial.asset_id == asset_id).all()
            
            for trial in trials:
                if not trial.sponsor_company_id:
                    continue
                
                # Use trial start date as ownership evidence
                trial_date = trial.est_primary_completion_date or date.today()
                
                confidence = self.evidence_weights.get("clinical_trial", 0.60)
                
                event = OwnershipEvent(
                    event_date=trial_date,
                    event_type="clinical_trial",
                    to_company_id=trial.sponsor_company_id,
                    to_company_name=self._get_company_name(session, trial.sponsor_company_id),
                    ownership_type="licensee",  # Trials indicate licensing rights
                    evidence_source="clinical_trial",
                    evidence_url=f"https://clinicaltrials.gov/ct2/show/{trial.nct_id}" if trial.nct_id else None,
                    confidence_score=Decimal(str(confidence)),
                    description=f"Clinical trial sponsorship: {trial.nct_id}",
                    source_record_id=str(trial.trial_id)
                )
                events.append(event)
                
        except Exception as e:
            logger.error(f"Error extracting trial sponsor events for asset {asset_id}: {e}")
        
        return events
    
    def _extract_existing_ownership_events(self, session: Session, asset_id: int) -> List[OwnershipEvent]:
        """Extract events from existing ownership records."""
        events = []
        
        try:
            # Get ownership from assets table
            asset = session.query(Asset).filter(Asset.asset_id == asset_id).first()
            ownership_records = []
            if asset and asset.owner_company_id:
                ownership_records = [type('OwnershipRecord', (), {
                    'company_id': asset.owner_company_id,
                    'start_date': None,
                    'end_date': None,
                    'source': 'direct_ownership'
                })()]
            
            for record in ownership_records:
                if not record.start_date:
                    continue
                
                event = OwnershipEvent(
                    event_date=record.start_date,
                    event_type="existing_record",
                    to_company_id=record.company_id,
                    to_company_name=self._get_company_name(session, record.company_id),
                    ownership_type="assignee",
                    evidence_source=record.source,
                    evidence_url=record.evidence_url,
                    confidence_score=Decimal("0.80"),  # Medium confidence for existing records
                    description="Existing ownership record"
                )
                events.append(event)
                
        except Exception as e:
            logger.error(f"Error extracting existing ownership events for asset {asset_id}: {e}")
        
        return events
    
    def _reconcile_ownership_events(self, events: List[OwnershipEvent]) -> Tuple[List[OwnershipEvent], List[Tuple[OwnershipEvent, OwnershipEvent]]]:
        """Reconcile conflicting ownership events."""
        conflicts = []
        reconciled_events = []
        
        # Group events by date ranges
        for i, event in enumerate(events):
            conflicting_events = []
            
            # Check for conflicts with nearby events
            for j, other_event in enumerate(events):
                if i == j:
                    continue
                
                # Check if events are close in time but have different outcomes
                days_diff = abs((event.event_date - other_event.event_date).days)
                
                if (days_diff <= self.max_consolidation_gap_days and
                    event.to_company_id != other_event.to_company_id and
                    event.to_company_id is not None and other_event.to_company_id is not None):
                    
                    conflicting_events.append(other_event)
            
            if conflicting_events:
                # Choose the highest confidence event
                all_conflicting = [event] + conflicting_events
                best_event = max(all_conflicting, key=lambda e: e.confidence_score)
                
                if best_event not in reconciled_events:
                    reconciled_events.append(best_event)
                
                # Record conflicts
                for conflicting in conflicting_events:
                    if (event, conflicting) not in conflicts and (conflicting, event) not in conflicts:
                        conflicts.append((event, conflicting))
            else:
                reconciled_events.append(event)
        
        # Remove duplicates and sort
        unique_events = []
        seen = set()
        
        for event in reconciled_events:
            key = (event.event_date, event.to_company_id, event.event_type)
            if key not in seen:
                unique_events.append(event)
                seen.add(key)
        
        unique_events.sort(key=lambda e: e.event_date)
        
        return unique_events, conflicts
    
    def _build_ownership_periods(self, events: List[OwnershipEvent]) -> List[OwnershipPeriod]:
        """Build ownership periods from reconciled events."""
        periods = []
        
        if not events:
            return periods
        
        current_period = None
        
        for event in events:
            if not event.to_company_id:
                continue
            
            # End current period if ownership is changing
            if (current_period and 
                current_period.owner_company_id != event.to_company_id):
                current_period.end_date = event.event_date
                periods.append(current_period)
                current_period = None
            
            # Start new period if needed
            if (not current_period or 
                current_period.owner_company_id != event.to_company_id):
                
                current_period = OwnershipPeriod(
                    start_date=event.event_date,
                    end_date=None,  # Open-ended until next change
                    owner_company_id=event.to_company_id,
                    owner_company_name=event.to_company_name or "",
                    ownership_type=event.ownership_type,
                    confidence_score=event.confidence_score
                )
            
            # Add event to period
            current_period.evidence_events.append(event)
            
            # Update confidence (take maximum)
            current_period.confidence_score = max(
                current_period.confidence_score,
                event.confidence_score
            )
        
        # Add final period
        if current_period:
            periods.append(current_period)
        
        return periods
    
    def _get_asset_display_name(self, asset: Asset) -> str:
        """Get display name for asset."""
        names = asset.names_jsonb or {}
        return names.get('inn', '') or names.get('internal_codes', [''])[0] or f"Asset {asset.asset_id}"
    
    def _resolve_assignee_to_company(self, session: Session, assignee_name: str) -> Optional[Tuple[int, str]]:
        """Resolve assignee name to company ID and name."""
        if not assignee_name:
            return None
        
        try:
            # Try exact match first
            company = session.query(Company).filter(
                Company.name.ilike(f"%{assignee_name}%")
            ).first()
            
            if company:
                return (company.company_id, company.name)
                
        except Exception as e:
            logger.debug(f"Error resolving assignee '{assignee_name}': {e}")
        
        return None
    
    def _get_company_name(self, session: Session, company_id: int) -> Optional[str]:
        """Get company name by ID."""
        try:
            company = session.query(Company).filter(Company.company_id == company_id).first()
            return company.name if company else None
        except:
            return None
    
    def _calculate_assignment_confidence(self, assignment: PatentAssignment) -> float:
        """Calculate confidence score for patent assignment."""
        base_confidence = 0.90
        
        # Reduce confidence for old assignments
        if assignment.recorded_date:
            days_old = (date.today() - assignment.recorded_date).days
            if days_old > 3650:  # 10 years
                base_confidence *= 0.8
        
        # Increase confidence if financial details are present
        if assignment.execution_amount:
            base_confidence = min(0.95, base_confidence + 0.05)
        
        # Reduce confidence for unclear assignment types
        if not assignment.type or assignment.type.lower() == "unknown":
            base_confidence *= 0.9
        
        return base_confidence
    
    def _determine_ownership_type(self, assignment_type: str) -> str:
        """Determine ownership type from assignment type."""
        if not assignment_type:
            return "assignee"
        
        assignment_type_lower = assignment_type.lower()
        
        if "license" in assignment_type_lower:
            return "licensee"
        elif "security" in assignment_type_lower:
            return "co_owner"
        else:
            return "assignee"
    
    def _parse_transfer_from_pr(self, extracted_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse transfer details from press release data."""
        description = extracted_data.get('description', '')
        
        if not description:
            return None
        
        transfer_info = {}
        
        # Look for acquisition language
        if any(word in description.lower() for word in ['acquire', 'acquisition', 'purchase']):
            transfer_info['type'] = 'assignee'
        elif any(word in description.lower() for word in ['license', 'licensing']):
            transfer_info['type'] = 'licensee'
        else:
            transfer_info['type'] = 'assignee'
        
        # Try to extract financial amounts
        import re
        money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion))?'
        money_matches = re.findall(money_pattern, description, re.IGNORECASE)
        
        if money_matches:
            try:
                amount_str = money_matches[0].replace('$', '').replace(',', '')
                if 'million' in amount_str.lower():
                    amount_str = amount_str.replace('million', '').strip()
                    amount = Decimal(amount_str) * 1000000
                elif 'billion' in amount_str.lower():
                    amount_str = amount_str.replace('billion', '').strip()
                    amount = Decimal(amount_str) * 1000000000
                else:
                    amount = Decimal(amount_str)
                
                transfer_info['amount'] = amount
            except:
                pass
        
        transfer_info['description'] = description[:200]  # Truncate for storage
        
        return transfer_info
