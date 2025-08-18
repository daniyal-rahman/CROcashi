# ncfd/src/ncfd/mapping/candidates.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

ALLOWED_EXCH = {"NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE ARCA", "OTCQX", "OTCQB"}

def _company_hits(session: Session, qnorm: str, limit: int) -> List[Tuple[int, float]]:
    sql = text("""
        SELECT company_id, similarity(name_norm, :q) AS sim
        FROM companies
        WHERE name_norm % :q
        ORDER BY sim DESC
        LIMIT :lim
    """)
    rows = session.execute(sql, {"q": qnorm, "lim": limit}).fetchall()
    return [(r[0], float(r[1])) for r in rows]

def _alias_hits(session: Session, qnorm: str, limit: int) -> List[Tuple[int, float]]:
    sql = text("""
        SELECT company_id, similarity(alias_norm, :q) AS sim
        FROM company_aliases
        WHERE alias_norm % :q
        ORDER BY sim DESC
        LIMIT :lim
    """)
    rows = session.execute(sql, {"q": qnorm, "lim": limit}).fetchall()
    return [(r[0], float(r[1])) for r in rows]

def _attach_company_meta(session: Session, company_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not company_ids:
        return {}
    sql = text("""
        SELECT company_id, name, COALESCE(website_domain,'') AS website_domain
        FROM companies
        WHERE company_id = ANY(:ids)
    """)
    rows = session.execute(sql, {"ids": company_ids}).fetchall()
    return {r[0]: {"company_id": r[0], "name": r[1], "website_domain": r[2]} for r in rows}

def _col_exists(session: Session, table: str, column: str) -> bool:
    sql = text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
        LIMIT 1
    """)
    return session.execute(sql, {"t": table, "c": column}).first() is not None

def _table_exists(session: Session, table: str) -> bool:
    sql = text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = :t
        LIMIT 1
    """)
    return session.execute(sql, {"t": table}).first() is not None

def _best_us_security(session: Session, company_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not company_ids:
        return {}

    use_direct_exchange = _col_exists(session, "securities", "exchange")
    use_fk_exchange = (not use_direct_exchange) and _col_exists(session, "securities", "exchange_id") and _table_exists(session, "exchanges")

    if use_direct_exchange:
        join_sql = ""
        exch_expr = "UPPER(COALESCE(s.exchange,''))"
    elif use_fk_exchange:
        label_col: Optional[str] = None
        for cand in ("code", "name", "mic"):
            if _col_exists(session, "exchanges", cand):
                label_col = cand
                break
        label_col = label_col or "name"
        join_sql = "LEFT JOIN exchanges e ON e.exchange_id = s.exchange_id"
        exch_expr = f"UPPER(COALESCE(e.{label_col},''))"
    else:
        join_sql = ""
        exch_expr = "''"

    sql = text(f"""
        WITH ranked AS (
          SELECT
            s.company_id,
            s.ticker,
            s.cik,
            {exch_expr} AS exchange,
            ROW_NUMBER() OVER (
              PARTITION BY s.company_id
              ORDER BY
                CASE
                  WHEN {exch_expr} IN ('NASDAQ','XNAS') THEN 1
                  WHEN {exch_expr} IN ('NYSE','XNYS') THEN 2
                  WHEN {exch_expr} IN ('NYSE AMERICAN','AMEX','XASE') THEN 3
                  WHEN {exch_expr} IN ('NYSE ARCA','ARCX') THEN 4
                  WHEN {exch_expr} = 'OTCQX' THEN 5
                  WHEN {exch_expr} = 'OTCQB' THEN 6
                  ELSE 99
                END,
                s.ticker
            ) AS rn
          FROM securities s
          {join_sql}
          WHERE s.company_id = ANY(:ids)
        )
        SELECT company_id, ticker, cik, exchange
        FROM ranked
        WHERE rn = 1
    """)
    rows = session.execute(sql, {"ids": company_ids}).fetchall()
    return {r[0]: {"ticker": r[1], "cik": r[2], "exchange": r[3]} for r in rows}

# ncfd/src/ncfd/mapping/candidates.py  (function only)
def _alias_domains_map(session: Session, company_ids: List[int]) -> Dict[int, List[str]]:
    if not company_ids:
        return {}
    sql = text("""
        SELECT company_id,
               lower(regexp_replace(alias, '^www\\.', '')) AS domain
        FROM company_aliases
        WHERE alias_type = 'domain'
          AND alias IS NOT NULL
          AND company_id = ANY(:ids)
    """)
    rows = session.execute(sql, {"ids": company_ids}).fetchall()
    out: Dict[int, List[str]] = {}
    for cid, dom in rows:
        if dom:
            out.setdefault(cid, [])
            if dom not in out[cid]:
                out[cid].append(dom)
    return out

def candidate_retrieval(session: Session, sponsor_text_norm: str, k: int = 50) -> List[Dict[str, Any]]:
    k_each = max(1, k // 2)
    c_hits = _company_hits(session, sponsor_text_norm, k_each)
    a_hits = _alias_hits(session, sponsor_text_norm, k_each)

    sim_by_company: Dict[int, float] = {}
    for cid, sim in c_hits + a_hits:
        sim_by_company[cid] = max(sim_by_company.get(cid, 0.0), sim)

    top = sorted(sim_by_company.items(), key=lambda x: x[1], reverse=True)[:k]
    company_ids = [cid for cid, _ in top]

    meta = _attach_company_meta(session, company_ids)
    sec = _best_us_security(session, company_ids)
    alias_domains = _alias_domains_map(session, company_ids)

    out: List[Dict[str, Any]] = []
    for cid, sim in top:
        m = meta.get(cid, {"company_id": cid, "name": None, "website_domain": ""})
        s = sec.get(cid, {"ticker": None, "cik": None, "exchange": None})
        out.append({
            "company_id": cid,
            "name": m["name"],
            "website_domain": m["website_domain"],
            "domains": alias_domains.get(cid, []),   # <— NEW
            "ticker": s["ticker"],
            "cik": s["cik"],
            "exchange": s["exchange"],
            "sim": sim,
        })
    return out
