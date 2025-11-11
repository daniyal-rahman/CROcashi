"""
Company risk analysis service for calculating risk scores and metrics.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import func, case, and_, or_
from sqlalchemy.orm import Session

from database.models.entities import Company
from database.models.clinical import ClinicalTrial
from database.models.relationships import (
    TrialSponsor, PublicationTrial, PublicationDrug, PublicationCompany,
    FilingDrug, CompanyDrug
)
from database.models.events import Event
from src.models.clinical_constants import TrialStatus
from src.services.cache_config import CacheTTL
from src.services.failure_analysis_service import FailureAnalysisService
from src.services.failure_tracker import FailureTracker

logger = logging.getLogger(__name__)


class CompanyRiskService:
    """
    Service for calculating company risk scores and metrics.
    
    Provides company-specific risk analysis including:
    - Risk score calculation (0-100)
    - Pipeline metrics
    - Failure rates by phase
    - Timeline analysis
    - Warning signal detection
    """
    
    # Risk score component weights
    FAILURE_RATE_WEIGHT = 40
    RECENT_FAILURES_WEIGHT = 30
    PIPELINE_STAGNATION_WEIGHT = 20
    WARNING_SIGNALS_WEIGHT = 10
    
    # Risk categories
    RISK_CATEGORIES = {
        'LOW': (0, 25),
        'MODERATE': (25, 50),
        'HIGH': (50, 75),
        'CRITICAL': (75, 100)
    }
    
    def __init__(self, session: Session, cache=None):
        """
        Initialize company risk service.
        
        Args:
            session: SQLAlchemy database session
            cache: Optional Redis cache client (if None, will use get_cache())
        """
        from src.services.cache import get_cache
        self.session = session
        self.cache = cache if cache is not None else get_cache()
        self.failure_service = FailureAnalysisService(session)
        self.failure_tracker = FailureTracker(session)
    
    def get_company_metrics(self, company_id: UUID) -> Dict[str, Any]:
        """
        Calculate all metrics for a company.
        
        Args:
            company_id: Company UUID
            
        Returns:
            Dictionary with all company metrics
        """
        try:
            # Check cache first
            cache_key = f"company_metrics:{company_id}"
            if self.cache:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            
            # Get company
            company = self.session.query(Company).filter(
                Company.company_id == company_id,
                Company.deleted_at.is_(None)
            ).first()
            
            if not company:
                return {
                    'company_id': str(company_id),
                    'error': 'Company not found'
                }
            
            # Get all trials for this company
            trials_query = self.session.query(ClinicalTrial).join(
                TrialSponsor,
                ClinicalTrial.trial_id == TrialSponsor.trial_id
            ).filter(
                TrialSponsor.entity_id == company_id,
                TrialSponsor.entity_type == 'company',
                TrialSponsor.deleted_at.is_(None),
                ClinicalTrial.deleted_at.is_(None)
            )
            
            all_trials = trials_query.all()
            
            # Calculate metrics
            total_trials = len(all_trials)
            
            # Active trials
            active_trials = [t for t in all_trials if t.status in TrialStatus.ACTIVE_STATUSES]
            active_count = len(active_trials)
            
            # Failed trials
            failed_trials = [t for t in all_trials if t.status in TrialStatus.FAILED_STATUSES]
            terminated_count = len(failed_trials)
            
            # Calculate success rates by phase
            phase_1_trials = [t for t in all_trials if t.phase_numeric == 1]
            phase_2_trials = [t for t in all_trials if t.phase_numeric == 2]
            phase_3_trials = [t for t in all_trials if t.phase_numeric == 3]
            
            phase_1_success_rate = self._calculate_phase_success_rate(phase_1_trials)
            phase_2_success_rate = self._calculate_phase_success_rate(phase_2_trials)
            phase_3_success_rate = self._calculate_phase_success_rate(phase_3_trials)
            
            # Calculate pipeline velocity (new programs per year)
            pipeline_velocity = self._calculate_pipeline_velocity(company_id, all_trials)
            
            # Get days since last pipeline update
            days_since_last_update = self._get_days_since_last_update(company_id)
            
            # Detect failure clustering
            failure_clustering = self._detect_failure_clustering(company_id)
            
            # Get additional metrics from inferred relationships
            publication_metrics = self._get_publication_metrics(company_id)
            filing_metrics = self._get_filing_metrics(company_id)
            drug_metrics = self._get_drug_metrics(company_id)
            
            metrics = {
                'company_id': str(company_id),
                'company_name': company.name,
                'total_trials': total_trials,
                'active_trials': active_count,
                'terminated_count': terminated_count,
                'success_rate_phase_1': phase_1_success_rate,
                'success_rate_phase_2': phase_2_success_rate,
                'success_rate_phase_3': phase_3_success_rate,
                'pipeline_velocity': pipeline_velocity,
                'days_since_last_update': days_since_last_update,
                'failure_clustering': failure_clustering,
                # New metrics from inferred relationships
                'publications_count': publication_metrics.get('publications_count', 0),
                'publications_with_trials': publication_metrics.get('publications_with_trials', 0),
                'publications_with_drugs': publication_metrics.get('publications_with_drugs', 0),
                'filings_with_drugs': filing_metrics.get('filings_with_drugs', 0),
                'total_drugs': drug_metrics.get('total_drugs', 0),
                'calculated_at': datetime.now().isoformat()
            }
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, metrics, ttl=CacheTTL.METRICS)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating company metrics for {company_id}: {e}", exc_info=True)
            return {
                'company_id': str(company_id),
                'error': str(e)
            }
    
    def _calculate_phase_success_rate(self, trials: List[ClinicalTrial]) -> Optional[float]:
        """Calculate success rate for a phase."""
        if not trials:
            return None
        
        # Success = completed (not terminated/withdrawn)
        successful = [t for t in trials if t.status == TrialStatus.COMPLETED]
        total = len(trials)
        
        if total == 0:
            return None
        
        return len(successful) / total
    
    def _calculate_pipeline_velocity(self, company_id: UUID, trials: List[ClinicalTrial]) -> float:
        """Calculate new programs per year."""
        if not trials:
            return 0.0
        
        # Get registration dates
        registration_dates = [t.registration_date for t in trials if t.registration_date]
        
        if not registration_dates:
            return 0.0
        
        # Calculate time span
        min_date = min(registration_dates)
        max_date = max(registration_dates)
        
        if min_date == max_date:
            return float(len(trials))
        
        days_span = (max_date - min_date).days
        if days_span == 0:
            return float(len(trials))
        
        years_span = days_span / 365.25
        if years_span == 0:
            return float(len(trials))
        
        return len(trials) / years_span
    
    def _get_days_since_last_update(self, company_id: UUID) -> Optional[int]:
        """Get days since last pipeline update event."""
        try:
            # Get most recent event for this company
            from sqlalchemy import func
            recent_event = self.session.query(Event).filter(
                func.array_position(Event.entities_involved, company_id) != None,
                Event.deleted_at.is_(None)
            ).order_by(Event.event_date.desc()).first()
            
            if not recent_event:
                return None
            
            days = (date.today() - recent_event.event_date).days
            return days
            
        except Exception as e:
            logger.error(f"Error getting days since last update: {e}", exc_info=True)
            return None
    
    def _detect_failure_clustering(self, company_id: UUID) -> Dict[str, Any]:
        """Detect if multiple failures occurred in short period."""
        try:
            # Get failure events in last 12 months
            twelve_months_ago = date.today() - timedelta(days=365)
            
            failure_events = self.session.query(Event).filter(
                func.array_position(Event.entities_involved, company_id) != None,
                Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn']),
                Event.event_date >= twelve_months_ago,
                Event.deleted_at.is_(None)
            ).order_by(Event.event_date.asc()).all()
            
            if len(failure_events) < 2:
                return {
                    'has_clustering': False,
                    'failure_count': len(failure_events),
                    'clustering_period_days': None
                }
            
            # Check if failures are clustered (within 90 days)
            clustered_periods = []
            if failure_events:
                current_cluster = [failure_events[0]]
                
                for event in failure_events[1:]:
                    days_between = (event.event_date - current_cluster[-1].event_date).days
                    if days_between <= 90:
                        current_cluster.append(event)
                    else:
                        if len(current_cluster) >= 2:
                            clustered_periods.append(current_cluster)
                        current_cluster = [event]
                
                # Check last cluster
                if len(current_cluster) >= 2:
                    clustered_periods.append(current_cluster)
            
            if clustered_periods:
                # Get largest cluster
                largest_cluster = max(clustered_periods, key=len)
                period_days = (largest_cluster[-1].event_date - largest_cluster[0].event_date).days
                
                return {
                    'has_clustering': True,
                    'failure_count': len(failure_events),
                    'clustering_period_days': period_days,
                    'cluster_size': len(largest_cluster)
                }
            
            return {
                'has_clustering': False,
                'failure_count': len(failure_events),
                'clustering_period_days': None
            }
            
        except Exception as e:
            logger.error(f"Error detecting failure clustering: {e}", exc_info=True)
            return {
                'has_clustering': False,
                'error': str(e)
            }
    
    def _get_publication_metrics(self, company_id: UUID) -> Dict[str, Any]:
        """Get publication-related metrics for a company."""
        try:
            # Count publications mentioning this company
            publications_count = self.session.query(PublicationCompany).filter(
                PublicationCompany.company_id == company_id,
                PublicationCompany.deleted_at.is_(None)
            ).count()
            
            # Count publications that mention trials sponsored by this company
            # Join PublicationTrial -> TrialSponsor to find company's trials
            publications_with_trials = self.session.query(PublicationTrial).join(
                TrialSponsor,
                PublicationTrial.trial_id == TrialSponsor.trial_id
            ).filter(
                TrialSponsor.entity_id == company_id,
                TrialSponsor.entity_type == 'company',
                PublicationTrial.deleted_at.is_(None),
                TrialSponsor.deleted_at.is_(None)
            ).distinct().count()
            
            # Count publications mentioning drugs from company's pipeline
            # Join PublicationDrug -> CompanyDrug to find company's drugs
            publications_with_drugs = self.session.query(PublicationDrug).join(
                CompanyDrug,
                PublicationDrug.drug_id == CompanyDrug.drug_id
            ).filter(
                CompanyDrug.company_id == company_id,
                PublicationDrug.deleted_at.is_(None),
                CompanyDrug.deleted_at.is_(None)
            ).distinct().count()
            
            return {
                'publications_count': publications_count,
                'publications_with_trials': publications_with_trials,
                'publications_with_drugs': publications_with_drugs
            }
        except Exception as e:
            logger.warning(f"Error getting publication metrics for {company_id}: {e}")
            return {
                'publications_count': 0,
                'publications_with_trials': 0,
                'publications_with_drugs': 0
            }
    
    def _get_filing_metrics(self, company_id: UUID) -> Dict[str, Any]:
        """Get SEC filing-related metrics for a company."""
        try:
            # Count filings mentioning drugs from company's pipeline
            # Join FilingDrug -> CompanyDrug to find company's drugs
            filings_with_drugs = self.session.query(FilingDrug).join(
                CompanyDrug,
                FilingDrug.drug_id == CompanyDrug.drug_id
            ).filter(
                CompanyDrug.company_id == company_id,
                FilingDrug.deleted_at.is_(None),
                CompanyDrug.deleted_at.is_(None)
            ).distinct().count()
            
            return {
                'filings_with_drugs': filings_with_drugs
            }
        except Exception as e:
            logger.warning(f"Error getting filing metrics for {company_id}: {e}")
            return {
                'filings_with_drugs': 0
            }
    
    def _get_drug_metrics(self, company_id: UUID) -> Dict[str, Any]:
        """Get drug-related metrics for a company."""
        try:
            # Count total drugs in company's pipeline (including inferred)
            total_drugs = self.session.query(func.count(func.distinct(CompanyDrug.drug_id))).filter(
                CompanyDrug.company_id == company_id,
                CompanyDrug.deleted_at.is_(None)
            ).scalar() or 0
            
            return {
                'total_drugs': total_drugs
            }
        except Exception as e:
            logger.warning(f"Error getting drug metrics for {company_id}: {e}")
            return {
                'total_drugs': 0
            }
    
    def calculate_company_risk_score(self, company_id: UUID) -> Dict[str, Any]:
        """
        Calculate composite risk score (0-100) for a company.
        
        Args:
            company_id: Company UUID
            
        Returns:
            Dictionary with risk score, category, and component breakdown
        """
        try:
            # Check cache first
            cache_key = f"risk_score:{company_id}"
            if self.cache:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            
            # Get metrics
            metrics = self.get_company_metrics(company_id)
            
            if 'error' in metrics:
                return metrics
            
            # Component 1: Failure Rate (40 points)
            total_trials = metrics.get('total_trials', 0)
            terminated_count = metrics.get('terminated_count', 0)
            
            if total_trials > 0:
                failure_rate = terminated_count / total_trials
                failure_score = min(failure_rate * self.FAILURE_RATE_WEIGHT, self.FAILURE_RATE_WEIGHT)
            else:
                failure_score = 0
            
            # Component 2: Recent Failures (30 points)
            twelve_months_ago = date.today() - timedelta(days=365)
            recent_events = self.failure_service.get_program_events(
                entity_id=company_id,
                start_date=twelve_months_ago
            )
            
            failure_events = [e for e in recent_events if e.event_type in [
                'trial.status.terminated',
                'trial.status.withdrawn',
                'regulatory.clinical_hold'
            ]]
            
            failures_last_12mo = len(failure_events)
            if failures_last_12mo >= 3:
                recent_score = 30
            elif failures_last_12mo == 2:
                recent_score = 20
            elif failures_last_12mo == 1:
                recent_score = 10
            else:
                recent_score = 0
            
            # Component 3: Pipeline Stagnation (20 points)
            days_since_update = metrics.get('days_since_last_update')
            if days_since_update is None:
                stagnation_score = 0
            elif days_since_update > 730:  # 2 years
                stagnation_score = 20
            elif days_since_update > 365:  # 1 year
                stagnation_score = 15
            elif days_since_update > 180:  # 6 months
                stagnation_score = 10
            else:
                stagnation_score = 0
            
            # Component 4: Early Warning Signals (10 points)
            warning_signals = self._get_warning_signals(company_id)
            warning_count = len(warning_signals)
            warning_score = min(warning_count * 2, self.WARNING_SIGNALS_WEIGHT)
            
            # Calculate total risk score
            total_score = failure_score + recent_score + stagnation_score + warning_score
            
            # Determine risk category
            risk_category = self._get_risk_category(total_score)
            
            result = {
                'company_id': str(company_id),
                'company_name': metrics.get('company_name'),
                'risk_score': round(total_score, 2),
                'risk_category': risk_category,
                'components': {
                    'failure_rate': {
                        'score': round(failure_score, 2),
                        'weight': self.FAILURE_RATE_WEIGHT,
                        'details': {
                            'total_trials': total_trials,
                            'terminated_count': terminated_count,
                            'failure_rate': round(terminated_count / total_trials if total_trials > 0 else 0, 3)
                        }
                    },
                    'recent_failures': {
                        'score': recent_score,
                        'weight': self.RECENT_FAILURES_WEIGHT,
                        'details': {
                            'failures_last_12mo': failures_last_12mo
                        }
                    },
                    'pipeline_stagnation': {
                        'score': stagnation_score,
                        'weight': self.PIPELINE_STAGNATION_WEIGHT,
                        'details': {
                            'days_since_last_update': days_since_update
                        }
                    },
                    'warning_signals': {
                        'score': warning_score,
                        'weight': self.WARNING_SIGNALS_WEIGHT,
                        'details': {
                            'signal_count': warning_count,
                            'signals': warning_signals
                        }
                    }
                },
                'calculated_at': datetime.now().isoformat()
            }
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, result, ttl=CacheTTL.RISK_SCORE)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating risk score for {company_id}: {e}", exc_info=True)
            return {
                'company_id': str(company_id),
                'error': str(e),
                'calculated_at': datetime.now().isoformat()
            }
    
    def _get_warning_signals(self, company_id: UUID) -> List[Dict[str, Any]]:
        """Get early warning signals for a company."""
        signals = []
        
        try:
            # Get recent failure signals
            failure_signals = self.failure_service.get_failure_signals(company_id)
            
            for signal in failure_signals:
                signals.append({
                    'type': 'failure_signal',
                    'event_type': signal.event_type,
                    'event_date': signal.event_date.isoformat(),
                    'severity': 'high'
                })
            
            # Check for failure clustering
            clustering = self._detect_failure_clustering(company_id)
            if clustering.get('has_clustering'):
                signals.append({
                    'type': 'failure_clustering',
                    'cluster_size': clustering.get('cluster_size'),
                    'period_days': clustering.get('clustering_period_days'),
                    'severity': 'critical'
                })
            
        except Exception as e:
            logger.error(f"Error getting warning signals: {e}", exc_info=True)
        
        return signals
    
    def _get_risk_category(self, score: float) -> str:
        """Get risk category from score."""
        if score < 25:
            return 'LOW'
        elif score < 50:
            return 'MODERATE'
        elif score < 75:
            return 'HIGH'
        else:
            return 'CRITICAL'
    
    def get_company_timeline(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        event_types: Optional[List[str]] = None
    ) -> List[Event]:
        """
        Get timeline of events for a company.
        
        Args:
            company_id: Company UUID
            start_date: Optional start date filter
            end_date: Optional end date filter
            event_types: Optional list of event types to filter
            
        Returns:
            List of Event objects ordered by date
        """
        try:
            # Check cache first
            # Build cache key with serializable values
            start_date_str = start_date.isoformat() if start_date else None
            end_date_str = end_date.isoformat() if end_date else None
            event_types_str = ','.join(sorted(event_types)) if event_types else None
            cache_key = f"company_timeline:{company_id}:{start_date_str}:{end_date_str}:{event_types_str}"
            if self.cache:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            
            # Use existing service method
            events = self.failure_service.get_entity_timeline(
                entity_id=company_id,
                include_related=True
            )
            
            # Apply additional filters
            if start_date:
                events = [e for e in events if e.event_date >= start_date]
            
            if end_date:
                events = [e for e in events if e.event_date <= end_date]
            
            if event_types:
                events = [e for e in events if e.event_type in event_types]
            
            # Cache result
            if self.cache:
                self.cache.set(cache_key, events, ttl=CacheTTL.TIMELINE)
            
            return events
            
        except Exception as e:
            logger.error(f"Error getting company timeline: {e}", exc_info=True)
            return []
    
    def get_company_trials(
        self,
        company_id: UUID,
        status_filter: Optional[List[str]] = None,
        phase_filter: Optional[List[int]] = None
    ) -> List[ClinicalTrial]:
        """
        Get all trials for a company with optional filters.
        
        Args:
            company_id: Company UUID
            status_filter: Optional list of statuses to filter
            phase_filter: Optional list of phase numbers to filter
            
        Returns:
            List of ClinicalTrial objects
        """
        try:
            query = self.session.query(ClinicalTrial).join(
                TrialSponsor,
                ClinicalTrial.trial_id == TrialSponsor.trial_id
            ).filter(
                TrialSponsor.entity_id == company_id,
                TrialSponsor.entity_type == 'company',
                TrialSponsor.deleted_at.is_(None),
                ClinicalTrial.deleted_at.is_(None)
            )
            
            if status_filter:
                query = query.filter(ClinicalTrial.status.in_(status_filter))
            
            if phase_filter:
                query = query.filter(ClinicalTrial.phase_numeric.in_(phase_filter))
            
            return query.order_by(ClinicalTrial.registration_date.desc()).all()
            
        except Exception as e:
            logger.error(f"Error getting company trials: {e}", exc_info=True)
            return []

