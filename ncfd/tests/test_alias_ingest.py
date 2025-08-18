# tests/test_alias_ingest.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ncfd.ingest.aliases import ingest_aliases_from_text, AliasInput

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, future=True)

def _mk_company(conn, cik, name, nn):
    return conn.execute(text("""
        INSERT INTO companies (cik, name, name_norm) VALUES (:c, :n, :nn)
        RETURNING company_id
    """), {"c": cik, "n": name, "nn": nn}).scalar_one()

def setup_function(_f):
    with engine.begin() as c:
        c.execute(text("DELETE FROM company_aliases"))
        c.execute(text("DELETE FROM securities WHERE ticker_norm IN ('ACME')"))
        c.execute(text("DELETE FROM companies WHERE cik IN (1234567890, 1234567891, 1234567892)"))

def test_fka_and_dba_high_precision():
    with engine.begin() as c:
        parent_id = _mk_company(c, 1234567890, "Acme Therapeutics, Inc.", "acme therapeutics")
    text_body = """
        On March 5, 2023, Acme Therapeutics, Inc. (formerly known as BetaBio, Inc.) changed its name.
        Acme Therapeutics, Inc. is doing business as Acme Bio in certain jurisdictions.
    """
    with Session(engine) as s, s.begin():
        stats = ingest_aliases_from_text(s, [
            AliasInput(company_id=parent_id, text=text_body, source="8-K", source_url="http://example.com/8k")
        ])
        assert stats["inserted"] == 2

    with engine.begin() as c:
        rows = c.execute(text("""
            SELECT alias, alias_type::text, alias_norm FROM company_aliases
            WHERE company_id=:cid ORDER BY alias_type, alias
        """), {"cid": parent_id}).all()
        assert ("Acme Bio", "dba", "acme") in rows  # 'Bio' drops via conservative suffix list
        assert ("BetaBio, Inc.", "former_name", "betabio") in rows

def test_subsidiary_link_if_known():
    with engine.begin() as c:
        parent_id = _mk_company(c, 1234567891, "ParentCo, Inc.", "parentco")
        sub_id = _mk_company(c,    1234567892, "Foobar Holdings, Inc.", "foobar")  # exists in DB

    text_body = "Foobar Holdings, Inc., a wholly-owned subsidiary of ParentCo, Inc., entered into an agreement..."
    with Session(engine) as s, s.begin():
        stats = ingest_aliases_from_text(s, [
            AliasInput(company_id=parent_id, text=text_body, source="8-K")
        ])
        assert stats["inserted"] == 1

    with engine.begin() as c:
        (alias, atype, nn, alias_company_id) = c.execute(text("""
            SELECT alias, alias_type::text, alias_norm, alias_company_id
            FROM company_aliases WHERE company_id=:cid
        """), {"cid": parent_id}).one()
        assert alias == "Foobar Holdings, Inc."
        assert atype == "subsidiary"
        assert nn == "foobar"
        assert alias_company_id == sub_id
