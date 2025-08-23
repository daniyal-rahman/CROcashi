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
from datetime import datetime, timedelta, date
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

logger = logging.getLogger(__name__)


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
    default_since_days: int = 7
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
        
        # Initialize components
        self.client = CtgovClient(base_url=self.config.api_base_url)
        self.change_detector = CtgovChangeDetector()
        
        # State management
        self.state_file = Path('.state/ctgov_pipeline.json')
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline_state = self._load_pipeline_state()
        
        # Statistics
        self.stats = {
            'trials_processed': 0,
            'trials_updated': 0,
            'trials_new': 0,
            'changes_detected': 0,
            'significant_changes': 0,
            'errors': [],
            'warnings': []
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
        start_time = datetime.utcnow()
        self.logger.info("Starting CT.gov daily ingestion")
        
        try:
            # Determine since date
            since_date = None
            if not force_full_scan and self.config.save_cursor:
                since_date = self._get_last_update_date()
            
            if since_date is None:
                since_date = datetime.utcnow() - timedelta(days=self.config.default_since_days)
            
            self.logger.info(f"Ingesting trials since: {since_date}")
            
            # Run ingestion with proper limiting
            result = self._run_ingestion_with_limits(
                since_date.date(), 
                self.config.max_studies_per_run
            )
            
            # Update cursor
            if self.config.save_cursor and result.success:
                self._update_last_update_date(datetime.utcnow())
            
            # Calculate processing time
            result.processing_time_seconds = (datetime.utcnow() - start_time).total_seconds()
            
            self.logger.info(f"CT.gov ingestion completed: {result.trials_processed} trials processed")
            return result
            
        except Exception as e:
            error_msg = f"Error in daily ingestion: {e}"
            self.logger.error(error_msg)
            
            return IngestionResult(
                success=False,
                errors=[error_msg],
                processing_time_seconds=(datetime.utcnow() - start_time).total_seconds()
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
        start_time = datetime.utcnow()
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
            result.processing_time_seconds = (datetime.utcnow() - start_time).total_seconds()
            
            self.logger.info(f"Limited CT.gov ingestion completed: {result.trials_processed} trials processed")
            return result
            
        except Exception as e:
            error_msg = f"Error in limited ingestion: {e}"
            self.logger.error(error_msg)
            
            return IngestionResult(
                success=False,
                errors=[error_msg],
                processing_time_seconds=(datetime.utcnow() - start_time).total_seconds()
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
                    # Use SAVEPOINT for each trial to isolate failures
                    with session.begin_nested():
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
                            # With SAVEPOINT, the rollback is automatic and only affects this trial
                            nct_id = raw_trial.get('protocolSection', {}).get('identificationModule', {}).get('nctId', 'unknown')
                            error_msg = f"Error processing trial {nct_id}: {e}"
                            self.logger.warning(error_msg)
                            result.errors.append(error_msg)
                            
                            # Log more details about the error
                            import traceback
                            self.logger.exception(f"Per-trial failure for {nct_id}")  # includes stack trace
                            
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
    
    def _extract_comprehensive_trial_fields(self, raw_trial: Dict[str, Any]) -> ComprehensiveTrialFields:
        """Extract comprehensive trial fields from raw CT.gov data as per spec."""
        try:
            protocol = raw_trial.get('protocolSection', {})
            identification = protocol.get('identificationModule', {})
            design = protocol.get('designModule', {})
            status_module = protocol.get('statusModule', {})
            arms_interventions = protocol.get('armsInterventionsModule', {})
            conditions = protocol.get('conditionsModule', {})
            outcomes = protocol.get('outcomesModule', {})
            enrollment = protocol.get('enrollmentModule', {})
            sponsor = protocol.get('sponsorCollaboratorsModule', {})
            
            # Extract sponsor information
            sponsor_info = self._extract_sponsor_info(sponsor)
            
            # Extract trial design
            trial_design = self._extract_trial_design(design)
            
            # Extract interventions
            interventions = self._extract_interventions(arms_interventions)
            
            # Extract conditions
            conditions_list = self._extract_conditions(conditions)
            
            # Extract outcomes
            outcomes_list = self._extract_outcomes(outcomes)
            
            # Extract enrollment info
            enrollment_info = self._extract_enrollment_info(enrollment)
            
            # Extract statistical analysis
            statistical_analysis = self._extract_statistical_analysis(outcomes)
            
            # Extract locations
            locations = self._extract_locations(protocol.get('leadSponsorModule', {}))
            
            # Create comprehensive trial fields
            trial_fields = ComprehensiveTrialFields(
                nct_id=identification.get('nctId', ''),
                brief_title=identification.get('briefTitle'),
                official_title=identification.get('officialTitle'),
                acronym=identification.get('acronym'),
                sponsor_info=sponsor_info,
                study_type=self._extract_study_type(design),
                phase=self._extract_phase_enum(design),
                status=self._extract_status_enum(status_module),
                trial_design=trial_design,
                interventions=interventions,
                conditions=conditions_list,
                outcomes=outcomes_list,
                enrollment_info=enrollment_info,
                statistical_analysis=statistical_analysis,
                locations=locations,
                raw_jsonb=raw_trial
            )
            
            return trial_fields
            
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
    
    def _extract_sponsor_info(self, sponsor_module: Dict[str, Any]) -> SponsorInfo:
        """Extract detailed sponsor information."""
        try:
            lead_sponsor = sponsor_module.get('leadSponsor', {})
            collaborators = sponsor_module.get('collaborators', [])
            responsible_party = sponsor_module.get('responsibleParty', {})
            
            return SponsorInfo(
                lead_sponsor_name=lead_sponsor.get('name'),
                lead_sponsor_cik=lead_sponsor.get('cik'),
                lead_sponsor_lei=lead_sponsor.get('lei'),
                lead_sponsor_country=lead_sponsor.get('country'),
                collaborators=[c.get('name', '') for c in collaborators if c.get('name')],
                responsible_party_name=responsible_party.get('name'),
                responsible_party_type=responsible_party.get('type'),
                agency_class=sponsor_module.get('agencyClass')
            )
        except Exception as e:
            self.logger.warning(f"Error extracting sponsor info: {e}")
            return SponsorInfo()
    
    def _extract_trial_design(self, design_module: Dict[str, Any]) -> TrialDesign:
        """Extract trial design information."""
        try:
            return TrialDesign(
                allocation=design_module.get('allocation'),
                masking=design_module.get('masking'),
                masking_description=design_module.get('maskingDescription'),
                primary_purpose=design_module.get('primaryPurpose'),
                intervention_model=design_module.get('interventionModel'),
                time_perspective=design_module.get('timePerspective'),
                observational_model=design_module.get('observationalModel')
            )
        except Exception as e:
            self.logger.warning(f"Error extracting trial design: {e}")
            return TrialDesign()
    
    def _extract_interventions(self, arms_interventions: Dict[str, Any]) -> List[Intervention]:
        """Extract intervention information."""
        try:
            interventions = []
            for int_data in arms_interventions.get('interventions', []):
                intervention = Intervention(
                    name=int_data.get('name', ''),
                    type=self._extract_intervention_type(int_data.get('type')),
                    description=int_data.get('description'),
                    arm_labels=int_data.get('armLabels', []),
                    other_names=int_data.get('otherNames', []),
                    drug_codes=int_data.get('drugCodes', [])
                )
                interventions.append(intervention)
            return interventions
        except Exception as e:
            self.logger.warning(f"Error extracting interventions: {e}")
            return []
    
    def _extract_conditions(self, conditions_module: Dict[str, Any]) -> List[Condition]:
        """Extract condition information."""
        try:
            conditions = []
            if isinstance(conditions_module, dict):
                for cond_data in conditions_module.get('conditions', []):
                    if isinstance(cond_data, dict):
                        condition = Condition(
                            name=cond_data.get('name', ''),
                            synonyms=cond_data.get('synonyms', [])
                        )
                        conditions.append(condition)
            return conditions
        except Exception as e:
            self.logger.warning(f"Error extracting conditions: {e}")
            return []
    
    def _extract_outcomes(self, outcomes_module: Dict[str, Any]) -> List[Outcome]:
        """Extract outcome information."""
        try:
            outcomes = []
            for outcome_data in outcomes_module.get('outcomes', []):
                outcome = Outcome(
                    name=outcome_data.get('name', ''),
                    type=outcome_data.get('type'),
                    description=outcome_data.get('description'),
                    time_frame=outcome_data.get('timeFrame'),
                    is_primary=outcome_data.get('isPrimary', False)
                )
                outcomes.append(outcome)
            return outcomes
        except Exception as e:
            self.logger.warning(f"Error extracting outcomes: {e}")
            return []
    
    def _extract_enrollment_info(self, enrollment_module: Dict[str, Any]) -> EnrollmentInfo:
        """Extract enrollment information."""
        try:
            if not isinstance(enrollment_module, dict):
                return EnrollmentInfo()
                
            return EnrollmentInfo(
                count=enrollment_module.get('actualEnrollment'),
                type='ACTUAL' if enrollment_module.get('actualEnrollment') else 'ESTIMATED',
                age_min=enrollment_module.get('minimumAge'),
                age_max=enrollment_module.get('maximumAge'),
                sex=enrollment_module.get('sex'),
                healthy_volunteers=enrollment_module.get('healthyVolunteers')
            )
        except Exception as e:
            self.logger.warning(f"Error extracting enrollment info: {e}")
            return EnrollmentInfo()
    
    def _extract_statistical_analysis(self, outcomes_module: Dict[str, Any]) -> StatisticalAnalysis:
        """Extract statistical analysis information."""
        try:
            if not isinstance(outcomes_module, dict):
                return StatisticalAnalysis()
                
            return StatisticalAnalysis(
                statistical_method=outcomes_module.get('statisticalMethod'),
                alpha_level=outcomes_module.get('alphaLevel'),
                power=outcomes_module.get('power'),
                sample_size_calculation=outcomes_module.get('sampleSizeCalculation'),
                interim_analyses=outcomes_module.get('interimAnalyses'),
                multiplicity_adjustment=outcomes_module.get('multiplicityAdjustment')
            )
        except Exception as e:
            self.logger.warning(f"Error extracting statistical analysis: {e}")
            return StatisticalAnalysis()
    
    def _extract_locations(self, lead_sponsor_module: Dict[str, Any]) -> List[Location]:
        """Extract location information."""
        try:
            locations = []
            for loc_data in lead_sponsor_module.get('locations', []):
                location = Location(
                    facility_name=loc_data.get('facility', ''),
                    city=loc_data.get('city'),
                    state=loc_data.get('state'),
                    country=loc_data.get('country'),
                    status=loc_data.get('status')
                )
                locations.append(location)
            return locations
        except Exception as e:
            self.logger.warning(f"Error extracting locations: {e}")
            return []
    
    def _extract_study_type(self, design_module: Dict[str, Any]) -> StudyType:
        """Extract study type."""
        try:
            study_type = design_module.get('studyType', '').upper()
            if study_type == 'INTERVENTIONAL':
                return StudyType.INTERVENTIONAL
            elif study_type == 'OBSERVATIONAL':
                return StudyType.OBSERVATIONAL
            elif study_type == 'EXPANDED_ACCESS':
                return StudyType.EXPANDED_ACCESS
            else:
                return StudyType.INTERVENTIONAL  # Default
        except Exception:
            return StudyType.INTERVENTIONAL
    
    def _extract_phase_enum(self, design_module: Dict[str, Any]) -> TrialPhase:
        """Extract trial phase as enum."""
        try:
            phases = design_module.get('phases', [])
            if phases:
                phase_str = phases[0].upper().replace(' ', '_')
                for phase_enum in TrialPhase:
                    if phase_enum.value == phase_str:
                        return phase_enum
            return TrialPhase.PHASE2  # Default
        except Exception:
            return TrialPhase.PHASE2
    
    def _extract_status_enum(self, status_module: Dict[str, Any]) -> TrialStatus:
        """Extract trial status as enum."""
        try:
            status_str = status_module.get('overallStatus', '').upper().replace(' ', '_')
            for status_enum in TrialStatus:
                if status_enum.value == status_str:
                    return status_enum
            return TrialStatus.UNKNOWN
        except Exception:
            return TrialStatus.UNKNOWN
    
    def _extract_intervention_type(self, type_str: str) -> InterventionType:
        """Extract intervention type as enum."""
        try:
            if type_str:
                type_upper = type_str.upper()
                for int_type in InterventionType:
                    if int_type.value == type_upper:
                        return int_type
            return InterventionType.DRUG  # Default
        except Exception:
            return InterventionType.DRUG
    
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
                    captured_at=datetime.utcnow(),
                    raw_jsonb=raw_data,
                    sha256=sha256_hash,
                    primary_endpoint_text=trial_fields.primary_endpoint_text,
                    sample_size=trial_fields.sample_size,
                    analysis_plan_text=trial_fields.analysis_plan_text,
                    changes_jsonb=changes['changes']
                )
                session.add(new_version)
                
                # Update trial fields
                self._update_trial_fields(existing_trial, trial_fields)
                existing_trial.last_seen_at = datetime.utcnow()
                
                result.trials_updated += 1
                result.changes_detected += len(changes['changes'])
                result.significant_changes += changes.get('significant_change_count', 0)
                
                self.logger.info(f"Updated trial {trial_fields.nct_id}: {len(changes['changes'])} changes")
            else:
                # No changes, just update last seen
                existing_trial.last_seen_at = datetime.utcnow()
                
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
            new_trial = Trial(
                nct_id=trial_fields.nct_id,
                brief_title=trial_fields.brief_title,
                official_title=trial_fields.official_title,
                sponsor_text=trial_fields.sponsor_info.lead_sponsor_name if trial_fields.sponsor_info else None,
                phase=phase_value,
                status=status_value,
                last_seen_at=datetime.utcnow()
            )
            session.add(new_trial)
            session.flush()  # Get trial_id
            
            # Create initial version
            import hashlib
            raw_data = trial_fields.raw_jsonb or {}
            sha256_hash = hashlib.sha256(json.dumps(raw_data, sort_keys=True).encode()).hexdigest()
            
            initial_version = TrialVersion(
                trial_id=new_trial.trial_id,
                captured_at=datetime.utcnow(),
                raw_jsonb=raw_data,
                sha256=sha256_hash,
                primary_endpoint_text=trial_fields.primary_endpoint_text,
                sample_size=trial_fields.sample_size,
                analysis_plan_text=trial_fields.analysis_plan_text,
                changes_jsonb={}
            )
            session.add(initial_version)
            
            result.trials_new += 1
            
            self.logger.info(f"Created new trial {trial_fields.nct_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling trial creation for {trial_fields.nct_id}: {e}")
            raise
    
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
