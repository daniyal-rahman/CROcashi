# ncfd/src/ncfd/ingest/subsidiaries.py
from __future__ import annotations
from typing import List, Tuple, Optional
import re
from pathlib import Path

import typer
from bs4 import BeautifulSoup  # add to pyproject if missing
from sqlalchemy import text
from sqlalchemy.orm import Session

from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name

app = typer.Typer(add_completion=False)

# --- heuristics ---------------------------------------------------------------
_SUB_HDR_RE = re.compile(r"subsidiar", re.IGNORECASE)

def _looks_like_ex21(doc_type: str | None, descr: str | None) -> bool:
    dt = (doc_type or "").upper()
    ds = (descr or "")
    return dt.startswith("EX-21") or (_SUB_HDR_RE.search(ds) is not None)

def _parse_html(html: str) -> List[str]:
    out: List[str] = []
    soup = BeautifulSoup(html, "lxml")
    # Prefer tables whose first row contains "subsidiar"
    tables = soup.find_all("table")
    for tbl in tables:
        header_txt = " ".join((th.get_text(" ", strip=True) for th in tbl.find_all("th")))[:512].lower()
        if not _SUB_HDR_RE.search(header_txt or ""):
            # Some exhibits use rows as headers (no <th>), fallback to first row cells
            first_row = tbl.find("tr")
            if first_row:
                first_txt = " ".join(td.get_text(" ", strip=True) for td in first_row.find_all(["td", "th"]))[:512].lower()
                if not _SUB_HDR_RE.search(first_txt or ""):
                    continue
        # Extract first column as subsidiary name
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            name = cells[0].get_text(" ", strip=True)
            # Skip header-like lines
            if len(name) < 3 or _SUB_HDR_RE.search(name):
                continue
            out.append(name)
    # If no tables yielded, fall back to paragraph/list scanning
    if not out:
        texts = [t.get_text(" ", strip=True) for t in soup.find_all(["p", "div", "li"])]
        for line in texts:
            # crude but useful: split on semicolons / line breaks substitutes
            for piece in re.split(r"[;\n\r]+", line):
                piece = piece.strip()
                if 3 <= len(piece) <= 200 and not _SUB_HDR_RE.search(piece):
                    out.append(piece)
    # De-dup & clean
    uniq = []
    seen = set()
    for s in out:
        s_clean = re.sub(r"\s+", " ", s).strip(" -\u00b7")
        if len(s_clean) < 3:
            continue
        if s_clean.lower() not in seen:
            uniq.append(s_clean)
            seen.add(s_clean.lower())
    return uniq

def _parse_text(txt: str) -> List[str]:
    out: List[str] = []
    # find section near "Exhibit 21" or "Subsidiaries of the registrant"
    # then collect subsequent lines that look like names until a blank chunk
    lines = [re.sub(r"\s+", " ", L).strip() for L in txt.splitlines()]
    buf: List[str] = []
    capture = False
    for L in lines:
        if _SUB_HDR_RE.search(L) or re.search(r"exhibit\s*21", L, re.IGNORECASE):
            capture = True
            continue
        if not capture:
            continue
        if not L or len(L) < 3:
            if buf:
                break
            continue
        # Heuristic: skip lines that are just jurisdictions or percent holdings
        if re.fullmatch(r"[A-Za-z ,.\-()/%]+", L):
            buf.append(L)
    # post-process buffer: split obvious lists
    for L in buf:
        for piece in re.split(r"[\t;•·•●]+", L):
            piece = piece.strip(" -\u00b7")
            if 3 <= len(piece) <= 200 and not _SUB_HDR_RE.search(piece):
                out.append(piece)
    # Dedup
    uniq, seen = [], set()
    for s in out:
        k = s.lower()
        if k not in seen:
            uniq.append(s)
            seen.add(k)
    return uniq

def _load_doc_body(local_path: Optional[str]) -> Optional[str]:
    if not local_path:
        return None
    p = Path(local_path)
    if not p.exists():
        return None
    try:
        raw = p.read_text(errors="ignore")
    except UnicodeDecodeError:
        raw = p.read_bytes().decode("latin-1", errors="ignore")
    return raw

# --- DB access (adapt column names if your SEC schema differs) ----------------
def _ex21_documents(session: Session, since: str, limit: int) -> List[tuple]:
    """
    Returns list of tuples:
      (parent_company_id, cik, form, filing_date, accession_no, doc_type, doc_description, local_path)
    """
    rows = session.execute(
        text("""
            SELECT c.company_id,
                   f.cik,
                   f.form,
                   f.filing_date,
                   d.accession_no,
                   COALESCE(d.doc_type,'') AS doc_type,
                   COALESCE(d.description,'') AS doc_description,
                   d.local_path
            FROM sec_filings f
            JOIN companies c ON c.cik = f.cik
            JOIN sec_documents d ON d.accession_no = f.accession_no
            WHERE f.form IN ('10-K','20-F')
              AND f.filing_date >= :since
              AND (
                    UPPER(COALESCE(d.doc_type,'')) LIKE 'EX-21%%'
                 OR d.description ILIKE '%%subsidiar%%'
              )
            ORDER BY f.filing_date DESC
            LIMIT :lim
        """),
        {"since": since, "lim": limit},
    ).fetchall()
    return rows

def _insert_aliases(session: Session, parent_company_id: int, names: List[str]) -> int:
    inserted = 0
    for raw in names:
        alias_norm = norm_name(raw)
        if not alias_norm:
            continue
        session.execute(
            text("""
                INSERT INTO company_aliases (company_id, alias_type, alias, alias_norm, source)
                VALUES (:cid, 'subsidiary', :alias, :alias_norm, 'exhibit21')
                ON CONFLICT (company_id, alias_norm, alias_type) DO NOTHING
            """),
            {"cid": parent_company_id, "alias": raw[:500], "alias_norm": alias_norm}
        )
        inserted += 1
    return inserted

# --- CLI ---------------------------------------------------------------------
@app.command("build-subs")
def build_subs(
    since: str = typer.Option("2018-01-01", help="Only filings on/after this date (YYYY-MM-DD)"),
    limit: int = typer.Option(2000, help="Max exhibits to scan this run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Scan/parse but do not write aliases"),
):
    """
    Scan SEC 10-K/20-F exhibits for subsidiaries (Exhibit 21) and insert
    deterministic aliases (alias_type='subsidiary') pointing to the parent company.
    """
    found, wrote = 0, 0
    with get_session() as s:
        rows = _ex21_documents(s, since, limit)
        for (parent_cid, cik, form, fdate, acc, doc_type, doc_descr, local_path) in rows:
            body = _load_doc_body(local_path)
            if not body:
                continue
            names = []
            # very naive HTML detection
            if "<html" in body.lower() or "<table" in body.lower():
                names = _parse_html(body)
            else:
                names = _parse_text(body)
            found += len(names)
            if not dry_run:
                wrote += _insert_aliases(s, parent_cid, names)
        typer.echo(f"Exhibits scanned={len(rows)}  names_found={found}  aliases_inserted={wrote}  dry_run={dry_run}")

if __name__ == "__main__":
    app()
