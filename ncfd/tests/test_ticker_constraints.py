import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as c:
        # keep seeded exchanges; just clear our scratch rows
        c.execute(text("DELETE FROM securities WHERE ticker_norm IN ('ZZZ','QQQ')"))
        c.execute(text("DELETE FROM company_aliases WHERE company_id IN (SELECT company_id FROM companies WHERE cik >= 9500000000)"))
        c.execute(text("DELETE FROM companies WHERE cik >= 9500000000"))

def _xnas_id(conn):
    return conn.execute(text("SELECT exchange_id FROM exchanges WHERE code='NASDAQ'")).scalar_one()

def test_unique_active_ticker_global_and_time_slicing():
    with engine.begin() as c:
        xnas = _xnas_id(c)
        # do the setup in a committed txn
        cid1 = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9500000001, 'Alpha Therapeutics Inc', 'alpha therapeutics')
            RETURNING company_id
        """)).scalar_one()
        cid2 = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9500000002, 'Beta Therapeutics Inc', 'beta therapeutics')
            RETURNING company_id
        """)).scalar_one()
        c.execute(text("""
            INSERT INTO securities(company_id, exchange_id, ticker, ticker_norm, status, effective_range)
            VALUES (:cid, :xid, 'ZZZ', 'ZZZ', 'active', daterange('2025-01-01', NULL, '[)'))
        """), {"cid": cid1, "xid": xnas})

    # try the conflicting insert in a separate transaction so only that part rolls back
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO securities(company_id, exchange_id, ticker, ticker_norm, status, effective_range)
                VALUES (:cid, :xid, 'ZZZ', 'ZZZ', 'active', daterange('2025-03-01', NULL, '[)'))
            """), {"cid": cid2, "xid": xnas})

    # delist the first, then insert the second as active
    with engine.begin() as c:
        c.execute(text("""
            UPDATE securities
            SET status='delisted',
                effective_range = daterange(lower(effective_range), DATE '2025-03-01', '[)')
            WHERE ticker_norm='ZZZ'
        """))
        # now the new active row can start exactly at 2025-03-01 without overlap
        c.execute(text("""
            INSERT INTO securities(company_id, exchange_id, ticker, ticker_norm, status, effective_range)
            VALUES (:cid, :xid, 'ZZZ', 'ZZZ', 'active', daterange('2025-03-01', NULL, '[)'))
        """), {"cid": cid2, "xid": xnas})

def test_no_overlapping_ranges_for_same_ticker():
    with engine.begin() as c:
        xnas = _xnas_id(c)
        cid = c.execute(text("""
            INSERT INTO companies (cik, name, name_norm) VALUES (9500000003, 'Gamma Tx Inc', 'gamma tx')
            RETURNING company_id
        """)).scalar_one()

    # First range
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO securities(company_id, exchange_id, ticker, ticker_norm, status, effective_range)
            VALUES (:cid, :xid, 'QQQ', 'QQQ', 'delisted', daterange('2024-01-01','2024-12-31','[)'))
        """), {"cid": cid, "xid": xnas})

    # Overlapping range for same ticker should fail exclusion constraint,
    # regardless of status/company/exchange.
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO securities(company_id, exchange_id, ticker, ticker_norm, status, effective_range)
                VALUES (:cid, :xid, 'QQQ', 'QQQ', 'active', daterange('2024-06-01','2025-01-01','[)'))
            """), {"cid": cid, "xid": xnas})
