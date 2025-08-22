import os
import datetime as dt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

@pytest.fixture(autouse=True)
def clean():
    # Minimal cleanup; each test runs in its own transaction via begin()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM company_aliases"))
        conn.execute(text("DELETE FROM securities"))
        conn.execute(text("DELETE FROM companies WHERE cik >= 9000000000"))
        # exchanges are seeded by migration; leave them

def _id(conn, sql, **p):
    return conn.execute(text(sql), p).scalar_one()

def test_company_name_normalization():
    with engine.begin() as conn:
        cid = _id(conn, """
            INSERT INTO companies (cik, name, name_norm)
            VALUES (9000000001, 'Acme Therapeutics, Inc.', 'tmp') RETURNING company_id
        """)
        # ORM hooks don't run on raw SQL, so simulate update via SQL to trigger DB-side check:
        # We'll now update via ORM path to hit the mapper events.
    from ncfd.db.models import Company
    with Session(engine) as s, s.begin():
        c = s.get(Company, cid)
        c.name = "  Ácme   Therapeutics,   Inc.  "
        # mapper event should rewrite name_norm
    with engine.begin() as conn:
        (nn,) = conn.execute(text("SELECT name_norm FROM companies WHERE company_id=:cid"), {"cid": cid}).one()
        assert nn == "acme therapeutics"  # suffixes removed, normalized spacing/case

def test_alias_normalization():
    from ncfd.db.models import Company, CompanyAlias
    with Session(engine) as s, s.begin():
        c = Company(cik=9000000002, name="Foobar Biopharma Inc.", name_norm="x")
        s.add(c); s.flush()
        a = CompanyAlias(company_id=c.company_id, alias="Foobar Biopharma, Inc.", alias_norm="x", alias_type="aka")
        s.add(a)
    with engine.begin() as conn:
        (an,) = conn.execute(text("""
            SELECT alias_norm FROM company_aliases
            WHERE company_id=(SELECT company_id FROM companies WHERE cik=9000000002)
        """)).one()
        assert an == "foobar biopharma"

def test_ticker_normalization_and_check():
    from ncfd.db.models import Company, Security, Exchange
    with Session(engine) as s, s.begin():
        # Ensure NASDAQ exists
        xnas_id = s.execute(text("SELECT exchange_id FROM exchanges WHERE code='NASDAQ'")).scalar_one()
        c = Company(cik=9000000003, name="Zeta Corp", name_norm="zeta")
        s.add(c); s.flush()
        # Lowercase ticker -> should be uppercased into ticker_norm by event
        sec = Security(
            company_id=c.company_id,
            exchange_id=xnas_id,
            ticker="znbi",
            ticker_norm="tmp",
            status="active",
            effective_range= "[2025-01-01,)",  # Postgres range literal
        )
        s.add(sec)

    with engine.begin() as conn:
        (tn,) = conn.execute(text("SELECT ticker_norm FROM securities WHERE ticker='znbi'")).one()
        assert tn == "ZNBI"  # event uppercased it

    # And DB check constraint enforces equality with upper(ticker)
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO securities(company_id,exchange_id,ticker,ticker_norm,status,effective_range)
                VALUES (
                  (SELECT company_id FROM companies WHERE cik=9000000003),
                  (SELECT exchange_id FROM exchanges WHERE code='NASDAQ'),
                  'ZZZ', 'zzz', 'active', daterange('2025-01-01', NULL, '[)')
                )
            """))
