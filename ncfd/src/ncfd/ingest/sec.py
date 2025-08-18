# src/ncfd/ingest/sec.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Any, Dict

import json
import os

from sqlalchemy import text, select
from sqlalchemy.orm import Session

from ncfd.db.models import Company
from ncfd.ingest.securities import upsert_security_active, ExchangeNotAllowed


# ---- Rows we expect from SEC ----
# We target the "company_tickers_exchange.json" schema when online,
# but the ingest accepts any iterable of SecCompanyRow below.

@dataclass(frozen=True)
class SecCompanyRow:
    cik: int
    ticker: str
    title: str
    exchange: Optional[str]  # "Nasdaq", "NYSE", "NYSE American", etc.


# ---- Helpers ----

_EXCHANGE_NAME_TO_CODE = {
    # normalize various SEC spellings into our 'exchanges.code'
    "nasdaq": "NASDAQ",
    "nasdaqgs": "NASDAQ",
    "nasdaqgm": "NASDAQ",
    "nasdaqg": "NASDAQ",
    "nyse": "NYSE",
    "nyse american": "NYSE American",
    "amex": "NYSE American",
}

def _normalize_exchange_code(exchange_name: Optional[str]) -> Optional[str]:
    if not exchange_name:
        return None
    return _EXCHANGE_NAME_TO_CODE.get(str(exchange_name).strip().lower())


def _get_or_create_company(session: Session, *, cik: int, name: str) -> int:
    # try fast path by CIK
    cid = session.execute(
        text("SELECT company_id FROM companies WHERE cik = :cik"),
        {"cik": cik},
    ).scalar()
    if cid:
        # Optional: update name if it changed (ORM events will re-normalize name_norm)
        c = session.get(Company, cid)
        if c and c.name != name:
            c.name = name
        return int(cid)

    # create via ORM so our normalization hook runs
    c = Company(cik=cik, name=name, name_norm=name)
    session.add(c)
    session.flush()
    return int(c.company_id)


# ---- Public ingest ----

def ingest_sec_rows(
    session: Session,
    rows: Iterable[SecCompanyRow],
    *,
    default_start: date = date(1900, 1, 1),
    skip_missing_exchange: bool = True,
) -> Dict[str, int]:
    """
    Upsert companies + create/maintain active security per ticker for allowed exchanges.

    - Resolves/validates exchange against whitelist.
    - Closes prior ticker ranges automatically (via upsert_security_active).
    - Skips rows with missing or disallowed exchanges.

    Returns counters: {"inserted_companies": n, "updated_companies": m, "activated": k, "skipped": s}
    """
    inserted_companies = updated_companies = activated = skipped = 0

    for r in rows:
        ex_code = _normalize_exchange_code(r.exchange)
        if not ex_code:
            if skip_missing_exchange:
                skipped += 1
                continue
        try:
            cid = _get_or_create_company(session, cik=int(r.cik), name=r.title)
            # crude updated/inserted accounting
            # (if company existed, _get_or_create_company didn't add; else it did)
            # We can detect by querying after flush
            # but here we'll approximate by: is present in session.new ?
            if any(isinstance(obj, Company) and obj.company_id == cid for obj in session.new):
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
            skipped += 1

    return {
        "inserted_companies": inserted_companies,
        "updated_companies": updated_companies,
        "activated": activated,
        "skipped": skipped,
    }


# ---- Optional: fetchers (offline-friendly) ----

def load_sec_company_tickers_json(path: str) -> Iterable[SecCompanyRow]:
    """
    Load from a local JSON file with SEC-like structure.

    Supports:
      - {"0":{"cik_str":..., "ticker":"...", "title":"...", "exchange":"Nasdaq"}, ...}
      - [{"cik":..., "ticker":"...", "title":"...", "exchange":"..."}, ...]
    """
    with open(path, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
        # SEC's company_tickers_exchange.json style
        for obj in data.values():
            yield SecCompanyRow(
                cik=int(obj.get("cik") or obj.get("cik_str")),
                ticker=str(obj["ticker"]),
                title=str(obj["title"]),
                exchange=obj.get("exchange"),
            )
    elif isinstance(data, list):
        for obj in data:
            yield SecCompanyRow(
                cik=int(obj.get("cik") or obj.get("cik_str")),
                ticker=str(obj["ticker"]),
                title=str(obj["title"]),
                exchange=obj.get("exchange"),
            )
    else:
        raise ValueError("Unrecognized JSON schema for SEC tickers")


def ingest_sec_company_tickers_from_file(
    session: Session,
    json_path: str,
    *,
    default_start: date = date(1900, 1, 1),
) -> Dict[str, int]:
    rows = load_sec_company_tickers_json(json_path)
    return ingest_sec_rows(session, rows, default_start=default_start)
