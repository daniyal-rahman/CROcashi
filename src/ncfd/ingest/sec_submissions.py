# src/ncfd/ingest/sec_submissions.py
from __future__ import annotations
import os, json, glob
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from ncfd.db.models import CompanyAlias
from ncfd.mapping.normalize import norm_name  # same normalizer as models

@dataclass(frozen=True)
class FormerNameRow:
    cik: int
    name: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    source_url: Optional[str] = None

def iter_sec_submissions_former_names(paths: Iterable[str]) -> Iterable[FormerNameRow]:
    """
    Yield FormerNameRow from SEC 'company submissions' JSON files.
    Accepts any iterable of file paths (*.json).
    Expects JSON with keys:
      - cik or cik_str
      - formerNames: [{"name": "...", "from": "YYYYMMDD", "to": "YYYYMMDD"}, ...]
    """
    for path in paths:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            continue

        cik_raw = data.get("cik") or data.get("cik_str")
        if cik_raw is None:
            continue
        try:
            cik = int(str(cik_raw))
        except Exception:
            continue

        arr = data.get("formerNames") or data.get("former_names") or []
        for obj in arr:
            name = (obj.get("name") or "").strip()
            if not name:
                continue
            yield FormerNameRow(
                cik=cik,
                name=name,
                date_from=obj.get("from"),
                date_to=obj.get("to"),
                source_url=data.get("filings", {}).get("recent", {}).get("accessionNumber", [None])[0],
            )

def ingest_former_names(
    session: Session,
    rows: Iterable[FormerNameRow],
    *,
    source: str = "sec_submissions",
) -> Dict[str, int]:
    """
    Upsert former names into company_aliases for companies we already have by CIK.
    Uses (company_id, alias_norm, alias_type) ON CONFLICT DO NOTHING.
    Returns counters.
    """
    inserted = skipped = missing_cik = 0

    for r in rows:
        cid = session.execute(
            text("SELECT company_id FROM companies WHERE cik = :cik"),
            {"cik": r.cik},
        ).scalar_one_or_none()
        if not cid:
            missing_cik += 1
            continue

        alias_norm = norm_name(r.name)
        if not alias_norm:
            skipped += 1
            continue

        stmt = (
            insert(CompanyAlias.__table__)
            .values(
                company_id=cid,
                alias=r.name,
                alias_norm=alias_norm,
                alias_type="former_name",
                source=source,
                source_url=r.source_url,
                metadata={"from": r.date_from, "to": r.date_to},
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CompanyAlias.__table__.c.company_id,
                    CompanyAlias.__table__.c.alias_norm,
                    CompanyAlias.__table__.c.alias_type,
                ]
            )
            .returning(CompanyAlias.__table__.c.alias_id)
        )
        res = session.execute(stmt).fetchone()
        if res:
            inserted += 1
        else:
            skipped += 1

    return {"inserted": inserted, "skipped": skipped, "missing_cik": missing_cik}

# ------------------------------ tiny CLI ------------------------------------

if __name__ == "__main__":
    import argparse
    from sqlalchemy.orm import sessionmaker
    from ncfd.db.session import get_engine

    ap = argparse.ArgumentParser(description="Ingest former names from SEC company submissions JSON files")
    ap.add_argument("--dir", required=True, help="Directory containing SEC submissions JSON files (CIK*.json)")
    args = ap.parse_args()

    paths = glob.glob(os.path.join(args.dir, "*.json"))
    Session = sessionmaker(bind=get_engine())
    s = Session()
    stats = ingest_former_names(s, iter_sec_submissions_former_names(paths))
    s.commit()
    print(stats)
