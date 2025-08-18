# tests/test_sec_ingest.py
import os
from datetime import date
import json
import tempfile

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ncfd.ingest.exchanges import ExchangeRow, upsert_exchanges
from ncfd.ingest.sec import ingest_sec_rows, SecCompanyRow

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

def _xnas_id(conn):
    return conn.execute(text("SELECT exchange_id FROM exchanges WHERE code='NASDAQ'")).scalar_one()

def setup_function(_f):
    with engine.begin() as c:
        # clean any tickers we use in this test
        c.execute(text("DELETE FROM securities WHERE ticker_norm IN ('ACME','BETA','HKCN')"))
        c.execute(text("DELETE FROM companies WHERE cik in (9111111111, 9222222222, 9333333333)"))
        # ensure whitelist present (seed migration already does, but be explicit)
        upsert_exchanges(Session(bind=c), [
            ExchangeRow(code="NASDAQ", mic="XNAS", name="NASDAQ", country="US", is_allowed=True),
            ExchangeRow(code="NYSE",   mic="XNYS", name="NYSE",   country="US", is_allowed=True),
            ExchangeRow(code="NYSE American", mic="XASE", name="NYSE American", country="US", is_allowed=True),
            ExchangeRow(code="HKX", mic="XHKX", name="HK Test", country="HK", is_allowed=False),
        ])

def test_ingest_basic_and_unique_active():
    rows = [
        SecCompanyRow(cik=9111111111, ticker="ACME", title="Acme Bio Inc.", exchange="Nasdaq"),
        SecCompanyRow(cik=9222222222, ticker="BETA", title="Beta Tx Inc.", exchange="NYSE"),
        # duplicate ticker ACME moving to a different CIK later in time
        SecCompanyRow(cik=9222222222, ticker="ACME", title="Beta Tx Inc.", exchange="NYSE"),
    ]
    with Session(engine) as s, s.begin():
        stats = ingest_sec_rows(s, rows, default_start=date(2000, 1, 1))
        assert stats["activated"] == 3  # three insert attempts executed

    with engine.begin() as c:
        # ACME should have two spans, non-overlapping, and only one 'active'
        spans = c.execute(text("""
            SELECT company_id, status::text,
                   lower(effective_range)::date AS lo,
                   upper(effective_range)::date AS hi
            FROM securities WHERE ticker_norm='ACME' ORDER BY lo
        """)).all()
        assert len(spans) == 2
        active_count = c.execute(text("""
            SELECT COUNT(*) FROM securities
            WHERE ticker_norm='ACME' AND status='active'
        """)).scalar_one()
        assert active_count == 1

def test_cn_hk_excluded():
    rows = [
        SecCompanyRow(cik=9333333333, ticker="HKCN", title="HK CN Co", exchange="HKX"),
    ]
    with Session(engine) as s, s.begin():
        stats = ingest_sec_rows(s, rows)
        assert stats["skipped"] >= 1

    with engine.begin() as c:
        cnt = c.execute(text("SELECT COUNT(*) FROM securities WHERE ticker_norm='HKCN'")).scalar_one()
        assert cnt == 0
