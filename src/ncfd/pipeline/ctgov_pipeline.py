"""
CT.gov Pipeline for automated trial ingestion and processing.

This module provides:
- Automated CT.gov trial discovery and ingestion with proper limiting
- Comprehensive field extraction as per spec requirements
- Change detection and versioning with full history
- Integration with entity resolution
- Signal evaluation triggering
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
import json
from dataclasses import dataclass, field

from ..ingest.ctgov import CtgovClient
from ..ingest.ctgov_change_detector import CtgovChangeDetector
from ..ingest.ctgov_types import ComprehensiveTrialFields, IngestionResult, SponsorInfo, TrialDesign, Intervention, Condition, Outcome, EnrollmentInfo, StatisticalAnalysis, Location, TrialPhase, TrialStatus, InterventionType, StudyType
from ..db.session import get_session
from ..db.models import Trial, TrialVersion, Company, CtgovIngestState
from ..config import get_config
from .asset_resolver import AssetResolver, AssetMatch
from ..utils.config_manager import get_config_manager
from ..utils.error_handler import get_pipeline_error_handler, handle_database_operation

logger = logging.getLogger(__name__)


@dataclass
class CtgovPipelineOutput:
    """Result of CT.gov pipeline execution."""
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
    # Trial metrics
    trials_processed: int = 0
    trials_created: int = 0
    trials_updated: int = 0
    trials_failed: int = 0
    
    # Change detection metrics
    changes_detected: int = 0
    material_changes: int = 0
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate processing time."""
        if self.end_time and self.start_time:
            self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()


@dataclass
class CtgovPipelineConfig:
    """Configuration for CT.gov pipeline."""
    # API settings
    api_base_url: str = "https://clinicaltrials.gov/api/v2"
    rate_limit_requests_per_minute: int = 300
    timeout_seconds: int = 45
    max_retries: int = 3
    
    # Ingestion settings - FIXED: Proper limiting at source
    batch_size: int = 100
    max_studies_per_run: int = 1000
    default_since_days: int = 1  # Set to 1 day to get September 19th data
    save_cursor: bool = True
    
    # Change detection
    change_detection_enabled: bool = True
    auto_trigger_signals: bool = True
    
    # Quality control
    min_quality_score: float = 0.7
    validation_enabled: bool = True
    
    # NEW: Proper filtering for biotech focus
    focus_phases: List[str] = field(default_factory=lambda: ["PHASE2", "PHASE3", "PHASE2_PHASE3"])
    focus_intervention_types: List[str] = field(default_factory=lambda: ["DRUG", "BIOLOGICAL"])
    focus_study_types: List[str] = field(default_factory=lambda: ["INTERVENTIONAL"])
    
    # Asset resolution
    asset_resolution_enabled: bool = True
    create_new_assets: bool = True
    min_asset_confidence: float = 0.7
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> CtgovPipelineConfig:
        """Create config from dictionary."""
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k)})


class CtgovPipeline:
    """
    CT.gov pipeline for automated trial ingestion and processing.
    
    Features:
    - Automated trial discovery and ingestion with proper limiting
    - Comprehensive field extraction as per spec requirements
    - Change detection between versions with full history
    - Integration with existing database
    - Signal evaluation triggering
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the CT.gov pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = CtgovPipelineConfig.from_dict(config)
        self.logger = logging.getLogger(__name__)
        
        # Initialize centralized utilities
        self.config_manager = get_config_manager()
        self.error_handler = get_pipeline_error_handler('ctgov')
        
        # Initialize components using centralized config
        api_base_url = self.config_manager.get_value('ctgov.api.base_url', self.config.api_base_url)
        self.client = CtgovClient(base_url=api_base_url)
        self.change_detector = CtgovChangeDetector()
        self.asset_resolver = AssetResolver()
        
        # State management
        state_file_path = self.config_manager.get_value('ctgov.state_file', '.state/ctgov_pipeline.json')
        self.state_file = Path(state_file_path)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline_state = self._load_pipeline_state()
        
        # Statistics
        self.stats = {
            'trials_processed': 0,
            'trials_updated': 0,
            'trials_new': 0,
            'changes_detected': 0,
            'significant_changes': 0,
            'assets_resolved': 0,
            'assets_created': 0,
            'trial_asset_links': 0
        }
        
        self.logger.info("CT.gov Pipeline initialized")
    
    def run_daily_ingestion(self, force_full_scan: bool = False) -> IngestionResult:
        """
        Run daily CT.gov ingestion.
        
        Args:
            force_full_scan: If True, ignore cursor and scan all trials
            
        Returns:
            IngestionResult with processing statistics
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info("Starting CT.gov daily ingestion")
        
        try:
            # Determine since date
            since_date = None
            if not force_full_scan and self.config.save_cursor:
                since_date = self._get_last_update_date()
            
            if since_date is None:
                since_date = datetime.now(timezone.utc) - timedelta(days=self.config.default_since_days)
            
            self.logger.info(f"Ingesting trials since: {since_date}")
            
            # Run ingestion with proper limiting
            result = self._run_ingestion_with_limits(
                since_date.date(), 
                self.config.max_studies_per_run
            )
            
            # Update cursor
            if self.config.save_cursor and result.success:
                self._update_last_update_date(datetime.now(timezone.utc))
            
            # Calculate processing time
            result.processing_time_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            self.logger.info(f"CT.gov ingestion completed: {result.trials_processed} trials processed")
            return result
            
        except Exception as e:
            error_msg = f"Error in daily ingestion: {e}"
            self.logger.error(error_msg)
            
            return IngestionResult(
                success=False,
                errors=[error_msg],
                processing_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds()
            )
    
    def run_limited_ingestion(self, 
                             max_studies: int = 3,
                             since_date: Optional[str] = None,
                             phases: Optional[List[str]] = None,
                             statuses: Optional[List[str]] = None) -> IngestionResult:
        """
        Run limited ingestion for testing with proper source limiting.
        
        Args:
            max_studies: Maximum number of studies to process
            since_date: Date string (YYYY-MM-DD) to filter from
            phases: List of trial phases to include
            statuses: List of trial statuses to include
            
        Returns:
            IngestionResult with processing statistics
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info(f"Starting limited CT.gov ingestion: max_studies={max_studies}")
        
        try:
            # Parse since date
            since_date_obj = None
            if since_date:
                since_date_obj = datetime.strptime(since_date, '%Y-%m-%d').date()
            
            # Run ingestion with proper limiting at source
            result = self._run_ingestion_with_limits(
                since_date_obj, 
                max_studies,
                phase_filter=phases,
                status_filter=statuses
            )
            
            # Calculate processing time
            result.processing_time_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            self.logger.info(f"Limited CT.gov ingestion completed: {result.trials_processed} trials processed")
            return result
            
        except Exception as e:
            error_msg = f"Error in limited ingestion: {e}"
            self.logger.error(error_msg)
            
            return IngestionResult(
                success=False,
                errors=[error_msg],
                processing_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds()
            )
    
    def _run_ingestion_with_limits(self, 
                                  since_date: Optional[date] = None,
                                  max_studies: int = 1000,
                                  phase_filter: Optional[List[str]] = None,
                                  status_filter: Optional[List[str]] = None) -> IngestionResult:
        """
        Run the actual ingestion process with proper limiting at source.
        
        Args:
            since_date: Date to filter from
            max_studies: Maximum studies to process
            phase_filter: Phases to include
            status_filter: Statuses to include
            
        Returns:
            IngestionResult with statistics
        """
        result = IngestionResult(success=True)
        
        try:
            with get_session() as session:
                processed_count = 0
                
                # FIXED: Use the focused iterator that limits data at source
                trial_iterator = self._get_limited_trial_iterator(
                    since_date, max_studies, phase_filter, status_filter
                )
                
                for raw_trial in trial_iterator:
                    try:
                        # Extract comprehensive fields as per spec
                        trial_fields = self._extract_comprehensive_trial_fields(raw_trial)
                        
                        # Process trial
                        self._process_trial_robust(session, trial_fields, result)
                        processed_count += 1
                        result.trials_processed += 1
                        
                        # Rate limiting
                        if processed_count % 10 == 0:
                            time.sleep(0.2)  # Brief pause every 10 trials
                        
                        # FIXED: Check limit after processing to ensure we don't exceed
                        if processed_count >= max_studies:
                            self.logger.info(f"Reached limit of {max_studies} studies, stopping ingestion")
                            break
                            
                    except Exception as e:
                        # Use centralized error handling
                        nct_id = raw_trial.get('protocolSection', {}).get('identificationModule', {}).get('nctId', 'unknown')
                        error_result = self.error_handler.handle_trial_error(e, nct_id, {'raw_trial': raw_trial})
                        
                        result.errors.append(error_result.error_message)
                        
                        # Don't continue on critical errors that might corrupt the session
                        if "constraint" in str(e).lower() or "foreign key" in str(e).lower():
                            self.logger.error(f"Critical database error for {nct_id}, stopping ingestion")
                            raise e
                        
                        continue
                
                session.commit()
                self.logger.info(f"Processed {processed_count} trials")
                
        except Exception as e:
            result.success = False
            result.errors.append(f"Ingestion failed: {e}")
            
        return result
    
    def _get_limited_trial_iterator(self, 
                                  since_date: Optional[date] = None,
                                  max_studies: int = 1000,
                                  phase_filter: Optional[List[str]] = None,
                                  status_filter: Optional[List[str]] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Get a limited iterator for trials with proper filtering at source.
        
        This is the key fix: instead of fetching all data and limiting afterward,
        we create a focused iterator that respects the limits.
        """
        # Use the focused study iterator that applies filters at source
        studies_iterator = self.client.iter_studies(
            since=since_date, 
            page_size=min(self.config.batch_size, max_studies)
        )
        
        count = 0
        for study in studies_iterator:
            # Apply additional filters if specified
            if self._passes_additional_filters(study, phase_filter, status_filter):
                yield study
                count += 1
                
                # Stop when we reach the limit
                if count >= max_studies:
                    break
    
    def _passes_additional_filters(self, 
                                 study: Dict[str, Any],
                                 phase_filter: Optional[List[str]] = None,
                                 status_filter: Optional[List[str]] = None) -> bool:
        """Apply additional filters beyond the basic client filters."""
        try:
            # Phase filter
            if phase_filter:
                study_phase = self._extract_phase(study)
                if study_phase and study_phase not in phase_filter:
                    return False
            
            # Status filter
            if status_filter:
                study_status = self._extract_status(study)
                if study_status and study_status not in status_filter:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Error applying additional filters: {e}")
            return True  # Default to including if filter fails
    
    def _extract_comprehensive_trial_fields(self, raw_trial: Dict[str, Any]) -> ComprehensiveTrialFields:
        """Extract comprehensive trial fields from raw CT.gov data using the client."""
        try:
            # Use the client's extraction method instead of duplicating logic
            return self.client.extract_comprehensive_fields(raw_trial)
        except Exception as e:
            self.logger.error(f"Error extracting comprehensive trial fields: {e}")
            # Fallback to basic extraction
            return self._extract_basic_trial_fields(raw_trial)
    
    def _extract_basic_trial_fields(self, raw_trial: Dict[str, Any]) -> ComprehensiveTrialFields:
        """Fallback basic extraction if comprehensive extraction fails."""
        protocol = raw_trial.get('protocolSection', {})
        identification = protocol.get('identificationModule', {})
        
        return ComprehensiveTrialFields(
            nct_id=identification.get('nctId', ''),
            brief_title=identification.get('briefTitle'),
            official_title=identification.get('officialTitle'),
            raw_jsonb=raw_trial
        )
    
    def _extract_phase(self, study: Dict[str, Any]) -> Optional[str]:
        """Extract trial phase from study data."""
        try:
            protocol = study.get('protocolSection', {})
            design = protocol.get('designModule', {})
            phases = design.get('phases', [])
            
            if phases:
                # Return the first phase (usually the primary one)
                return phases[0].upper()
            
            return None
        except Exception:
            return None
    
    def _extract_status(self, study: Dict[str, Any]) -> Optional[str]:
        """Extract trial status from study data."""
        try:
            protocol = study.get('protocolSection', {})
            status_module = protocol.get('statusModule', {})
            overall_status = status_module.get('overallStatus', '')
            
            if overall_status:
                return overall_status.upper().replace(' ', '_')
            
            return None
        except Exception:
            return None
    
    def _passes_filters(self, 
                       trial_fields: ComprehensiveTrialFields,
                       phase_filter: Optional[List[str]] = None,
                       status_filter: Optional[List[str]] = None) -> bool:
        """Check if trial passes the specified filters."""
        # Phase filter
        if phase_filter and trial_fields.phase:
            if trial_fields.phase.value not in phase_filter:
                return False
        
        # Status filter
        if status_filter and trial_fields.status:
            if trial_fields.status.value not in status_filter:
                return False
        
        return True
    
    def _process_trial_robust(self, session, trial_fields: ComprehensiveTrialFields, result: IngestionResult):
        """Process a single trial with robust error handling and proper versioning."""
        try:
            # Check if trial exists
            existing_trial = session.query(Trial).filter(
                Trial.nct_id == trial_fields.nct_id
            ).first()
            
            if existing_trial:
                # Check for changes and create new version if needed
                if self.config.change_detection_enabled:
                    self._handle_trial_update(session, existing_trial, trial_fields, result)
            else:
                # Create new trial with proper versioning
                self._handle_trial_creation(session, trial_fields, result)
                
        except Exception as e:
            raise Exception(f"Error processing trial {trial_fields.nct_id}: {e}")
    
    def _handle_trial_update(self, session, existing_trial: Trial, trial_fields: ComprehensiveTrialFields, result: IngestionResult):
        """Handle updating an existing trial with change detection."""
        try:
            # Get the latest version data for comparison
            latest_version = session.query(TrialVersion).filter(
                TrialVersion.trial_id == existing_trial.trial_id
            ).order_by(TrialVersion.trial_version_id.desc()).first()
            
            latest_data = latest_version.raw_jsonb if latest_version else {}
            
            # Detect changes using simple JSON comparison
            changes = self._detect_simple_changes(
                latest_data,
                trial_fields.raw_jsonb or {}
            )
            
            if changes.get('changes') and changes['changes']:
                # Create new version
                import hashlib
                raw_data = trial_fields.raw_jsonb or {}
                sha256_hash = hashlib.sha256(json.dumps(raw_data, sort_keys=True).encode()).hexdigest()
                
                new_version = TrialVersion(
                    trial_id=existing_trial.trial_id,
                    captured_at=datetime.now(timezone.utc),
                    raw_jsonb=raw_data,
                    sha256=sha256_hash,
                    primary_endpoint_text=trial_fields.primary_endpoint_text,
                    sample_size=trial_fields.sample_size,
                    analysis_plan_text=trial_fields.analysis_plan_text,
                    changes=changes['changes']
                )
                session.add(new_version)
                
                # Update trial fields
                self._update_trial_fields(existing_trial, trial_fields)
                existing_trial.last_seen_at = datetime.now(timezone.utc)
                
                # Handle asset resolution for updated trials
                if self.config.asset_resolution_enabled:
                    self._handle_asset_resolution(session, existing_trial, trial_fields, result)
                
                result.trials_updated += 1
                result.changes_detected += len(changes['changes'])
                result.significant_changes += changes.get('significant_change_count', 0)
                
                self.logger.info(f"Updated trial {trial_fields.nct_id}: {len(changes['changes'])} changes")
            else:
                # No changes, just update last seen
                existing_trial.last_seen_at = datetime.now(timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Error handling trial update for {trial_fields.nct_id}: {e}")
            raise
    
    def _handle_trial_creation(self, session, trial_fields: ComprehensiveTrialFields, result: IngestionResult):
        """Handle creating a new trial with proper versioning."""
        try:
            # Validate required fields
            if not trial_fields.nct_id:
                raise ValueError("NCT ID is required")
            
            # Extract phase and status safely
            phase_value = None
            if trial_fields.phase:
                try:
                    phase_value = trial_fields.phase.value
                except AttributeError:
                    self.logger.warning(f"Phase field is not an enum: {type(trial_fields.phase)}")
                    phase_value = str(trial_fields.phase) if trial_fields.phase else None
            
            status_value = None
            if trial_fields.status:
                try:
                    status_value = trial_fields.status.value
                except AttributeError:
                    self.logger.warning(f"Status field is not an enum: {type(trial_fields.status)}")
                    status_value = str(trial_fields.status) if trial_fields.status else None
            
            # Create new trial
            import hashlib
            raw_data = trial_fields.raw_jsonb or {}
            sha256_hash = hashlib.sha256(json.dumps(raw_data, sort_keys=True).encode()).hexdigest()
            
            new_trial = Trial(
                nct_id=trial_fields.nct_id,
                brief_title=trial_fields.brief_title,
                official_title=trial_fields.official_title,
                sponsor_text=trial_fields.sponsor_info.lead_sponsor_name if trial_fields.sponsor_info else None,
                phase=phase_value,
                status=status_value,
                est_primary_completion_date=trial_fields.primary_completion_date,
                last_seen_at=datetime.now(timezone.utc),
                current_sha256=sha256_hash,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(new_trial)
            session.flush()  # Get trial_id

                        # Attempt to resolve sponsor to a company and wire to SEC data
            try:
                sponsor_name = trial_fields.sponsor_info.lead_sponsor_name if trial_fields.sponsor_info else None
                if sponsor_name:
                    from ncfd.mapping.simple_resolver import resolve_sponsor_simple
                    
                    sponsor_result = resolve_sponsor_simple(session, new_trial.nct_id, sponsor_name)
                    if sponsor_result.company_id and sponsor_result.confidence >= 0.8:
                        new_trial.sponsor_company_id = sponsor_result.company_id
                        logger.info(f"Resolved sponsor '{sponsor_name}' to company {sponsor_result.company_id} ({sponsor_result.match_method})")
            except Exception as _e:
                # Non-fatal; keep ingestion robust
                self.logger.warning(f"Sponsor resolution failed for {trial_fields.nct_id}: {_e}")
            
            # Create initial version
            
            initial_version = TrialVersion(
                trial_id=new_trial.trial_id,
                captured_at=datetime.now(timezone.utc),
                raw_jsonb=raw_data,
                sha256=sha256_hash,
                primary_endpoint_text=trial_fields.primary_endpoint_text,
                sample_size=trial_fields.sample_size,
                analysis_plan_text=trial_fields.analysis_plan_text,
                changes={}
            )
            session.add(initial_version)
            
            # Handle asset resolution for new trials
            if self.config.asset_resolution_enabled:
                self._handle_asset_resolution(session, new_trial, trial_fields, result)
            
            result.trials_new += 1
            
            self.logger.info(f"Created new trial {trial_fields.nct_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling trial creation for {trial_fields.nct_id}: {e}")
            raise
    
    def _handle_asset_resolution(self, session, trial: Trial, trial_fields: ComprehensiveTrialFields, result: IngestionResult):
        """Handle asset resolution for a trial."""
        try:
            # Extract drug names from trial data
            drug_names = self.asset_resolver.extract_drug_names(trial_fields.raw_jsonb or {})
            
            if not drug_names:
                return
            
            # Resolve to existing assets
            asset_matches = self.asset_resolver.resolve_assets(
                session, drug_names, trial.sponsor_company_id
            )
            
            # Create new assets if enabled and needed
            if self.config.create_new_assets:
                for drug_name in drug_names:
                    if drug_name.confidence >= self.config.min_asset_confidence:
                        new_asset_id = self.asset_resolver.create_asset_if_needed(session, drug_name)
                        if new_asset_id:
                            # Add to matches if not already matched
                            if not any(match.asset_id == new_asset_id for match in asset_matches):
                                asset_matches.append(AssetMatch(
                                    asset_id=new_asset_id,
                                    confidence=drug_name.confidence * 0.9,  # Slight penalty for new asset
                                    match_type='new_asset',
                                    matched_alias=drug_name.normalized,
                                    heuristics={'method': 'new_asset_creation'}
                                ))
                            result.assets_created += 1
            
            # Link trial to assets
            if asset_matches:
                self.asset_resolver.link_trial_to_assets(
                    session, trial.trial_id, trial.nct_id, asset_matches
                )
                result.assets_resolved += len(set(match.asset_id for match in asset_matches))
                result.trial_asset_links += len(asset_matches)
                
                self.logger.info(f"Resolved {len(asset_matches)} assets for trial {trial.nct_id}")
            
        except Exception as e:
            self.logger.warning(f"Asset resolution failed for trial {trial.nct_id}: {e}")
            # Non-fatal; don't fail the entire trial processing
    
    def _detect_simple_changes(self, old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple change detection for raw JSON data.
        
        Args:
            old_data: Previous version data
            new_data: Current version data
            
        Returns:
            Dictionary with change information
        """
        try:
            changes = {}
            significant_changes = []
            
            # Simple comparison of key fields
            key_fields = [
                'briefTitle', 'officialTitle', 'phase', 'status', 
                'sampleSize', 'primaryEndpoint', 'analysisPlan'
            ]
            
            for field in key_fields:
                old_value = self._get_nested_value(old_data, field)
                new_value = self._get_nested_value(new_data, field)
                
                if old_value != new_value:
                    changes[field] = {
                        'old': old_value,
                        'new': new_value,
                        'changed': True
                    }
                    
                    # Mark certain fields as significant
                    if field in ['phase', 'status', 'sampleSize', 'primaryEndpoint']:
                        significant_changes.append(field)
            
            return {
                'changes': changes,
                'significant_changes': significant_changes,
                'significant_change_count': len(significant_changes),
                'change_count': len(changes)
            }
            
        except Exception as e:
            self.logger.warning(f"Error in simple change detection: {e}")
            return {
                'changes': {},
                'significant_changes': [],
                'significant_change_count': 0,
                'change_count': 0
            }
    
    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get nested value from JSON data using dot notation."""
        try:
            if not isinstance(data, dict):
                return None
                
            # Handle nested paths like 'protocolSection.identificationModule.nctId'
            parts = field_path.split('.')
            current = data
            
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            
            return current
        except Exception:
            return None
    
    def _update_trial_fields(self, trial: Trial, trial_fields: ComprehensiveTrialFields):
        """Update trial fields with new data."""
        if trial_fields.brief_title:
            trial.brief_title = trial_fields.brief_title
        if trial_fields.official_title:
            trial.official_title = trial_fields.official_title
        if trial_fields.sponsor_info and trial_fields.sponsor_info.lead_sponsor_name:
            trial.sponsor_text = trial_fields.sponsor_info.lead_sponsor_name
        if trial_fields.phase:
            # Safe enum value extraction
            trial.phase = getattr(trial_fields.phase, "value", str(trial_fields.phase))
        if trial_fields.status:
            # Safe enum value extraction
            trial.status = getattr(trial_fields.status, "value", str(trial_fields.status))
    
    def _load_pipeline_state(self) -> Dict[str, Any]:
        """Load pipeline state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Error loading pipeline state: {e}")
        return {}
    
    def _save_pipeline_state(self):
        """Save pipeline state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.pipeline_state, f, indent=2, default=str)
        except Exception as e:
            self.logger.warning(f"Error saving pipeline state: {e}")
    
    def _get_last_update_date(self) -> Optional[datetime]:
        """Get the last update date from state."""
        last_update = self.pipeline_state.get('last_update_date')
        if last_update:
            try:
                return datetime.fromisoformat(last_update)
            except Exception:
                pass
        return None
    
    def _update_last_update_date(self, update_date: datetime):
        """Update the last update date in state."""
        self.pipeline_state['last_update_date'] = update_date.isoformat()
        self._save_pipeline_state()
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status for orchestrator."""
        return {
            'status': 'ready' if self.pipeline_state else 'not_started',
            'last_update_date': self.pipeline_state.get('last_update_date'),
            'trials_processed': self.stats.get('trials_processed', 0),
            'trials_updated': self.stats.get('trials_updated', 0),
            'trials_new': self.stats.get('trials_new', 0),
            'state_file': str(self.state_file)
        }
