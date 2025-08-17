#!/usr/bin/env python
import os, sys, json
from pathlib import Path
from datetime import date
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ncfd.ingest.ctgov import CtgovClient, _parse_date  # type: ignore

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
    for raw in client.iter_studies(since=since, page_size=page_size):
        f = client.extract_fields(raw)
        print(json.dumps({
            "nct_id": f.nct_id,
            "phase": f.phase,
            "status": f.status,
            "types": f.intervention_types,
            "n": f.sample_size,
            "pep": f.primary_endpoint_text,
            "last_update": f.last_update_posted_date.isoformat() if f.last_update_posted_date else None,
        }, ensure_ascii=False))
        count += 1
        if f.last_update_posted_date and (max_seen is None or f.last_update_posted_date > max_seen):
            max_seen = f.last_update_posted_date
        # if count >= page_size:  # keep it polite for smoke runs; remove if you want full paging
        #     break

    save_cursor(max_seen)
    print(f"\nOK: printed {count} studies; cursor now {max_seen.isoformat() if max_seen else 'unset'}")

if __name__ == "__main__":
    main()
