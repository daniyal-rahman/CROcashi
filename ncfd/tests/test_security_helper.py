import os
from datetime import date
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ncfd.ingest.exchanges import ExchangeRow, upsert_exchanges
from ncfd.ingest.securities import (
    upsert_security_active,
    deactivate_security,
    transfer_ticker_ownership,
    ExchangeNotAllowed,
)

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as c:
        c.execute(text("DELETE FROM securities WHERE ticker_norm IN ('HELPX','HELPA')"))
        c.execute(text("DELETE FROM companies WHERE cik >= 9600000000"))
        # Ensure HKX exists and is disallowed for the disallow test
        upsert_exchanges(Session(bind=c), [ExchangeRow(code="HKX", mic="XHKX", name="HK Test", country="HK", is_allowed=True)])


def _xnas_id(conn):
    return conn.execute(text("SELECT exchange_id FROM exchanges WHERE code='NASDAQ'")).scalar_one()


def test_upsert_security_active_closes_prior():
    with engine.begin() as c:
        xnas = _xnas_id(c)
        cid1 = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9600000001, 'Delta Tx Inc', 'delta tx') RETURNING company_id
        """)).scalar_one()
        cid2 = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9600000002, 'Epsilon Tx Inc', 'epsilon tx') RETURNING company_id
        """)).scalar_one()

    # First active at 2025-01-01
    with Session(engine) as s, s.begin():
        sid1 = upsert_security_active(
            s, company_id=cid1, exchange_code="NASDAQ",
            ticker="helpx", effective_date=date(2025, 1, 1)
        )
        assert isinstance(sid1, int)

    # Second active at 2025-03-01 -> should close the first at 2025-03-01
    with Session(engine) as s, s.begin():
        sid2 = upsert_security_active(
            s, company_id=cid2, exchange_code="NASDAQ",
            ticker="helpx", effective_date=date(2025, 3, 1)
        )
        assert isinstance(sid2, int)

    # Validate: two rows, non-overlapping, only one active
    with engine.begin() as c:
        rows = c.execute(text("""
            SELECT status::text, lower(effective_range)::date AS lo, upper(effective_range)::date AS hi
            FROM securities WHERE ticker_norm='HELPX' ORDER BY lo
        """)).all()
        assert len(rows) == 2
        assert rows[0]._mapping["status"] == "delisted"
        assert rows[0]._mapping["lo"] == date(2025,1,1)
        assert rows[0]._mapping["hi"] == date(2025,3,1)
        assert rows[1]._mapping["status"] == "active"
        assert rows[1]._mapping["lo"] == date(2025,3,1)
        assert rows[1]._mapping["hi"] is None

        # Unique active global should hold
        actives = c.execute(text("""
            SELECT COUNT(*) FROM securities
            WHERE ticker_norm='HELPX' AND status='active'
        """)).scalar_one()
        assert actives == 1


def test_disallowed_exchange_rejected():
    with engine.begin() as c:
        cid = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9600000003, 'Zeta Bio Inc', 'zeta bio') RETURNING company_id
        """)).scalar_one()

    with Session(engine) as s, s.begin():
        with pytest.raises(ExchangeNotAllowed):
            upsert_security_active(
                s, company_id=cid, exchange_code="HKX",
                ticker="HELPA", effective_date=date(2025, 4, 1)
            )


def test_deactivate_security_and_transfer():
    with engine.begin() as c:
        cid_a = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9600000004, 'Owner A', 'owner a') RETURNING company_id
        """)).scalar_one()
        cid_b = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9600000005, 'Owner B', 'owner b') RETURNING company_id
        """)).scalar_one()

    with Session(engine) as s, s.begin():
        upsert_security_active(
            s, company_id=cid_a, exchange_code="NASDAQ",
            ticker="HELPA", effective_date=date(2025, 1, 15)
        )

    # Deactivate mid-2025
    with Session(engine) as s, s.begin():
        n = deactivate_security(s, ticker="HELPA", end_date=date(2025, 6, 1))
        assert n >= 1

    # Transfer to B at 2025-06-01
    with Session(engine) as s, s.begin():
        sid = transfer_ticker_ownership(
            s, from_company_id=cid_a, to_company_id=cid_b,
            exchange_code="NASDAQ", ticker="HELPA", effective_date=date(2025, 6, 1)
        )
        assert isinstance(sid, int)

    with engine.begin() as c:
        spans = c.execute(text("""
            SELECT status::text, lower(effective_range)::date, upper(effective_range)::date
            FROM securities WHERE ticker_norm='HELPA' ORDER BY 2
        """)).all()
        # three rows: active(A) -> delisted(A at 6/1) -> active(B from 6/1)
        assert len(spans) == 3
        active_count = c.execute(text("""
            SELECT COUNT(*) FROM securities WHERE ticker_norm='HELPA' AND status='active'
        """)).scalar_one()
        assert active_count == 1
