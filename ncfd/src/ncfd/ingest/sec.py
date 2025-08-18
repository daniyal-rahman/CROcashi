# src/ncfd/ingest/sec.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Any, Dict

import json
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB

from ncfd.db.models import Company
from ncfd.ingest.securities import upsert_security_active, ExchangeNotAllowed


# -----------------------------------------------------------------------------
# Data model for ingest
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SecCompanyRow:
    cik: int
    ticker: str
    title: str
    exchange: Optional[str]  # e.g., "Nasdaq", "NYSE", "NYSE American", "OTCQX", ...


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

# Normalize various SEC spellings into our exchanges.code
_EXCHANGE_NAME_TO_CODE = {
    # NASDAQ variants
    "nasdaq": "NASDAQ",
    "nasdaqgs": "NASDAQ",
    "nasdaqgm": "NASDAQ",
    "nasdaqcm": "NASDAQ",
    "nasdaqg": "NASDAQ",
    "nasdaq global select market": "NASDAQ",
    "nasdaq global market": "NASDAQ",
    "nasdaq capital market": "NASDAQ",

    # NYSE variants
    "nyse": "NYSE",
    "new york stock exchange": "NYSE",

    # NYSE American / AMEX variants
    "nyse american": "NYSE American",
    "nyse mkt": "NYSE American",
    "nyse mkt llc": "NYSE American",
    "amex": "NYSE American",

    # OTC (only QX/QB are allowed in your whitelist)
    "otcqx": "OTCQX",
    "otcqx u.s.": "OTCQX",
    "otcqx u.s.a.": "OTCQX",
    "otcqb": "OTCQB",
    "otcqb u.s.": "OTCQB",
}

def _normalize_exchange_code(exchange_name: Optional[str]) -> Optional[str]:
    if not exchange_name:
        return None
    key = str(exchange_name).strip().lower()
    return _EXCHANGE_NAME_TO_CODE.get(key)


def _get_or_create_company(session: Session, *, cik: int, name: str) -> tuple[int, bool]:
    """
    Returns (company_id, created_bool). Uses ORM so name_norm is set by events.
    """
    cid = session.execute(
        text("SELECT company_id FROM companies WHERE cik = :cik"),
        {"cik": cik},
    ).scalar()
    if cid:
        c = session.get(Company, cid)
        if c and c.name != name:
            c.name = name  # ORM events will re-normalize name_norm
        return int(cid), False

    c = Company(cik=cik, name=name, name_norm=name)
    session.add(c)
    session.flush()
    return int(c.company_id), True


# -----------------------------------------------------------------------------
# Public ingest
# -----------------------------------------------------------------------------

def ingest_sec_rows(
    session: Session,
    rows: Iterable[SecCompanyRow],
    *,
    default_start: date = date(1900, 1, 1),
    skip_missing_exchange: bool = True,
) -> Dict[str, int]:
    """
    Upsert companies + create/maintain active security per ticker for allowed exchanges.

    - Resolves/validates exchange against whitelist (via exchanges table).
    - Closes prior ticker ranges automatically (via upsert_security_active).
    - Skips rows with missing or disallowed exchanges if configured.

    Returns counters: {"inserted_companies", "updated_companies", "activated", "skipped"}.
    """
    inserted_companies = updated_companies = activated = skipped = 0

    for r in rows:
        ex_code = _normalize_exchange_code(r.exchange)
        if not ex_code:
            if skip_missing_exchange:
                skipped += 1
                continue

        try:
            cid, created = _get_or_create_company(session, cik=int(r.cik), name=r.title)
            if created:
                inserted_companies += 1
            else:
                updated_companies += 1

            # Maintain an active listing for the ticker on the mapped exchange
            upsert_security_active(
                session,
                company_id=cid,
                exchange_code=ex_code,
                ticker=r.ticker,
                effective_date=default_start,
                sec_type="common",
                currency="USD",
                cik=r.cik,
                metadata={"source": "sec_company_tickers"},
            )
            activated += 1

        except ExchangeNotAllowed:
            # Exchange exists but is not allowed in whitelist
            skipped += 1

    return {
        "inserted_companies": inserted_companies,
        "updated_companies": updated_companies,
        "activated": activated,
        "skipped": skipped,
    }


# -----------------------------------------------------------------------------
# Loaders (offline-friendly)
# -----------------------------------------------------------------------------

def load_sec_company_tickers_json(path: str) -> Iterable[SecCompanyRow]:
    """
    Load from a local JSON file with SEC-like structure.

    Supports:
      1) Tabular format (current official):
         {"fields": ["cik","name","ticker","exchange",...],
          "data": [[..., ...], ...]}
      2) Dict-of-dicts:
         {"0":{"cik_str":...,"ticker":"...","title":"...","exchange":"Nasdaq"}, ...}
      3) List-of-dicts:
         [{"cik":...,"ticker":"...","title":"...","exchange":"..."}, ...]
    """
    with open(path, "r") as f:
        data = json.load(f)

    # Case 1: "fields"+"data" tabular format (array-of-arrays)
    if isinstance(data, dict) and isinstance(data.get("fields"), list) and isinstance(data.get("data"), list):
        fields = [str(x).strip().lower() for x in data["fields"]]

        def col(*names: str) -> Optional[int]:
            for n in names:
                if n in fields:
                    return fields.index(n)
            return None

        i_cik   = col("cik", "cik_str")
        i_name  = col("name", "title")
        i_tick  = col("ticker", "tickers")
        i_exchg = col("exchange", "exch", "exchange_short")

        if i_cik is None or i_tick is None or i_name is None:
            raise ValueError("SEC tabular JSON missing required columns (need cik/name/ticker)")

        for row in data["data"]:
            if not isinstance(row, (list, tuple)):
                continue
            cik = int(str(row[i_cik]))
            title = str(row[i_name]) if row[i_name] is not None else ""
            ticker = str(row[i_tick]) if row[i_tick] is not None else ""
            exchange = str(row[i_exchg]) if (i_exchg is not None and row[i_exchg] is not None) else None
            yield SecCompanyRow(cik=cik, ticker=ticker, title=title, exchange=exchange)
        return

    # Case 2: dict-of-dicts
    if isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
        for obj in data.values():
            yield SecCompanyRow(
                cik=int(obj.get("cik") or obj.get("cik_str")),
                ticker=str(obj.get("ticker")),
                title=str(obj.get("title") or obj.get("name") or ""),
                exchange=obj.get("exchange"),
            )
        return

    # Case 3: list-of-dicts
    if isinstance(data, list):
        for obj in data:
            yield SecCompanyRow(
                cik=int(obj.get("cik") or obj.get("cik_str")),
                ticker=str(obj.get("ticker")),
                title=str(obj.get("title") or obj.get("name") or ""),
                exchange=obj.get("exchange"),
            )
        return

    raise ValueError("Unrecognized JSON schema for SEC tickers")


def ingest_sec_company_tickers_from_file(
    session: Session,
    json_path: str,
    *,
    default_start: date = date(1900, 1, 1),
) -> Dict[str, int]:
    rows = load_sec_company_tickers_json(json_path)
    return ingest_sec_rows(session, rows, default_start=default_start)


# -----------------------------------------------------------------------------
# Optional tiny CLI for convenience
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from sqlalchemy.orm import sessionmaker
    from ncfd.db.session import get_engine

    ap = argparse.ArgumentParser(description="Ingest SEC company tickers JSON into companies + securities")
    ap.add_argument("--json", required=True, help="Path to SEC company_tickers_exchange.json")
    ap.add_argument("--start", default="1900-01-01", help="Effective start date for active listings (YYYY-MM-DD)")
    args = ap.parse_args()

    Session = sessionmaker(bind=get_engine())
    s = Session()
    stats = ingest_sec_company_tickers_from_file(s, args.json, default_start=date.fromisoformat(args.start))
    s.commit()
    print(stats)
