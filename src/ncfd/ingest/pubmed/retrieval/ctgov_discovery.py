"""
CT.gov integration for trial-first discovery.

Implements ClinicalTrials.gov API integration to discover trials
and extract NCT IDs for PubMed backfill queries.
"""

import asyncio
import logging
import aiohttp
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from ....entities.schema import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class CTgovConfig:
    """Configuration for CT.gov integration."""
    api_base_url: str = "https://clinicaltrials.gov/api/v2"
    max_trials_per_search: int = 100
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    enable_trial_discovery: bool = True
    enable_nct_backfill: bool = True


@dataclass
class TrialInfo:
    """Information about a discovered trial."""
    nct_id: str
    title: str
    phase: Optional[str]
    status: Optional[str]
    condition: Optional[str]
    intervention: Optional[str]
    sponsor: Optional[str]
    start_date: Optional[str]
    completion_date: Optional[str]
    linked_pmids: List[str]
    study_type: Optional[str]
    enrollment: Optional[int]


@dataclass
class CTgovDiscoveryResult:
    """Result from CT.gov trial discovery."""
    trials_found: int
    nct_ids: List[str]
    trial_info: List[TrialInfo]
    linked_pmids: List[str]
    discovery_time: float
    success: bool
    error_message: Optional[str] = None


class CTgovAPIClient:
    """Client for CT.gov API interactions."""
    
    def __init__(self, config: CTgovConfig):
        """
        Initialize CT.gov API client.
        
        Args:
            config: CT.gov configuration
        """
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(__name__)
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def search_trials(
        self,
        condition: Optional[str] = None,
        intervention: Optional[str] = None,
        sponsor: Optional[str] = None,
        study_type: str = "Interventional",
        phase: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for trials using CT.gov API.
        
        Args:
            condition: Disease/condition to search for
            intervention: Drug/intervention to search for
            sponsor: Sponsor organization
            study_type: Type of study (default: Interventional)
            phase: Trial phase
            status: Trial status
            
        Returns:
            API response data
        """
        try:
            # Build search parameters
            params = {
                'format': 'json',
                'query.cond': condition,
                'query.intr': intervention,
                'query.spons': sponsor,
                'query.phase': phase,
                'fields': 'NCTId,BriefTitle'
            }
            
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            
            url = f"{self.config.api_base_url}/studies"
            
            self.logger.info(f"Searching CT.gov API: {url}")
            self.logger.debug(f"Search parameters: {params}")
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    trials_found = data.get('totalStudies', 0)
                    self.logger.info(f"CT.gov direct API search completed: {trials_found} trials found")
                    return data
                else:
                    error_text = await response.text()
                    self.logger.error(f"CT.gov API search failed: {response.status} - {error_text}")
                    return {'studies': [], 'totalStudies': 0}
                    
        except Exception as e:
            self.logger.error(f"Error searching CT.gov API: {e}")
            return {'studies': [], 'totalStudies': 0}
    
    async def get_trial_details(self, nct_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific trial.
        
        Args:
            nct_id: NCT ID of the trial
            
        Returns:
            Detailed trial information
        """
        try:
            url = f"{self.config.api_base_url}/studies/{nct_id}"
            params = {'format': 'json'}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_text = await response.text()
                    self.logger.error(f"Failed to get trial details for {nct_id}: {response.status} - {error_text}")
                    return {}
                    
        except Exception as e:
            self.logger.error(f"Error getting trial details for {nct_id}: {e}")
            return {}


class CTgovTrialDiscoverer:
    """Discovers trials from CT.gov and extracts NCT IDs for PubMed backfill."""
    
    def __init__(self, config: Optional[CTgovConfig] = None):
        """
        Initialize CT.gov trial discoverer.
        
        Args:
            config: CT.gov configuration
        """
        self.config = config or CTgovConfig()
        self.logger = logging.getLogger(__name__)
        
        logger.info(f"Initialized CT.gov trial discoverer with config: {self.config}")
    
    async def discover_trials(self, entity_pack: EntityPack) -> CTgovDiscoveryResult:
        """
        Discover trials for an entity pack.
        
        Args:
            entity_pack: Entity pack with trial information
            
        Returns:
            Discovery result with NCT IDs and trial information
        """
        start_time = datetime.now()
        
        try:
            self.logger.info(f"Starting CT.gov trial discovery for entity pack: {entity_pack.entity_id}")
            
            # Check if discovery is enabled
            if not self.config.enable_trial_discovery:
                self.logger.info("CT.gov trial discovery disabled")
                return CTgovDiscoveryResult(
                    trials_found=0,
                    nct_ids=[],
                    trial_info=[],
                    linked_pmids=[],
                    discovery_time=0.0,
                    success=True
                )
            
            # Build search parameters from entity pack
            search_params = self._build_search_params(entity_pack)
            
            # Search for trials
            async with CTgovAPIClient(self.config) as client:
                api_response = await client.search_trials(**search_params)
                
                if not api_response.get('studies'):
                    self.logger.info("CT.gov term-based search found 0 trials, proceeding with NCT backfill")
                    # Don't return early - continue with NCT backfill
                
                # Process trial results
                trial_info = self._process_trial_results(api_response['studies'])
                
                # Extract NCT IDs
                nct_ids = [trial.nct_id for trial in trial_info]
                
                # Extract linked PMIDs
                linked_pmids = []
                for trial in trial_info:
                    linked_pmids.extend(trial.linked_pmids)
                
                # Remove duplicates
                linked_pmids = list(set(linked_pmids))
                
                discovery_time = (datetime.now() - start_time).total_seconds()
                
                self.logger.info(f"CT.gov discovery completed: {len(trial_info)} total trials "
                               f"({len(api_response.get('studies', []))} from term search + {len(nct_ids) - len(api_response.get('studies', []))} from NCT backfill), "
                               f"{len(nct_ids)} NCT IDs, {len(linked_pmids)} linked PMIDs")
                
                return CTgovDiscoveryResult(
                    trials_found=len(trial_info),
                    nct_ids=nct_ids,
                    trial_info=trial_info,
                    linked_pmids=linked_pmids,
                    discovery_time=discovery_time,
                    success=True
                )
                
        except Exception as e:
            discovery_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"CT.gov trial discovery failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            return CTgovDiscoveryResult(
                trials_found=0,
                nct_ids=[],
                trial_info=[],
                linked_pmids=[],
                discovery_time=discovery_time,
                success=False,
                error_message=error_msg
            )
    
    def _build_search_params(self, entity_pack: EntityPack) -> Dict[str, Any]:
        """
        Build search parameters from entity pack.
        
        Args:
            entity_pack: Entity pack with trial information
            
        Returns:
            Search parameters for CT.gov API
        """
        # Get primary indication
        primary_indication = entity_pack.indications.primary[0] if entity_pack.indications.primary else None
        
        # Get primary asset
        primary_asset = entity_pack.asset.canonical
        
        # Get primary company
        primary_company = entity_pack.company.canonical
        
        # Build search parameters
        params = {
            'condition': primary_indication,
            'intervention': primary_asset,
            'sponsor': primary_company,
            'study_type': 'Interventional'
        }
        
        # Add aliases to intervention search
        if entity_pack.asset.aliases:
            intervention_terms = [primary_asset] + entity_pack.asset.aliases
            params['intervention'] = ' OR '.join(intervention_terms)
        
        # Add company aliases to sponsor search
        if entity_pack.company.aliases:
            sponsor_terms = [primary_company] + entity_pack.company.aliases
            params['sponsor'] = ' OR '.join(sponsor_terms)
        
        self.logger.debug(f"Built CT.gov search parameters: {params}")
        return params
    
    def _process_trial_results(self, studies: List[Dict[str, Any]]) -> List[TrialInfo]:
        """
        Process trial results from CT.gov API.
        
        Args:
            studies: List of study data from API
            
        Returns:
            List of processed trial information
        """
        trial_info = []
        
        for study in studies:
            try:
                # Extract basic information
                protocol_section = study.get('protocolSection', {})
                identification_module = protocol_section.get('identificationModule', {})
                design_module = protocol_section.get('designModule', {})
                status_module = protocol_section.get('statusModule', {})
                sponsor_module = protocol_section.get('sponsorCollaboratorsModule', {})
                conditions_module = protocol_section.get('conditionsModule', {})
                interventions_module = protocol_section.get('interventionsModule', {})
                
                # Extract NCT ID
                nct_id = identification_module.get('nctId', '')
                if not nct_id:
                    continue
                
                # Extract title
                title = identification_module.get('briefTitle', '')
                
                # Extract phase
                phase_info = design_module.get('phases', [])
                phase = phase_info[0] if phase_info else None
                
                # Extract status
                overall_status = status_module.get('overallStatus', {})
                status = overall_status.get('label') if overall_status else None
                
                # Extract sponsor
                lead_sponsor = sponsor_module.get('leadSponsor', {})
                sponsor = lead_sponsor.get('name') if lead_sponsor else None
                
                # Extract conditions
                conditions = conditions_module.get('conditions', [])
                condition = conditions[0] if conditions else None
                
                # Extract interventions
                interventions = interventions_module.get('interventions', [])
                intervention = interventions[0].get('name') if interventions else None
                
                # Extract dates
                start_date_struct = status_module.get('startDateStruct', {})
                start_date = start_date_struct.get('date') if start_date_struct else None
                
                completion_date_struct = status_module.get('completionDateStruct', {})
                completion_date = completion_date_struct.get('date') if completion_date_struct else None
                
                # Extract study type
                study_type_info = design_module.get('studyType', {})
                study_type = study_type_info.get('label') if study_type_info else None
                
                # Extract enrollment
                enrollment_info = design_module.get('enrollmentInfo', {})
                enrollment = enrollment_info.get('count') if enrollment_info else None
                
                # Extract linked PMIDs from results references
                linked_pmids = self._extract_linked_pmids(study)
                
                trial = TrialInfo(
                    nct_id=nct_id,
                    title=title,
                    phase=phase,
                    status=status,
                    condition=condition,
                    intervention=intervention,
                    sponsor=sponsor,
                    start_date=start_date,
                    completion_date=completion_date,
                    linked_pmids=linked_pmids,
                    study_type=study_type,
                    enrollment=enrollment
                )
                
                trial_info.append(trial)
                
            except Exception as e:
                self.logger.warning(f"Failed to process trial: {e}")
                continue
        
        return trial_info
    
    def _extract_linked_pmids(self, study: Dict[str, Any]) -> List[str]:
        """
        Extract linked PMIDs from study results references.
        
        Args:
            study: Study data from CT.gov API
            
        Returns:
            List of linked PMIDs
        """
        linked_pmids = []
        
        try:
            # Look for results references in the study data
            results_section = study.get('resultsSection', {})
            references_module = results_section.get('referencesModule', {})
            references = references_module.get('references', [])
            
            for reference in references:
                # Extract PMID from reference
                pmid = reference.get('pmid')
                if pmid:
                    linked_pmids.append(str(pmid))
                
                # Also check for DOI that might link to PubMed
                doi = reference.get('doi')
                if doi:
                    # Could potentially resolve DOI to PMID, but for now just log
                    self.logger.debug(f"Found DOI reference: {doi}")
            
        except Exception as e:
            self.logger.warning(f"Failed to extract linked PMIDs: {e}")
        
        return linked_pmids


class NCTBackfillQuery:
    """Handles NCT ID backfill queries for PubMed."""
    
    def __init__(self):
        """Initialize NCT backfill query processor."""
        self.logger = logging.getLogger(__name__)
    
    def build_nct_queries(self, nct_ids: List[str]) -> List[str]:
        """
        Build NCT-linked PubMed queries.
        
        Args:
            nct_ids: List of NCT IDs
            
        Returns:
            List of PubMed query strings
        """
        if not nct_ids:
            return []
        
        queries = []
        
        # Build individual NCT queries
        for nct_id in nct_ids:
            query = f"{nct_id}[si]"
            queries.append(query)
        
        # Build combined query
        if len(nct_ids) > 1:
            combined_query = " OR ".join([f"{nct_id}[si]" for nct_id in nct_ids])
            queries.append(combined_query)
        
        self.logger.info(f"Built {len(queries)} NCT backfill queries for {len(nct_ids)} NCT IDs")
        return queries
    
    def extract_nct_ids_from_text(self, text: str) -> List[str]:
        """
        Extract NCT IDs from text.
        
        Args:
            text: Text to search for NCT IDs
            
        Returns:
            List of found NCT IDs
        """
        import re
        
        # NCT ID pattern: NCT followed by 8 digits
        nct_pattern = r'NCT\d{8}'
        nct_ids = re.findall(nct_pattern, text, re.IGNORECASE)
        
        # Remove duplicates and return
        return list(set(nct_ids))


class CTgovIntegration:
    """Main integration class for CT.gov functionality."""
    
    def __init__(self, config: Optional[CTgovConfig] = None):
        """
        Initialize CT.gov integration.
        
        Args:
            config: CT.gov configuration
        """
        self.config = config or CTgovConfig()
        self.discoverer = CTgovTrialDiscoverer(self.config)
        self.nct_backfill = NCTBackfillQuery()
        self.logger = logging.getLogger(__name__)
    
    async def discover_and_build_queries(self, entity_pack: EntityPack) -> Tuple[List[str], CTgovDiscoveryResult]:
        """
        Discover trials and build NCT backfill queries.
        
        Args:
            entity_pack: Entity pack for trial discovery
            
        Returns:
            Tuple of (nct_queries, discovery_result)
        """
        try:
            # Discover trials
            discovery_result = await self.discoverer.discover_trials(entity_pack)
            
            if not discovery_result.success:
                self.logger.error(f"Trial discovery failed: {discovery_result.error_message}")
                return [], discovery_result
            
            # Build NCT queries
            nct_queries = self.nct_backfill.build_nct_queries(discovery_result.nct_ids)
            
            self.logger.info(f"CT.gov integration completed: {len(nct_queries)} queries built")
            return nct_queries, discovery_result
            
        except Exception as e:
            self.logger.error(f"CT.gov integration failed: {e}")
            return [], CTgovDiscoveryResult(
                trials_found=0,
                nct_ids=[],
                trial_info=[],
                linked_pmids=[],
                discovery_time=0.0,
                success=False,
                error_message=str(e)
            )
    
    def get_integration_summary(self) -> Dict[str, Any]:
        """Get summary of CT.gov integration configuration."""
        return {
            'api_base_url': self.config.api_base_url,
            'max_trials_per_search': self.config.max_trials_per_search,
            'timeout_seconds': self.config.timeout_seconds,
            'enable_trial_discovery': self.config.enable_trial_discovery,
            'enable_nct_backfill': self.config.enable_nct_backfill
        }
