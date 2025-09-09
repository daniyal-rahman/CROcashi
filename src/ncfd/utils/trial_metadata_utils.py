"""
Trial Metadata Utilities

Utilities for managing trial metadata, including backfill helpers for missing data.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import requests

from ..db.models import Trial
from ..db.session import session_scope

logger = logging.getLogger(__name__)


class TrialMetadataBackfill:
    """Helper class for backfilling missing trial metadata."""
    
    def __init__(self):
        self.ctgov_base_url = "https://clinicaltrials.gov/api/query/full_studies"
        self.timeout_seconds = 30
    
    def backfill_trial_by_nct(self, nct_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Backfill trial metadata by NCT ID from CT.gov API.
        
        Args:
            nct_id: NCT identifier for the trial
            
        Returns:
            Tuple of (success, trial_data)
        """
        logger.info(f"Attempting to backfill trial metadata for {nct_id}")
        
        try:
            # Check if trial already exists and has complete metadata
            with session_scope() as session:
                existing_trial = session.query(Trial).filter(Trial.nct_id == nct_id).first()
                if existing_trial and existing_trial.official_title and existing_trial.brief_title:
                    logger.info(f"Trial {nct_id} already has complete metadata")
                    return True, self._trial_to_dict(existing_trial)
            
            # Fetch from CT.gov API
            ctgov_data = self._fetch_from_ctgov(nct_id)
            if not ctgov_data:
                logger.error(f"Failed to fetch trial data from CT.gov for {nct_id}")
                return False, {}
            
            # Parse CT.gov response
            trial_data = self._parse_ctgov_response(ctgov_data)
            if not trial_data:
                logger.error(f"Failed to parse CT.gov response for {nct_id}")
                return False, {}
            
            # Upsert trial data
            success = self._upsert_trial_data(nct_id, trial_data)
            if success:
                logger.info(f"Successfully backfilled trial metadata for {nct_id}")
                return True, trial_data
            else:
                logger.error(f"Failed to upsert trial data for {nct_id}")
                return False, {}
                
        except Exception as e:
            logger.error(f"Error backfilling trial metadata for {nct_id}: {e}")
            return False, {}
    
    def _fetch_from_ctgov(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """Fetch trial data from CT.gov API."""
        try:
            params = {
                'expr': nct_id,
                'fmt': 'json',
                'min_rnk': 1,
                'max_rnk': 1
            }
            
            response = requests.get(
                self.ctgov_base_url,
                params=params,
                timeout=self.timeout_seconds
            )
            response.raise_for_status()
            
            data = response.json()
            studies = data.get('FullStudiesResponse', {}).get('FullStudies', [])
            
            if not studies:
                logger.warning(f"No studies found for {nct_id}")
                return None
            
            return studies[0].get('Study', {})
            
        except requests.RequestException as e:
            logger.error(f"HTTP error fetching {nct_id} from CT.gov: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {nct_id} from CT.gov: {e}")
            return None
    
    def _parse_ctgov_response(self, study_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse CT.gov API response into trial data."""
        try:
            protocol_section = study_data.get('ProtocolSection', {})
            identification_module = protocol_section.get('IdentificationModule', {})
            status_module = protocol_section.get('StatusModule', {})
            design_module = protocol_section.get('DesignModule', {})
            conditions_module = protocol_section.get('ConditionsModule', {})
            interventions_module = protocol_section.get('InterventionsModule', {})
            sponsors_module = protocol_section.get('SponsorCollaboratorsModule', {})
            
            # Extract basic information
            trial_data = {
                'nct_id': identification_module.get('NCTId'),
                'official_title': identification_module.get('OfficialTitle'),
                'brief_title': identification_module.get('BriefTitle'),
                'status': status_module.get('OverallStatus'),
                'phase': self._extract_phase(design_module),
                'indication': self._extract_indication(conditions_module),
                'sponsor_text': self._extract_sponsor(sponsors_module),
                'current_sha256': self._generate_trial_hash(identification_module, status_module)
            }
            
            # Validate required fields
            if not trial_data['nct_id'] or not trial_data['official_title']:
                logger.error(f"Missing required fields in CT.gov response")
                return None
            
            return trial_data
            
        except Exception as e:
            logger.error(f"Error parsing CT.gov response: {e}")
            return None
    
    def _extract_phase(self, design_module: Dict[str, Any]) -> Optional[str]:
        """Extract phase information from design module."""
        phases = design_module.get('PhaseList', {}).get('Phase', [])
        if not phases:
            return None
        
        # Join multiple phases with "/"
        if isinstance(phases, list):
            return "/".join(phases)
        return str(phases)
    
    def _extract_indication(self, conditions_module: Dict[str, Any]) -> Optional[str]:
        """Extract indication information from conditions module."""
        conditions = conditions_module.get('ConditionList', {}).get('Condition', [])
        if not conditions:
            return None
        
        # Join multiple conditions
        if isinstance(conditions, list):
            return "; ".join(conditions)
        return str(conditions)
    
    def _extract_sponsor(self, sponsors_module: Dict[str, Any]) -> Optional[str]:
        """Extract sponsor information from sponsors module."""
        lead_sponsor = sponsors_module.get('LeadSponsor', {})
        return lead_sponsor.get('LeadSponsorName')
    
    def _generate_trial_hash(self, identification_module: Dict[str, Any], 
                           status_module: Dict[str, Any]) -> str:
        """Generate SHA256 hash for trial data."""
        # Create a stable hash based on key trial data
        hash_data = {
            'nct_id': identification_module.get('NCTId'),
            'official_title': identification_module.get('OfficialTitle'),
            'brief_title': identification_module.get('BriefTitle'),
            'status': status_module.get('OverallStatus'),
            'last_update': status_module.get('LastUpdatePostDate')
        }
        
        hash_string = str(sorted(hash_data.items()))
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    def _upsert_trial_data(self, nct_id: str, trial_data: Dict[str, Any]) -> bool:
        """Upsert trial data into the database."""
        try:
            with session_scope() as session:
                # Check if trial exists
                existing_trial = session.query(Trial).filter(Trial.nct_id == nct_id).first()
                
                if existing_trial:
                    # Update existing trial
                    logger.info(f"Updating existing trial {nct_id}")
                    existing_trial.official_title = trial_data.get('official_title') or existing_trial.official_title
                    existing_trial.brief_title = trial_data.get('brief_title') or existing_trial.brief_title
                    existing_trial.status = trial_data.get('status') or existing_trial.status
                    existing_trial.phase = trial_data.get('phase') or existing_trial.phase
                    existing_trial.indication = trial_data.get('indication') or existing_trial.indication
                    existing_trial.sponsor_text = trial_data.get('sponsor_text') or existing_trial.sponsor_text
                    existing_trial.current_sha256 = trial_data.get('current_sha256') or existing_trial.current_sha256
                    existing_trial.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new trial
                    logger.info(f"Creating new trial {nct_id}")
                    new_trial = Trial(
                        nct_id=trial_data['nct_id'],
                        official_title=trial_data['official_title'],
                        brief_title=trial_data['brief_title'],
                        status=trial_data.get('status'),
                        phase=trial_data.get('phase'),
                        indication=trial_data.get('indication'),
                        sponsor_text=trial_data.get('sponsor_text'),
                        current_sha256=trial_data['current_sha256']
                    )
                    session.add(new_trial)
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Database error upserting trial {nct_id}: {e}")
            return False
    
    def _trial_to_dict(self, trial: Trial) -> Dict[str, Any]:
        """Convert Trial model to dictionary."""
        return {
            'trial_id': trial.trial_id,
            'nct_id': trial.nct_id,
            'official_title': trial.official_title,
            'brief_title': trial.brief_title,
            'status': trial.status,
            'phase': trial.phase,
            'indication': trial.indication,
            'sponsor_text': trial.sponsor_text,
            'current_sha256': trial.current_sha256
        }


def ensure_trial_metadata(nct_id: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Ensure trial metadata is complete, backfilling from CT.gov if necessary.
    
    Args:
        nct_id: NCT identifier for the trial
        
    Returns:
        Tuple of (success, trial_data)
    """
    backfill = TrialMetadataBackfill()
    return backfill.backfill_trial_by_nct(nct_id)


def validate_trial_metadata(trial_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate trial metadata completeness.
    
    Args:
        trial_data: Trial data dictionary
        
    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    
    required_fields = ['nct_id', 'official_title', 'current_sha256']
    for field in required_fields:
        if not trial_data.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate NCT ID format
    nct_id = trial_data.get('nct_id', '')
    if nct_id and not nct_id.startswith('NCT'):
        errors.append(f"Invalid NCT ID format: {nct_id}")
    
    # Check title length
    official_title = trial_data.get('official_title', '')
    if official_title and len(official_title) < 10:
        errors.append(f"Official title too short: {len(official_title)} characters")
    
    return len(errors) == 0, errors
