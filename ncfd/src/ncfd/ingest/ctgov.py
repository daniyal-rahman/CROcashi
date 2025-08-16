"""Client utilities for the ClinicalTrials.gov v2 API.

This module intentionally focuses on network interactions only.  It knows how to
page through the public API and extract a few normalized fields from the study
records.  Persistence, hashing, and diffing are handled elsewhere in the code
base.  The goal is to provide a clean surface for higher level ingest
orchestration without coupling to the database layer.

Examples
--------

```python
from ncfd.ingest.ctgov import CtgovClient

client = CtgovClient()
for raw in client.iter_studies(page_size=10):
    fields = client.extract_fields(raw)
    print(fields.nct_id, fields.phase)
```
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generator, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Return a :class:`date` from an ISO8601 string, ignoring errors."""

    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class NormalizedFields:
    """Subset of useful study fields.

    The names mirror the columns in the eventual ``trials`` table but the class
    is intentionally lightweight so that callers can decide how to persist or
    further process the data.
    """

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
    """Lightweight wrapper around the ClinicalTrials.gov API."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, session: Optional[requests.Session] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # API pagination
    # ------------------------------------------------------------------
    def iter_studies(self, since: Optional[date] = None, page_size: int = 100) -> Generator[dict, None, None]:
        """Yield raw study JSON matching our ingest criteria.

        Parameters
        ----------
        since:
            If provided, only studies with ``lastUpdatePostDate`` greater than or
            equal to this date are returned.
        page_size:
            Number of studies to request per page.  ``ClinicalTrials.gov`` caps
            this at 1,000 but we default to a conservative value.
        """

        params = {
            "filter.studyType": "INTERVENTIONAL",
            "filter.interventionTypes": "DRUG,BIOLOGICAL",
            "filter.phases": "PHASE_3,PHASE_2_PHASE_3,PHASE_2",
            "pageSize": page_size,
        }
        if since:
            params["filter.lastUpdatePostDate"] = f"GE:{since.isoformat()}"

        next_token: Optional[str] = None
        url = f"{self.base_url}/studies"

        while True:
            call_params = dict(params)
            if next_token:
                call_params["pageToken"] = next_token

            resp = self.session.get(url, params=call_params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()

            for study in payload.get("studies", []):
                yield study

            next_token = (
                payload.get("nextPageToken")
                or resp.headers.get("x-next-page-token")
                or resp.headers.get("X-Next-Page-Token")
            )
            if not next_token:
                break

    # ------------------------------------------------------------------
    # Field extraction helpers
    # ------------------------------------------------------------------
    def extract_fields(self, study: dict) -> NormalizedFields:
        """Extract a subset of normalized fields from a raw study JSON blob."""

        ps = study.get("protocolSection", {})

        identification = ps.get("identificationModule", {})
        nct_id = identification.get("nctId")

        sponsor_text = (
            ps.get("sponsorCollaboratorsModule", {})
            .get("leadSponsor", {})
            .get("name")
        )

        phases = ps.get("designModule", {}).get("phases", [])
        phase = phases[0] if phases else None

        intervention_types: List[str] = []
        for item in ps.get("armsInterventionsModule", {}).get("interventions", []):
            typ = item.get("type")
            if typ:
                intervention_types.append(typ)
        intervention_types = sorted(set(intervention_types))

        outcomes = ps.get("outcomesModule", {}).get("primaryOutcomes", [])
        parts = []
        for out in outcomes:
            measure = (out.get("measure") or "").strip()
            timeframe = (out.get("timeFrame") or "").strip()
            if measure:
                if timeframe:
                    parts.append(f"{measure} ({timeframe})")
                else:
                    parts.append(measure)
        primary_endpoint = "; ".join(parts) or None

        enrollment_info = ps.get("designModule", {}).get("enrollmentInfo", {})
        sample_size = enrollment_info.get("count")

        status_module = ps.get("statusModule", {})
        status = status_module.get("overallStatus")

        first_posted = _parse_date(status_module.get("firstPostedDate"))
        last_update = _parse_date(status_module.get("lastUpdatePostedDate"))
        est_primary_completion = _parse_date(
            (status_module.get("primaryCompletionDateStruct") or {}).get("date")
        )

        analysis_plan_text = None
        analysis_module = ps.get("analysisModule", {})
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

    # ------------------------------------------------------------------
    # Optional: fetch version history metadata
    # ------------------------------------------------------------------
    def fetch_history_metadata(self, nct_id: str) -> List[dict]:
        """Return basic version metadata from the public HTML history page.

        The ClinicalTrials.gov API does not expose full historical records.  This
        helper parses the "Record History" tab to capture submission dates and
        associated links.  The structure of the page is not guaranteed to remain
        stable; callers should tolerate an empty list.
        """

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
                {
                    "version_rank": idx,
                    "submitted_date": submitted,
                    "url": link["href"] if link else None,
                }
            )
        return versions


__all__ = ["CtgovClient", "NormalizedFields"]

