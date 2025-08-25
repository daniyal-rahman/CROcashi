"""
Lightweight ClinicalTrials.gov v2 client focused on interventional drug/biologic Ph 2/3.
Server-side filter: date (LastUpdatePostDate). All other filters are client-side for stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generator, Iterable, List, Optional, Tuple, Dict, Any
import hashlib
import json
import os
import sys
import time
import logging

import requests
from bs4 import BeautifulSoup

from .ctgov_types import (
    ComprehensiveTrialFields, SponsorInfo, TrialDesign, Intervention, 
    Condition, Outcome, EnrollmentInfo, StatisticalAnalysis, Location,
    TrialPhase, TrialStatus, InterventionType, StudyType
)

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"
SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.strptime(value, fmt).date()
            # normalize YYYY-MM to YYYY-MM-01 for comparisons
            if fmt == "%Y-%m":
                return date(d.year, d.month, 1)
            return d
        except ValueError:
            continue
    return None


@dataclass
class NormalizedFields:
    nct_id: str
    sponsor_text: Optional[str]
    phase: Optional[str]
    intervention_types: List[str]
    primary_endpoint_text: Optional[str]
    sample_size: Optional[int]
    analysis_plan_text: Optional[str]
    status: Optional[str]
    first_posted_date: Optional[date]
    last_update_posted_date: Optional[date]
    est_primary_completion_date: Optional[date]


class CtgovClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, session: Optional[requests.Session] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or SESSION
        self.logger = logging.getLogger(__name__)

    # -----------------------------
    # API pagination (robust path)
    # -----------------------------
    def iter_raw(self, since: Optional[date] = None, page_size: int = 100) -> Generator[dict, None, None]:
        """
        Yield raw study JSON with only a date Essie filter (if provided) to avoid v2 400s.

        We send: GET /api/v2/studies
                 ?pageSize=...
                 [&query.term=AREA[LastUpdatePostDate]RANGE[YYYY-MM-DD,MAX]]
        Then page via nextPageToken. Everything else is filtered client-side.
        """
        url = f"{self.base_url}/studies"
        params = {"pageSize": page_size}
        if since:
            # Essie area for the "Other terms" box that the site itself uses
            params["query.term"] = f"AREA[LastUpdatePostDate]RANGE[{since.isoformat()},MAX]"

        next_token = None
        retry_count = 0
        max_retries = 3
        
        while True:
            call = dict(params)
            if next_token:
                call["pageToken"] = next_token

            try:
                resp = self.session.get(url, params=call, timeout=45)
                
                # Handle different response status codes
                if resp.status_code == 200:
                    retry_count = 0  # Reset retry count on success
                elif resp.status_code >= 500:
                    # Server error - retry with exponential backoff
                    if retry_count < max_retries:
                        retry_count += 1
                        wait_time = min(2 ** retry_count, 30)  # Max 30 seconds
                        self.logger.warning(f"Server error {resp.status_code}, retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        resp.raise_for_status()
                elif resp.status_code == 429:
                    # Rate limit - wait and retry
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    self.logger.warning(f"Rate limited, waiting {retry_after}s before retry")
                    time.sleep(retry_after)
                    continue
                else:
                    resp.raise_for_status()

                data = resp.json()
                studies = data.get("studies", [])
                for st in studies:
                    yield st

                next_token = data.get("nextPageToken") or resp.headers.get("x-next-page-token") or resp.headers.get("X-Next-Page-Token")
                if not next_token:
                    break
                    
            except requests.exceptions.RequestException as e:
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = min(2 ** retry_count, 30)
                    self.logger.warning(f"Request failed: {e}, retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"Max retries exceeded for {url}: {e}")
                    raise

    # -----------------------------
    # High-level iterator
    # -----------------------------
    def iter_studies(self, since: Optional[date] = None, page_size: int = 100) -> Generator[dict, None, None]:
        """
        Yield studies that are:
          - Interventional
          - Have any intervention.type in {DRUG, BIOLOGICAL}
          - Phase includes Phase 2, Phase 2/Phase 3, or Phase 3
        (filtered client-side for stability)
        """
        for st in self.iter_raw(since=since, page_size=page_size):
            if not self._is_interventional(st):
                continue
            if not self._has_drug_or_biologic(st):
                continue
            if not self._is_phase_2_or_3(st):
                continue
            yield st

    @staticmethod
    def _is_interventional(st: dict) -> bool:
        ps = st.get("protocolSection", {})
        dm = ps.get("designModule", {})
        study_type = dm.get("studyType") or st.get("studyType")  # some exports also expose at root
        return (study_type or "").upper().startswith("INTERVENTIONAL")

    @staticmethod
    def _has_drug_or_biologic(st: dict) -> bool:
        ps = st.get("protocolSection", {})
        ims = ps.get("armsInterventionsModule", {}) or {}
        types = []
        for it in ims.get("interventions", []) or []:
            typ = (it.get("type") or "").upper()
            if typ:
                types.append(typ)
        s = set(types)
        return bool({"DRUG", "BIOLOGICAL"} & s)

    @staticmethod
    def _is_phase_2_or_3(st: dict) -> bool:
        ps = st.get("protocolSection", {})
        phases = ps.get("designModule", {}).get("phases", []) or []
        # v2 uses enumerations like PHASE1, PHASE2, PHASE2_PHASE3, PHASE3, etc.
        phases_u = {p.upper() for p in phases}
        return bool(phases_u & {"PHASE2", "PHASE3", "PHASE2_PHASE3"})

    # -----------------------------
    # Field extraction
    # -----------------------------
    def extract_fields(self, study: dict) -> NormalizedFields:
        """Extract basic fields (maintains backward compatibility)."""
        ps = study.get("protocolSection", {}) or {}
        identification = ps.get("identificationModule", {}) or {}
        nct_id = identification.get("nctId")

        sponsor_text = (
            ps.get("sponsorCollaboratorsModule", {}) or {}
        ).get("leadSponsor", {}) or {}
        sponsor_text = sponsor_text.get("name")

        phases = ps.get("designModule", {}).get("phases", []) or []
        # phase = phases[0] if phases else None
        phase = next((p.upper() for p in phases if p.upper() in ["PHASE2", "PHASE3", "PHASE2_PHASE3"]), None)

        intervention_types: List[str] = []
        for item in (ps.get("armsInterventionsModule", {}) or {}).get("interventions", []) or []:
            typ = item.get("type")
            if typ:
                intervention_types.append(typ)
        intervention_types = sorted(set(intervention_types))

        outcomes = (ps.get("outcomesModule", {}) or {}).get("primaryOutcomes", []) or []
        parts = []
        for out in outcomes:
            measure = (out.get("measure") or "").strip()
            timeframe = (out.get("timeFrame") or "").strip()
            if measure:
                parts.append(f"{measure} ({timeframe})" if timeframe else measure)
        primary_endpoint = "; ".join(parts) or None

        enrollment_info = (ps.get("designModule", {}) or {}).get("enrollmentInfo", {}) or {}
        sample_size = enrollment_info.get("count")

        status_module = ps.get("statusModule", {}) or {}
        status = status_module.get("overallStatus")

        first_posted = _parse_date((status_module.get("studyFirstPostDateStruct") or {}).get("date"))
        last_update = _parse_date((status_module.get("lastUpdatePostDateStruct") or {}).get("date"))
        est_primary_completion = _parse_date((status_module.get("primaryCompletionDateStruct") or {}).get("date"))

        # analysis plan text is rarely present as a single field; keep best-effort
        analysis_plan_text = None
        analysis_module = (ps.get("analysisModule", {}) or {})
        if isinstance(analysis_module.get("analysisPlan"), str):
            text = analysis_module.get("analysisPlan", "").strip()
            analysis_plan_text = text or None

        return NormalizedFields(
            nct_id=nct_id,
            sponsor_text=sponsor_text,
            phase=phase,
            intervention_types=intervention_types,
            primary_endpoint_text=primary_endpoint,
            sample_size=sample_size,
            analysis_plan_text=analysis_plan_text,
            status=status,
            first_posted_date=first_posted,
            last_update_posted_date=last_update,
            est_primary_completion_date=est_primary_completion,
        )

    def extract_comprehensive_fields(self, study: dict) -> ComprehensiveTrialFields:
        """Extract comprehensive trial information."""
        ps = study.get("protocolSection", {}) or {}
        identification = ps.get("identificationModule", {}) or {}
        
        # Basic identification
        nct_id = identification.get("nctId")
        brief_title = identification.get("briefTitle")
        official_title = identification.get("officialTitle")
        acronym = identification.get("acronym")
        
        # Sponsor information
        sponsor_info = self._extract_sponsor_info(ps)
        
        # Study type and phase
        study_type = self._determine_study_type(ps)
        phase = self._extract_phase(ps)
        
        # Trial design
        trial_design = self._extract_trial_design(ps)
        
        # Interventions
        interventions = self._extract_interventions(ps)
        
        # Conditions
        conditions = self._extract_conditions(ps)
        
        # Outcomes
        primary_outcomes = self._extract_outcomes(ps, "primaryOutcomes")
        secondary_outcomes = self._extract_outcomes(ps, "secondaryOutcomes")
        other_outcomes = self._extract_outcomes(ps, "otherOutcomes")
        
        # Enrollment
        enrollment_info = self._extract_enrollment_info(ps)
        
        # Eligibility
        eligibility_criteria = self._extract_eligibility_criteria(ps)
        
        # Statistical analysis
        statistical_analysis = self._extract_statistical_analysis(ps)
        
        # Status and dates
        status, dates = self._extract_status_and_dates(ps)
        
        # Locations
        locations = self._extract_locations(ps)
        
        # Additional metadata
        keywords = self._extract_keywords(ps)
        mesh_terms = self._extract_mesh_terms(ps)
        study_documents = self._extract_study_documents(ps)
        
        return ComprehensiveTrialFields(
            nct_id=nct_id,
            brief_title=brief_title,
            official_title=official_title,
            acronym=acronym,
            sponsor_info=sponsor_info,
            study_type=study_type,
            phase=phase,
            trial_design=trial_design,
            interventions=interventions,
            conditions=conditions,
            primary_outcomes=primary_outcomes,
            secondary_outcomes=secondary_outcomes,
            other_outcomes=other_outcomes,
            enrollment_info=enrollment_info,
            eligibility_criteria=eligibility_criteria,
            statistical_analysis=statistical_analysis,
            status=status,
            first_posted_date=dates.get("first_posted"),
            last_update_posted_date=dates.get("last_update"),
            study_start_date=dates.get("study_start"),
            primary_completion_date=dates.get("primary_completion"),
            study_completion_date=dates.get("study_completion"),
            locations=locations,
            keywords=keywords,
            mesh_terms=mesh_terms,
            study_documents=study_documents,
            raw_jsonb=study,
            extracted_at=datetime.utcnow()
        )

    def _extract_sponsor_info(self, ps: Dict[str, Any]) -> SponsorInfo:
        """Extract detailed sponsor information."""
        sponsor_module = ps.get("sponsorCollaboratorsModule", {}) or {}
        
        lead_sponsor = sponsor_module.get("leadSponsor", {}) or {}
        lead_sponsor_name = lead_sponsor.get("name", "")
        lead_sponsor_cik = lead_sponsor.get("cik")
        lead_sponsor_lei = lead_sponsor.get("lei")
        lead_sponsor_country = lead_sponsor.get("country")
        
        collaborators = []
        for collab in sponsor_module.get("collaborators", []) or []:
            name = collab.get("name")
            if name:
                collaborators.append(name)
        
        responsible_party = sponsor_module.get("responsibleParty", {}) or {}
        responsible_party_name = responsible_party.get("name")
        responsible_party_type = responsible_party.get("type")
        
        agency_class = sponsor_module.get("agencyClass")
        
        return SponsorInfo(
            lead_sponsor_name=lead_sponsor_name,
            lead_sponsor_cik=lead_sponsor_cik,
            lead_sponsor_lei=lead_sponsor_lei,
            lead_sponsor_country=lead_sponsor_country,
            collaborators=collaborators,
            responsible_party_name=responsible_party_name,
            responsible_party_type=responsible_party_type,
            agency_class=agency_class
        )

    def _determine_study_type(self, ps: Dict[str, Any]) -> StudyType:
        """Determine the study type."""
        design_module = ps.get("designModule", {}) or {}
        study_type = design_module.get("studyType") or ps.get("studyType")
        
        if study_type:
            study_type_upper = study_type.upper()
            if "INTERVENTIONAL" in study_type_upper:
                return StudyType.INTERVENTIONAL
            elif "OBSERVATIONAL" in study_type_upper:
                return StudyType.OBSERVATIONAL
            elif "EXPANDED_ACCESS" in study_type_upper:
                return StudyType.EXPANDED_ACCESS
        
        return StudyType.INTERVENTIONAL  # Default

    def _extract_phase(self, ps: Dict[str, Any]) -> Optional[TrialPhase]:
        """Extract trial phase."""
        design_module = ps.get("designModule", {}) or {}
        phases = design_module.get("phases", []) or []
        
        if not phases:
            return None
        
        # phase_str = phases[0].upper()
        for p in phases.upper():
            if p in {"PHASE2", "PHASE3", "PHASE2_PHASE3"}:
                phase_str = p
                break
        # Map phase strings to enum values
        phase_mapping = {
            # "PHASE1": TrialPhase.PHASE1,
            "PHASE2": TrialPhase.PHASE2,
            "PHASE3": TrialPhase.PHASE3,
            "PHASE4": TrialPhase.PHASE4,
            "PHASE2_PHASE3": TrialPhase.PHASE2_PHASE3,
            "PHASE1_PHASE2": TrialPhase.PHASE1_PHASE2,
            "PHASE3_PHASE4": TrialPhase.PHASE3_PHASE4,
            # "EARLY_PHASE1": TrialPhase.EARLY_PHASE1
        }
        
        return phase_mapping.get(phase_str)

    def _extract_trial_design(self, ps: Dict[str, Any]) -> TrialDesign:
        """Extract trial design information."""
        design_module = ps.get("designModule", {}) or {}
        
        allocation = design_module.get("allocation")
        masking = design_module.get("masking")
        masking_description = design_module.get("maskingDescription")
        primary_purpose = design_module.get("primaryPurpose")
        intervention_model = design_module.get("interventionModel")
        time_perspective = design_module.get("timePerspective")
        observational_model = design_module.get("observationalModel")
        
        return TrialDesign(
            allocation=allocation,
            masking=masking,
            masking_description=masking_description,
            primary_purpose=primary_purpose,
            intervention_model=intervention_model,
            time_perspective=time_perspective,
            observational_model=observational_model
        )

    def _extract_interventions(self, ps: Dict[str, Any]) -> List[Intervention]:
        """Extract intervention information."""
        interventions = []
        arms_interventions = ps.get("armsInterventionsModule", {}) or {}
        
        for item in arms_interventions.get("interventions", []) or []:
            name = item.get("name", "")
            type_str = item.get("type", "").upper()
            
            # Map intervention type to enum
            intervention_type = InterventionType.OTHER
            if type_str == "DRUG":
                intervention_type = InterventionType.DRUG
            elif type_str == "BIOLOGICAL":
                intervention_type = InterventionType.BIOLOGICAL
            elif type_str == "DEVICE":
                intervention_type = InterventionType.DEVICE
            elif type_str == "PROCEDURE":
                intervention_type = InterventionType.PROCEDURE
            elif type_str == "RADIATION":
                intervention_type = InterventionType.RADIATION
            elif type_str == "BEHAVIORAL":
                intervention_type = InterventionType.BEHAVIORAL
            elif type_str == "GENETIC":
                intervention_type = InterventionType.GENETIC
            elif type_str == "DIETARY_SUPPLEMENT":
                intervention_type = InterventionType.DIETARY_SUPPLEMENT
            elif type_str == "COMBINATION_PRODUCT":
                intervention_type = InterventionType.COMBINATION_PRODUCT
            elif type_str == "DIAGNOSTIC_TEST":
                intervention_type = InterventionType.DIAGNOSTIC_TEST
            
            description = item.get("description")
            arm_labels = item.get("armLabels", []) or []
            other_names = item.get("otherNames", []) or []
            
            # Extract drug codes if available
            drug_codes = []
            if item.get("drugCodes"):
                for code in item.get("drugCodes", []):
                    if isinstance(code, dict):
                        drug_codes.append(code.get("code", ""))
                    else:
                        drug_codes.append(str(code))
            
            interventions.append(Intervention(
                name=name,
                type=intervention_type,
                description=description,
                arm_labels=arm_labels,
                other_names=other_names,
                drug_codes=drug_codes
            ))
        
        return interventions

    def _extract_conditions(self, ps: Dict[str, Any]) -> List[Condition]:
        """Extract condition information."""
        conditions = []
        conditions_module = ps.get("conditionsModule", {}) or {}
        
        for item in conditions_module.get("conditions", []) or []:
            name = item.get("name", "")
            mesh_terms = item.get("meshTerms", []) or []
            synonyms = item.get("synonyms", []) or []
            
            conditions.append(Condition(
                name=name,
                mesh_terms=mesh_terms,
                synonyms=synonyms
            ))
        
        return conditions

    def _extract_outcomes(self, ps: Dict[str, Any], outcome_type: str) -> List[Outcome]:
        """Extract outcome information."""
        outcomes = []
        outcomes_module = ps.get("outcomesModule", {}) or {}
        
        for item in outcomes_module.get(outcome_type, []) or []:
            measure = item.get("measure", "")
            description = item.get("description")
            time_frame = item.get("timeFrame")
            unit_of_measure = item.get("unitOfMeasure")
            safety_issue = item.get("safetyIssue", False)
            
            outcomes.append(Outcome(
                measure=measure,
                description=description,
                time_frame=time_frame,
                type=outcome_type.upper().replace("OUTCOMES", ""),
                unit_of_measure=unit_of_measure,
                safety_issue=safety_issue
            ))
        
        return outcomes

    def _extract_enrollment_info(self, ps: Dict[str, Any]) -> EnrollmentInfo:
        """Extract enrollment information."""
        design_module = ps.get("designModule", {}) or {}
        enrollment_info = design_module.get("enrollmentInfo", {}) or {}
        
        count = enrollment_info.get("count")
        type_str = enrollment_info.get("type")
        age_min = enrollment_info.get("minimumAge")
        age_max = enrollment_info.get("maximumAge")
        age_unit = enrollment_info.get("ageUnit")
        sex = enrollment_info.get("sex")
        healthy_volunteers = enrollment_info.get("healthyVolunteers")
        
        return EnrollmentInfo(
            count=count,
            type=type_str,
            age_min=age_min,
            age_max=age_max,
            age_unit=age_unit,
            sex=sex,
            healthy_volunteers=healthy_volunteers
        )

    def _extract_eligibility_criteria(self, ps: Dict[str, Any]) -> Optional[str]:
        """Extract eligibility criteria."""
        eligibility_module = ps.get("eligibilityModule", {}) or {}
        return eligibility_module.get("eligibilityCriteria")

    def _extract_statistical_analysis(self, ps: Dict[str, Any]) -> StatisticalAnalysis:
        """Extract statistical analysis information."""
        analysis_module = ps.get("analysisModule", {}) or {}
        
        analysis_plan = analysis_module.get("analysisPlan")
        statistical_method = analysis_module.get("statisticalMethod")
        alpha_level = analysis_module.get("alphaLevel")
        power = analysis_module.get("power")
        sample_size_calculation = analysis_module.get("sampleSizeCalculation")
        interim_analyses = analysis_module.get("interimAnalyses")
        multiplicity_adjustment = analysis_module.get("multiplicityAdjustment")
        
        return StatisticalAnalysis(
            analysis_plan=analysis_plan,
            statistical_method=statistical_method,
            alpha_level=alpha_level,
            power=power,
            sample_size_calculation=sample_size_calculation,
            interim_analyses=interim_analyses,
            multiplicity_adjustment=multiplicity_adjustment
        )

    def _extract_status_and_dates(self, ps: Dict[str, Any]) -> Tuple[Optional[TrialStatus], Dict[str, Optional[date]]]:
        """Extract status and dates."""
        status_module = ps.get("statusModule", {}) or {}
        
        status_str = status_module.get("overallStatus")
        status = None
        if status_str:
            status_upper = status_str.upper()
            status_mapping = {
                "ACTIVE_NOT_RECRUITING": TrialStatus.ACTIVE_NOT_RECRUITING,
                "COMPLETED": TrialStatus.COMPLETED,
                "ENROLLING_BY_INVITATION": TrialStatus.ENROLLING_BY_INVITATION,
                "NOT_YET_RECRUITING": TrialStatus.NOT_YET_RECRUITING,
                "RECRUITING": TrialStatus.RECRUITING,
                "SUSPENDED": TrialStatus.SUSPENDED,
                "TERMINATED": TrialStatus.TERMINATED,
                "WITHDRAWN": TrialStatus.WITHDRAWN
            }
            status = status_mapping.get(status_upper, TrialStatus.UNKNOWN)
        
        # Extract dates
        first_posted = _parse_date((status_module.get("studyFirstPostDateStruct") or {}).get("date"))
        last_update = _parse_date((status_module.get("lastUpdatePostDateStruct") or {}).get("date"))
        study_start = _parse_date((status_module.get("startDateStruct") or {}).get("date"))
        primary_completion = _parse_date((status_module.get("primaryCompletionDateStruct") or {}).get("date"))
        study_completion = _parse_date((status_module.get("completionDateStruct") or {}).get("date"))
        
        dates = {
            "first_posted": first_posted,
            "last_update": last_update,
            "study_start": study_start,
            "primary_completion": primary_completion,
            "study_completion": study_completion
        }
        
        return status, dates

    def _extract_locations(self, ps: Dict[str, Any]) -> List[Location]:
        """Extract location information."""
        locations = []
        locations_module = ps.get("locationsModule", {}) or {}
        
        for item in locations_module.get("facilities", []) or []:
            facility_name = item.get("facility", "")
            city = item.get("city")
            state = item.get("state")
            country = item.get("country")
            zip_code = item.get("zipCode")
            status = item.get("status")
            
            locations.append(Location(
                facility_name=facility_name,
                city=city,
                state=state,
                country=country,
                zip_code=zip_code,
                status=status
            ))
        
        return locations

    def _extract_keywords(self, ps: Dict[str, Any]) -> List[str]:
        """Extract keywords."""
        identification = ps.get("identificationModule", {}) or {}
        return identification.get("keywords", []) or []

    def _extract_mesh_terms(self, ps: Dict[str, Any]) -> List[str]:
        """Extract MeSH terms."""
        conditions_module = ps.get("conditionsModule", {}) or {}
        mesh_terms = []
        
        for condition in conditions_module.get("conditions", []) or []:
            terms = condition.get("meshTerms", []) or []
            mesh_terms.extend(terms)
        
        return list(set(mesh_terms))  # Remove duplicates

    def _extract_study_documents(self, ps: Dict[str, Any]) -> List[str]:
        """Extract study document references."""
        documents_module = ps.get("documentsModule", {}) or {}
        documents = []
        
        for doc in documents_module.get("documents", []) or []:
            url = doc.get("url")
            if url:
                documents.append(url)
        
        return documents

    # -----------------------------
    # Optional HTML history scrape
    # -----------------------------
    def fetch_history_metadata(self, nct_id: str) -> List[dict]:
        url = f"https://clinicaltrials.gov/study/{nct_id}?tab=history"
        resp = self.session.get(url, timeout=30)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("table tbody tr")
        versions: List[dict] = []
        for idx, row in enumerate(rows, start=1):
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if not cols:
                continue
            submitted = _parse_date(cols[0] if cols else None)
            link = row.find("a", href=True)
            versions.append(
                {"version_rank": idx, "submitted_date": submitted, "url": link["href"] if link else None}
            )
        return versions


def _sha256_canonical(obj: dict) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# -----------------------------
# Quick CLI to sanity-check API
# -----------------------------
def _main() -> None:
    since_env = os.getenv("CTG_SINCE")
    page_size_env = os.getenv("CTG_PAGE_SIZE")
    since = _parse_date(since_env) if since_env else None
    page_size = int(page_size_env) if page_size_env else 10

    c = CtgovClient()
    seen = 0
    for st in c.iter_studies(since=since, page_size=page_size):
        fields = c.extract_fields(st)
        print(fields.nct_id, fields.phase, fields.status, fields.intervention_types, fields.last_update_posted_date)
        seen += 1
        if seen >= max(page_size, 20):  # don’t spam terminal
            break

    if seen == 0:
        print("No studies matched (after client-side filtering). Try widening CTG_SINCE or page size.")


if __name__ == "__main__":
    _main()
