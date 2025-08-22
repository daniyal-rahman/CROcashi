from sqlalchemy import text
from ncfd.mapping.candidates import candidate_retrieval
from ncfd.mapping.normalize import norm_name

def seed_for_candidates(session):
    session.execute(text("DELETE FROM securities"))
    session.execute(text("DELETE FROM company_aliases"))
    session.execute(text("DELETE FROM companies"))

    # Companies (with name_norm assumed to exist in your schema)
    session.execute(text("""
        INSERT INTO companies (company_id, name, name_norm, website_domain) VALUES
          (2001, 'Regeneron Pharmaceuticals, Inc.', 'regeneron pharmaceuticals inc', 'regeneron.com'),
          (2002, 'Regenxbio Inc', 'regenxbio inc', 'regenxbio.com'),
          (2003, 'AlphaBio Therapeutics', 'alphabio therapeutics', 'alphabio.com')
    """))

    # Aliases (alias_norm assumed to exist)
    session.execute(text("""
        INSERT INTO company_aliases (company_id, alias_type, name, alias_norm) VALUES
          (2002, 'aka', 'Regenx Bio', 'regenx bio'),
          (2003, 'aka', 'Alpha Bio',  'alpha bio')
    """))

    # Securities
    session.execute(text("""
        INSERT INTO securities (company_id, exchange, ticker, cik) VALUES
          (2001, 'NASDAQ', 'REGN', '0000872589'),
          (2002, 'NASDAQ', 'RGNX', '0001501756'),
          (2003, 'OTCQX',  'ABTX', '0001234567')
    """))
    session.commit()

def test_candidate_retrieval_topk(session):
    seed_for_candidates(session)
    q = norm_name("Regenx Bio")
    out = candidate_retrieval(session, q, k=5)
    ids = [x["company_id"] for x in out]
    # Both Regeneron and Regenxbio should appear, Regenxbio should rank higher
    assert 2002 in ids
    assert 2001 in ids
    # top-one is likely 2002 (alias direct hit). We don't assert exact order to keep it robust.

def test_candidate_fields_present(session):
    seed_for_candidates(session)
    out = candidate_retrieval(session, norm_name("Alpha Bio"), k=3)
    item = next(x for x in out if x["company_id"] == 2003)
    assert item["ticker"] == "ABTX"
    assert item["exchange"] in {"OTCQX", "NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE ARCA"}
    assert isinstance(item["sim"], float)
