#!/usr/bin/env python
import os, sys, json, hashlib
from pathlib import Path
from datetime import date, datetime
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ncfd.ingest.ctgov import CtgovClient, _parse_date  # type: ignore
from ncfd.db.session import session_scope
from ncfd.db.models import Trial, TrialVersion

STATE_DIR = Path(".state")
CURSOR_PATH = STATE_DIR / "ctgov_cursor.txt"

def load_cursor() -> Optional[date]:
    env = os.getenv("CTG_SINCE")
    if env:
        return _parse_date(env)
    if CURSOR_PATH.exists():
        txt = CURSOR_PATH.read_text().strip()
        return _parse_date(txt)
    return None

def save_cursor(d: Optional[date]) -> None:
    if not d:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(d.isoformat() + "\n")

def main():
    since = load_cursor()
    page_size = int(os.getenv("CTG_PAGE_SIZE", "50"))
    client = CtgovClient()

    max_seen = since
    count = 0
    with session_scope() as session:
        for raw in client.iter_studies(since=since, page_size=page_size):
            f = client.extract_fields(raw)
            
            raw_json_str = json.dumps(raw, sort_keys=True, ensure_ascii=False)
            sha256 = hashlib.sha256(raw_json_str.encode("utf-8")).hexdigest()

            trial = session.query(Trial).filter(Trial.nct_id == f.nct_id).one_or_none()

            if not trial:
                trial = Trial(
                    nct_id=f.nct_id,
                    sponsor_text=f.sponsor_text,
                    phase=f.phase,
                    status=f.status,
                    primary_endpoint_text=f.primary_endpoint_text,
                    first_posted_date=f.first_posted_date,
                    last_update_posted_date=f.last_update_posted_date,
                    intervention_types=f.intervention_types,
                    current_sha256=sha256,
                    last_seen_at=datetime.utcnow()
                )
                session.add(trial)
                trial_version = TrialVersion(
                    trial=trial,
                    raw_jsonb=raw,
                    sha256=sha256,
                    last_update_posted_date=f.last_update_posted_date,
                    primary_endpoint_text=f.primary_endpoint_text,
                    sample_size=f.sample_size
                )
                trial.versions.append(trial_version)

            elif trial.current_sha256 != sha256:
                trial.sponsor_text = f.sponsor_text
                trial.phase = f.phase
                trial.status = f.status
                trial.primary_endpoint_text = f.primary_endpoint_text
                trial.first_posted_date = f.first_posted_date
                trial.last_update_posted_date = f.last_update_posted_date
                trial.intervention_types = f.intervention_types
                trial.current_sha256 = sha256
                trial.last_seen_at = datetime.utcnow()

                trial_version = TrialVersion(
                    trial=trial,
                    raw_jsonb=raw,
                    sha256=sha256,
                    last_update_posted_date=f.last_update_posted_date,
                    primary_endpoint_text=f.primary_endpoint_text,
                    sample_size=f.sample_size
                )
                trial.versions.append(trial_version)

            count += 1
            if f.last_update_posted_date and (max_seen is None or f.last_update_posted_date > max_seen):
                max_seen = f.last_update_posted_date
            # if count >= page_size:  # keep it polite for smoke runs; remove if you want full paging
            #     break

    save_cursor(max_seen)
    print(f"\nOK: processed {count} studies; cursor now {max_seen.isoformat() if max_seen else 'unset'}")

if __name__ == "__main__":
    main()
