"""
USPTO Patent Data Processing Pipeline

Orchestrates the complete patent data processing workflow:
1. Patent and assignment data ingestion
2. Company resolution for assignees
3. Asset-patent linking
4. Ownership timeline reconstruction
5. Database storage and validation

Integrates all USPTO components into a cohesive processing pipeline.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import text

from .patent_client import USPTOPatentClient
from .assignment_client import USPTOAssignmentClient
from .patent_types import PatentRecord, AssignmentRecord, IngestionResult
from ..sec import ingest_sec_rows
from ...db.models import Patent, PatentAssignment, Company, Asset, AssetPatentLink, OwnershipSnapshot
from ...db.session import get_session
from ...mapping.patent_assignee_resolver import PatentAssigneeResolver
from ...mapping.asset_patent_linker import AssetPatentLinker
from ...mapping.ownership_timeline import OwnershipTimelineBuilder

logger = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """Statistics from patent processing operation."""
    
    # Patent processing
    patents_fetched: int = 0
    patents_stored: int = 0
    patents_updated: int = 0
    patents_failed: int = 0
    
    # Assignment processing
    assignments_fetched: int = 0
    assignments_stored: int = 0
    assignments_failed: int = 0
    
    # Company resolution
    assignees_processed: int = 0
    assignees_resolved: int = 0
    assignees_unresolved: int = 0
    
    # Asset linking
    assets_processed: int = 0
    patent_links_created: int = 0
    high_confidence_links: int = 0
    
    # Ownership timelines
    timelines_built: int = 0
    ownership_snapshots_created: int = 0
    
    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def finalize(self):
        """Finalize processing stats."""
        self.end_time = datetime.now(UTC)
        if self.start_time:
            self.total_duration_seconds = (self.end_time - self.start_time).total_seconds()
    
    @property
    def patent_success_rate(self) -> float:
        """Calculate patent processing success rate."""
        total = self.patents_fetched
        successful = self.patents_stored + self.patents_updated
        return successful / total if total > 0 else 0.0
    
    @property
    def resolution_rate(self) -> float:
        """Calculate assignee resolution rate."""
        total = self.assignees_processed
        resolved = self.assignees_resolved
        return resolved / total if total > 0 else 0.0


class PatentProcessor:
    """
    Main processor for USPTO patent data.
    
    Coordinates the complete pipeline from raw patent data to ownership timelines.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize patent processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Initialize clients
        self.patent_client = USPTOPatentClient(self.config.get("uspto", {}))
        self.assignment_client = USPTOAssignmentClient(self.config.get("uspto", {}))
        
        # Initialize processors
        self.assignee_resolver = PatentAssigneeResolver(self.config.get("assignment_processing", {}))
        self.asset_linker = AssetPatentLinker(self.config.get("asset_patent_linking", {}))
        self.timeline_builder = OwnershipTimelineBuilder(self.config.get("ownership_timeline", {}))
        
        # Processing settings
        self.batch_size = self.config.get("pipeline", {}).get("batch_processing", {}).get("chunk_size", 100)
        self.max_retries = self.config.get("pipeline", {}).get("batch_processing", {}).get("max_retries", 3)
        
        logger.info("Initialized patent processor")
    
    def process_patents_for_companies(self, session: Session, 
                                    company_ids: List[int],
                                    since_date: Optional[date] = None) -> ProcessingStats:
        """
        Process patents for specific companies.
        
        Args:
            session: Database session
            company_ids: List of company IDs to process patents for
            since_date: Only process patents since this date
            
        Returns:
            Processing statistics
        """
        logger.info(f"Processing patents for {len(company_ids)} companies")
        
        stats = ProcessingStats()
        
        try:
            for company_id in company_ids:
                logger.info(f"Processing patents for company {company_id}")
                
                # Get company info
                company = session.query(Company).filter(Company.company_id == company_id).first()
                if not company:
                    stats.warnings.append(f"Company {company_id} not found")
                    continue
                
                # Process patents for this company
                company_stats = self._process_company_patents(session, company, since_date)
                self._merge_stats(stats, company_stats)
                
                # Commit after each company
                session.commit()
                
        except Exception as e:
            logger.error(f"Error processing patents for companies: {e}")
            stats.errors.append(str(e))
            session.rollback()
        
        stats.finalize()
        logger.info(f"Completed patent processing. Success rate: {stats.patent_success_rate:.2%}")
        
        return stats
    
    def process_pharmaceutical_patents(self, session: Session,
                                     since_date: Optional[date] = None,
                                     max_patents: int = 5000) -> ProcessingStats:
        """
        Process recent pharmaceutical patents.
        
        Args:
            session: Database session
            since_date: Only process patents since this date
            max_patents: Maximum number of patents to process
            
        Returns:
            Processing statistics
        """
        logger.info(f"Processing pharmaceutical patents since {since_date}")
        
        stats = ProcessingStats()
        
        try:
            # Fetch pharmaceutical patents
            patents = self.patent_client.fetch_pharmaceutical_patents(since_date, max_patents)
            stats.patents_fetched = len(patents)
            
            logger.info(f"Fetched {len(patents)} pharmaceutical patents")
            
            # Process patents in batches
            for i in range(0, len(patents), self.batch_size):
                batch = patents[i:i + self.batch_size]
                logger.debug(f"Processing patent batch {i//self.batch_size + 1}")
                
                batch_stats = self._process_patent_batch(session, batch)
                self._merge_stats(stats, batch_stats)
                
                # Commit after each batch
                session.commit()
                
        except Exception as e:
            logger.error(f"Error processing pharmaceutical patents: {e}")
            stats.errors.append(str(e))
            session.rollback()
        
        stats.finalize()
        return stats
    
    def rebuild_asset_patent_links(self, session: Session, 
                                 asset_ids: Optional[List[int]] = None) -> ProcessingStats:
        """
        Rebuild asset-patent links for all or specific assets.
        
        Args:
            session: Database session
            asset_ids: Specific asset IDs to process, or None for all
            
        Returns:
            Processing statistics
        """
        logger.info("Rebuilding asset-patent links")
        
        stats = ProcessingStats()
        
        try:
            # Get assets to process
            if asset_ids:
                assets = session.query(Asset).filter(Asset.asset_id.in_(asset_ids)).all()
            else:
                assets = session.query(Asset).all()
            
            stats.assets_processed = len(assets)
            logger.info(f"Processing {len(assets)} assets")
            
            # Process assets in batches
            for i in range(0, len(assets), self.batch_size):
                batch = assets[i:i + self.batch_size]
                
                for asset in batch:
                    try:
                        # Remove existing links
                        session.query(AssetPatentLink).filter(
                            AssetPatentLink.asset_id == asset.asset_id
                        ).delete()
                        
                        # Create new links
                        links = self.asset_linker.link_asset_to_patents(session, asset.asset_id)
                        
                        # Store links
                        for link in links:
                            if link.is_acceptable:
                                db_link = AssetPatentLink(
                                    asset_id=link.asset_id,
                                    patent_id=link.patent_id,
                                    link_confidence=link.confidence_score,
                                    link_method=link.link_method,
                                    evidence_spans=link.evidence_spans,
                                    created_at=datetime.now(UTC)
                                )
                                session.add(db_link)
                                
                                stats.patent_links_created += 1
                                if link.is_high_confidence:
                                    stats.high_confidence_links += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing asset {asset.asset_id}: {e}")
                        stats.errors.append(f"Asset {asset.asset_id}: {e}")
                
                # Commit after each batch
                session.commit()
                
        except Exception as e:
            logger.error(f"Error rebuilding asset-patent links: {e}")
            stats.errors.append(str(e))
            session.rollback()
        
        stats.finalize()
        return stats
    
    def rebuild_ownership_timelines(self, session: Session,
                                  asset_ids: Optional[List[int]] = None) -> ProcessingStats:
        """
        Rebuild ownership timelines for all or specific assets.
        
        Args:
            session: Database session
            asset_ids: Specific asset IDs to process, or None for all
            
        Returns:
            Processing statistics
        """
        logger.info("Rebuilding ownership timelines")
        
        stats = ProcessingStats()
        
        try:
            # Get assets with patent links
            if asset_ids:
                query = text("""
                    SELECT DISTINCT asset_id 
                    FROM asset_patent_links 
                    WHERE asset_id = ANY(:asset_ids)
                """)
                asset_ids_with_patents = [row[0] for row in session.execute(query, {"asset_ids": asset_ids}).fetchall()]
            else:
                query = text("SELECT DISTINCT asset_id FROM asset_patent_links")
                asset_ids_with_patents = [row[0] for row in session.execute(query).fetchall()]
            
            logger.info(f"Building timelines for {len(asset_ids_with_patents)} assets")
            
            for asset_id in asset_ids_with_patents:
                try:
                    # Build timeline
                    timeline = self.timeline_builder.build_timeline(session, asset_id)
                    stats.timelines_built += 1
                    
                    # Clear existing ownership snapshots
                    session.query(OwnershipSnapshot).filter(
                        OwnershipSnapshot.asset_id == asset_id
                    ).delete()
                    
                    # Create new ownership snapshots
                    for period in timeline.ownership_periods:
                        snapshot = OwnershipSnapshot(
                            asset_id=asset_id,
                            as_of_date=period.start_date,
                            owner_company_id=period.owner_company_id,
                            ownership_type=period.ownership_type,
                            ownership_percentage=period.ownership_percentage,
                            evidence_source="patent_assignment",
                            confidence_score=period.confidence_score,
                            created_at=datetime.now(UTC)
                        )
                        session.add(snapshot)
                        stats.ownership_snapshots_created += 1
                    
                    # Add current ownership snapshot if different
                    current_owner = timeline.get_current_owner()
                    if current_owner:
                        current_snapshot = OwnershipSnapshot(
                            asset_id=asset_id,
                            as_of_date=date.today(),
                            owner_company_id=current_owner.owner_company_id,
                            ownership_type=current_owner.ownership_type,
                            ownership_percentage=current_owner.ownership_percentage,
                            evidence_source="current_analysis",
                            confidence_score=current_owner.confidence_score,
                            created_at=datetime.now(UTC)
                        )
                        session.add(current_snapshot)
                        stats.ownership_snapshots_created += 1
                    
                except Exception as e:
                    logger.error(f"Error building timeline for asset {asset_id}: {e}")
                    stats.errors.append(f"Asset {asset_id}: {e}")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error rebuilding ownership timelines: {e}")
            stats.errors.append(str(e))
            session.rollback()
        
        stats.finalize()
        return stats
    
    def _process_company_patents(self, session: Session, company: Company, 
                               since_date: Optional[date]) -> ProcessingStats:
        """Process patents for a specific company."""
        stats = ProcessingStats()
        
        try:
            # Fetch patents for company
            patents = self.patent_client.fetch_patents_by_assignee(
                company.name, since_date, max_patents=1000
            )
            stats.patents_fetched = len(patents)
            
            if not patents:
                logger.debug(f"No patents found for company {company.name}")
                return stats
            
            # Process patents
            batch_stats = self._process_patent_batch(session, patents)
            self._merge_stats(stats, batch_stats)
            
            # Fetch and process assignments
            for patent in patents:
                try:
                    assignments = self.assignment_client.fetch_assignments_for_patent(patent.patent_number)
                    stats.assignments_fetched += len(assignments)
                    
                    assignment_stats = self._process_assignment_batch(session, assignments)
                    self._merge_stats(stats, assignment_stats)
                    
                except Exception as e:
                    logger.warning(f"Error fetching assignments for patent {patent.patent_number}: {e}")
                    stats.warnings.append(f"Patent {patent.patent_number}: {e}")
            
        except Exception as e:
            logger.error(f"Error processing patents for company {company.name}: {e}")
            stats.errors.append(str(e))
        
        return stats
    
    def _process_patent_batch(self, session: Session, patents: List[PatentRecord]) -> ProcessingStats:
        """Process a batch of patents."""
        stats = ProcessingStats()
        
        for patent in patents:
            try:
                # Check if patent already exists
                existing = session.query(Patent).filter(
                    Patent.number == patent.patent_number
                ).first()
                
                if existing:
                    # Update existing patent
                    self._update_patent_record(existing, patent)
                    stats.patents_updated += 1
                else:
                    # Create new patent
                    db_patent = self._create_patent_record(patent)
                    session.add(db_patent)
                    stats.patents_stored += 1
                
            except Exception as e:
                logger.error(f"Error processing patent {patent.patent_number}: {e}")
                stats.patents_failed += 1
                stats.errors.append(f"Patent {patent.patent_number}: {e}")
        
        return stats
    
    def _process_assignment_batch(self, session: Session, assignments: List[AssignmentRecord]) -> ProcessingStats:
        """Process a batch of assignments."""
        stats = ProcessingStats()
        
        for assignment in assignments:
            try:
                # Resolve assignor and assignee to companies
                assignor_resolution = self.assignee_resolver.resolve_assignee(session, assignment.assignor)
                assignee_resolution = self.assignee_resolver.resolve_assignee(session, assignment.assignee)
                
                stats.assignees_processed += 2
                if assignor_resolution.is_resolved:
                    stats.assignees_resolved += 1
                else:
                    stats.assignees_unresolved += 1
                
                if assignee_resolution.is_resolved:
                    stats.assignees_resolved += 1
                else:
                    stats.assignees_unresolved += 1
                
                # Get or create patent records for this assignment
                patent_ids = []
                for patent_number in assignment.patent_numbers:
                    patent = session.query(Patent).filter(Patent.number == patent_number).first()
                    if patent:
                        patent_ids.append(patent.patent_id)
                
                # Create assignment records
                for patent_id in patent_ids:
                    db_assignment = PatentAssignment(
                        patent_id=patent_id,
                        assignor=assignment.assignor,
                        assignee=assignment.assignee,
                        execution_date=assignment.execution_date,
                        recorded_date=assignment.recorded_date,
                        type=assignment.assignment_type,
                        assignment_type_detail=assignment.assignment_type,
                        execution_amount=assignment.consideration_amount,
                        consideration_type=assignment.consideration_type,
                        assignment_text=assignment.assignment_text,
                        parsed_metadata={
                            "assignor_resolution": assignor_resolution.__dict__ if assignor_resolution else None,
                            "assignee_resolution": assignee_resolution.__dict__ if assignee_resolution else None
                        },
                        source_url=assignment.source_url,
                        created_at=datetime.now(UTC)
                    )
                    session.add(db_assignment)
                    stats.assignments_stored += 1
                
            except Exception as e:
                logger.error(f"Error processing assignment {assignment.assignment_id}: {e}")
                stats.assignments_failed += 1
                stats.errors.append(f"Assignment {assignment.assignment_id}: {e}")
        
        return stats
    
    def _create_patent_record(self, patent: PatentRecord) -> Patent:
        """Create database patent record from PatentRecord."""
        return Patent(
            number=patent.patent_number,
            family_id=patent.family_id,
            jurisdiction="US",
            earliest_priority_date=patent.priority_date,
            status=patent.patent_status,
            assignees=patent.assignees,
            inventors=patent.inventors,
            links_jsonb={
                "title": patent.title,
                "abstract": patent.abstract,
                "application_date": patent.application_date.isoformat() if patent.application_date else None,
                "grant_date": patent.grant_date.isoformat() if patent.grant_date else None,
                "cpc_classes": patent.cpc_classes,
                "uspc_classes": patent.uspc_classes,
                "source_url": patent.source_url,
                "is_pharmaceutical": patent.is_pharmaceutical
            },
            created_at=datetime.now(UTC)
        )
    
    def _update_patent_record(self, existing: Patent, patent: PatentRecord):
        """Update existing patent record with new data."""
        # Update fields that might have changed
        existing.status = patent.patent_status
        existing.assignees = patent.assignees
        existing.inventors = patent.inventors
        
        # Update JSONB links with new information
        links = existing.links_jsonb or {}
        links.update({
            "title": patent.title,
            "abstract": patent.abstract,
            "last_updated": datetime.now(UTC).isoformat(),
            "is_pharmaceutical": patent.is_pharmaceutical
        })
        existing.links_jsonb = links
    
    def _merge_stats(self, target: ProcessingStats, source: ProcessingStats):
        """Merge processing statistics."""
        target.patents_fetched += source.patents_fetched
        target.patents_stored += source.patents_stored
        target.patents_updated += source.patents_updated
        target.patents_failed += source.patents_failed
        
        target.assignments_fetched += source.assignments_fetched
        target.assignments_stored += source.assignments_stored
        target.assignments_failed += source.assignments_failed
        
        target.assignees_processed += source.assignees_processed
        target.assignees_resolved += source.assignees_resolved
        target.assignees_unresolved += source.assignees_unresolved
        
        target.assets_processed += source.assets_processed
        target.patent_links_created += source.patent_links_created
        target.high_confidence_links += source.high_confidence_links
        
        target.timelines_built += source.timelines_built
        target.ownership_snapshots_created += source.ownership_snapshots_created
        
        target.errors.extend(source.errors)
        target.warnings.extend(source.warnings)
    
    def get_processing_summary(self, stats: ProcessingStats) -> Dict[str, Any]:
        """Get human-readable processing summary."""
        return {
            "patent_processing": {
                "fetched": stats.patents_fetched,
                "stored": stats.patents_stored,
                "updated": stats.patents_updated,
                "failed": stats.patents_failed,
                "success_rate": f"{stats.patent_success_rate:.1%}"
            },
            "assignment_processing": {
                "fetched": stats.assignments_fetched,
                "stored": stats.assignments_stored,
                "failed": stats.assignments_failed
            },
            "company_resolution": {
                "processed": stats.assignees_processed,
                "resolved": stats.assignees_resolved,
                "unresolved": stats.assignees_unresolved,
                "resolution_rate": f"{stats.resolution_rate:.1%}"
            },
            "asset_linking": {
                "assets_processed": stats.assets_processed,
                "links_created": stats.patent_links_created,
                "high_confidence_links": stats.high_confidence_links
            },
            "ownership_timelines": {
                "timelines_built": stats.timelines_built,
                "snapshots_created": stats.ownership_snapshots_created
            },
            "performance": {
                "duration_seconds": stats.total_duration_seconds,
                "duration_minutes": stats.total_duration_seconds / 60 if stats.total_duration_seconds else None
            },
            "issues": {
                "errors": len(stats.errors),
                "warnings": len(stats.warnings),
                "error_details": stats.errors[:10],  # First 10 errors
                "warning_details": stats.warnings[:10]  # First 10 warnings
            }
        }
