"""
Lightweight ClinicalTrials.gov v2 client focused on interventional drug/biologic Ph 2/3.
Server-side filter: date (LastUpdatePostDate). All other filters are client-side for stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generator, Iterable, List, Optional, Tuple
import hashlib
import json
import os
import sys
import time

import requests
from bs4 import BeautifulSoup

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
        while True:
            call = dict(params)
            if next_token:
                call["pageToken"] = next_token

            resp = self.session.get(url, params=call, timeout=45)
            # retry once on transient 5xx
            if resp.status_code >= 500:
                time.sleep(1.0)
                resp = self.session.get(url, params=call, timeout=45)
            resp.raise_for_status()

            data = resp.json()
            studies = data.get("studies", [])
            for st in studies:
                yield st

            next_token = data.get("nextPageToken") or resp.headers.get("x-next-page-token") or resp.headers.get("X-Next-Page-Token")
            if not next_token:
                break

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
        ps = study.get("protocolSection", {}) or {}
        identification = ps.get("identificationModule", {}) or {}
        nct_id = identification.get("nctId")

        sponsor_text = (
            ps.get("sponsorCollaboratorsModule", {}) or {}
        ).get("leadSponsor", {}) or {}
        sponsor_text = sponsor_text.get("name")

        phases = ps.get("designModule", {}).get("phases", []) or []
        phase = phases[0] if phases else None

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
