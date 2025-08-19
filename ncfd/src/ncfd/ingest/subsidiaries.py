# ncfd/src/ncfd/ingest/subsidiaries.py
from __future__ import annotations
from typing import List, Optional, Dict, Tuple
import re
from pathlib import Path
import subprocess
import shutil

import typer
from sqlalchemy import text
from sqlalchemy.orm import Session

from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name
from ncfd.ingest.deps import human_message

app = typer.Typer(add_completion=False)

try:
    from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore
except Exception:
    pdf_extract_text = None

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None

_SUB_HDR_RE = re.compile(r"subsidiar", re.IGNORECASE)
_CORP_RE = re.compile(
    r"\b("
    r"Inc|Incorporated|Corp|Corporation|Ltd|Limited|LLC|LLP|LP|PLC|"
    r"GmbH|S\.A\.|S\.p\.A\.|AG|BV|NV|SARL|S\.à r\.l\.|SAS|AB|Oy|A\/S|A\.S\.|"
    r"KK|Pte\. Ltd|Pty Ltd|Co\.,?\s*Ltd|Co\. Ltd"
    r")\b",
    re.I,
)


def _fallback_parse_naive(text: str) -> List[str]:
    names = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # strip bullets / numbering
        line = re.sub(r"^\s*(?:[-*•\u2022]|\(?\d+\)|\d+\.)\s*", "", line)
        # drop a trailing country in parentheses or after a comma
        line = re.sub(r"\s*(?:\(|,\s*)([A-Z]{2,3}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\)?\s*$", "", line)
        # squeeze spaces and trim punctuation
        line = re.sub(r"\s{2,}", " ", line).rstrip(" .,;")
        if not line:
            continue
        if _CORP_RE.search(line):
            names.append(line)
    # de-dupe preserving order
    seen = set()
    out: List[str] = []
    for n in names:
        if n.lower() not in seen:
            out.append(n)
            seen.add(n.lower())
    return out


def _looks_like_ex21(doc_type: str | None, descr: str | None) -> bool:
    dt = (doc_type or "").upper()
    ds = (descr or "")
    return dt.startswith("EX-21") or (_SUB_HDR_RE.search(ds) is not None)


def _parse_html(html: str) -> List[str]:
    if not BeautifulSoup:
        return []
    out: List[str] = []
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    for tbl in tables:
        header_txt = " ".join(th.get_text(" ", strip=True) for th in tbl.find_all("th")).lower()
        if not _SUB_HDR_RE.search(header_txt or ""):
            first_row = tbl.find("tr")
            if first_row:
                first_txt = " ".join(
                    td.get_text(" ", strip=True) for td in first_row.find_all(["td", "th"])
                ).lower()
                if not _SUB_HDR_RE.search(first_txt or ""):
                    continue
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            name = cells[0].get_text(" ", strip=True)
            if len(name) < 3 or _SUB_HDR_RE.search(name):
                continue
            out.append(name)
    if not out:
        texts = [t.get_text(" ", strip=True) for t in soup.find_all(["p", "div", "li"])]
        for line in texts:
            for piece in re.split(r"[;\n\r]+", line):
                piece = piece.strip()
                if 3 <= len(piece) <= 200 and not _SUB_HDR_RE.search(piece):
                    out.append(piece)
    uniq, seen = [], set()
    for s in out:
        s2 = re.sub(r"\s+", " ", s).strip(" -\u00b7")
        k = s2.lower()
        if len(s2) >= 3 and k not in seen:
            seen.add(k)
            uniq.append(s2)
    return uniq


def _parse_text(txt: str) -> List[str]:
    out: List[str] = []
    lines = [re.sub(r"\s+", " ", L).strip() for L in txt.splitlines()]
    buf: List[str] = []
    capture = False
    for L in lines:
        if _SUB_HDR_RE.search(L) or re.search(r"exhibit\s*21", L, re.IGNORECASE):
            capture = True
            continue
        if not capture:
            continue
        if not L:
            if buf:
                break
            continue
        buf.append(L)
    for L in buf:
        for piece in re.split(r"[\t;•·●]+", L):
            piece = piece.strip(" -\u00b7")
            if 3 <= len(piece) <= 200 and not _SUB_HDR_RE.search(piece):
                out.append(piece)
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
    suf = p.suffix.lower()
    # fast path for text/html-like files
    if suf in {".txt", ".htm", ".html"}:
        try:
            return p.read_text(errors="ignore")
        except UnicodeDecodeError:
            return p.read_bytes().decode("latin-1", errors="ignore")
    # handle PDF via pdfminer if available
    if suf == ".pdf":
        if not pdf_extract_text:
            return None  # dependency missing; skip
        try:
            return pdf_extract_text(str(p))
        except Exception:
            return None
    # fallback: try to read as text; if it blows up, skip
    try:
        return p.read_text(errors="ignore")
    except Exception:
        try:
            return p.read_bytes().decode("latin-1", errors="ignore")
        except Exception:
            return None

# ---------- schema autodetect ----------

_REQ_FILINGS_ANY = {
    "cik": {"cik"},
    "form": {"form", "form_type", "formname"},
    "date": {"filing_date", "filed_at", "filed", "report_date", "period"},
    "accession": {"accession_no", "accession_number", "accession", "accession_num"},
}
_REQ_DOCS_ANY = {
    "accession": {"accession_no", "accession_number", "accession", "accession_num"},
    "doc_type": {"doc_type", "type", "document_type"},
    "description": {"description", "doc_description", "document_description"},
    "path": {"local_path", "file_path", "filepath", "path", "localfile"},
}


def _columns_by_table(session: Session) -> Dict[str, set]:
    rows = session.execute(
        text(
            """
            SELECT lower(table_schema) AS sch, lower(table_name) AS tbl, lower(column_name) AS col
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog','information_schema')
        """
        )
    ).fetchall()
    out: Dict[str, set] = {}
    for sch, tbl, col in rows:
        key = f"{sch}.{tbl}"
        out.setdefault(key, set()).add(col)
    return out


def _best_table_and_cols(cols_by_tbl: Dict[str, set], req: Dict[str, set]) -> Optional[Tuple[str, Dict[str, str]]]:
    best: Optional[Tuple[str, Dict[str, str], int]] = None
    for full, cols in cols_by_tbl.items():
        chosen: Dict[str, str] = {}
        score = 0
        ok = True
        for fam, options in req.items():
            match = next((c for c in options if c in cols), None)
            if not match:
                ok = False
                break
            chosen[fam] = match
            score += 1
        if ok:
            bonus = 0
            if any(x in full for x in ("sec", "edgar", "filing", "document", "docs")):
                bonus += 1
            if best is None or (score + bonus) > best[2]:
                best = (full, chosen, score + bonus)
    if not best:
        return None
    return best[0], best[1]


def _validate_table_and_cols(session: Session, table: str, cols: List[str]) -> None:
    sch, tbl = (table.split(".", 1) + ["public"])[:2] if "." in table else ("public", table)
    session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE lower(table_schema) = lower(:sch)
              AND lower(table_name) = lower(:tbl)
              AND lower(column_name) = ANY(:cols)
        """
        ),
        {"sch": sch, "tbl": tbl, "cols": [c.lower() for c in cols]},
    ).fetchall()
    # We don't hard-fail here; any mismatch will surface when the main query runs.


def _detect_sec_sources(session: Session) -> Tuple[str, Dict[str, str], str, Dict[str, str]]:
    cols_by_tbl = _columns_by_table(session)
    filings = _best_table_and_cols(cols_by_tbl, _REQ_FILINGS_ANY)
    docs = _best_table_and_cols(cols_by_tbl, _REQ_DOCS_ANY)
    if not filings or not docs:
        raise RuntimeError("Could not auto-detect EDGAR tables.")
    filings_tbl, filings_cols = filings
    docs_tbl, docs_cols = docs
    return filings_tbl, filings_cols, docs_tbl, docs_cols


def _resolve_sources(
    session: Session,
    filings_table: Optional[str],
    filings_cols: Dict[str, Optional[str]],
    docs_table: Optional[str],
    docs_cols: Dict[str, Optional[str]],
) -> Tuple[str, Dict[str, str], str, Dict[str, str]]:
    if all(
        [filings_table, filings_cols.get("cik"), filings_cols.get("form"), filings_cols.get("date"), filings_cols.get("accession")]
    ) and all(
        [docs_table, docs_cols.get("accession"), docs_cols.get("doc_type"), docs_cols.get("description"), docs_cols.get("path")]
    ):
        fcols = {k: v for k, v in filings_cols.items() if v}
        dcols = {k: v for k, v in docs_cols.items() if v}
        _validate_table_and_cols(session, filings_table, list(fcols.values()))
        _validate_table_and_cols(session, docs_table, list(dcols.values()))
        return filings_table, fcols, docs_table, dcols
    # fallback to autodetect
    return _detect_sec_sources(session)


def _ex21_documents(
    session: Session,
    since: str,
    limit: int,
    filings_table: Optional[str] = None,
    filings_cols: Optional[Dict[str, Optional[str]]] = None,
    docs_table: Optional[str] = None,
    docs_cols: Optional[Dict[str, Optional[str]]] = None,
):
    filings_cols = filings_cols or {}
    docs_cols = docs_cols or {}
    filings_tbl, fcol, docs_tbl, dcol = _resolve_sources(
        session,
        filings_table,
        filings_cols,
        docs_table,
        docs_cols,
    )
    sql = f"""
        SELECT c.company_id,
               f.{fcol['cik']} AS cik,
               f.{fcol['form']} AS form,
               f.{fcol['date']} AS filing_date,
               f.{fcol['accession']} AS accession_no,
               COALESCE(d.{dcol['doc_type']}, '') AS doc_type,
               COALESCE(d.{dcol['description']}, '') AS doc_description,
               d.{dcol['path']} AS local_path
        FROM {filings_tbl} f
        JOIN companies c
          ON c.cik = CAST(f.{fcol['cik']} AS BIGINT)
        JOIN {docs_tbl} d
          ON d.{dcol['accession']} = f.{fcol['accession']}
        WHERE f.{fcol['form']} IN ('10-K','20-F')
          AND f.{fcol['date']} >= :since
          AND (
                UPPER(COALESCE(d.{dcol['doc_type']},'')) LIKE 'EX-21%%'
             OR d.{dcol['description']} ILIKE '%%subsidiar%%'
          )
        ORDER BY f.{fcol['date']} DESC
        LIMIT :lim
    """
    return session.execute(text(sql), {"since": since, "lim": limit}).fetchall()


def _insert_aliases(session: Session, parent_company_id: int, names: List[str]) -> int:
    inserted = 0
    for raw in names:
        alias_norm = norm_name(raw)
        if not alias_norm:
            continue
        session.execute(
            text(
                """
                INSERT INTO company_aliases (company_id, alias_type, alias, alias_norm, source)
                VALUES (:cid, 'subsidiary', :alias, :alias_norm, 'exhibit21')
                ON CONFLICT (company_id, alias_norm, alias_type) DO NOTHING
            """
            ),
            {"cid": parent_company_id, "alias": raw[:500], "alias_norm": alias_norm},
        )
        inserted += 1
    return inserted


def _common_cli_overrides():
    return {
        "filings_table": typer.Option(None, "--filings-table", help="schema.table for filings"),
        "filings_cik": typer.Option(None, "--filings-cik-col", help="filings column for CIK"),
        "filings_form": typer.Option(None, "--filings-form-col", help="filings column for form"),
        "filings_date": typer.Option(None, "--filings-date-col", help="filings column for filing date"),
        "filings_acc": typer.Option(None, "--filings-accession-col", help="filings column for accession"),
        "docs_table": typer.Option(None, "--docs-table", help="schema.table for documents"),
        "docs_acc": typer.Option(None, "--docs-accession-col", help="documents column for accession"),
        "docs_type": typer.Option(None, "--docs-type-col", help="documents column for doc type"),
        "docs_desc": typer.Option(None, "--docs-desc-col", help="documents column for description"),
        "docs_path": typer.Option(None, "--docs-path-col", help="documents column for local path"),
    }


@app.command("inspect")
def inspect(
    filings_table: Optional[str] = _common_cli_overrides()["filings_table"],
    filings_cik: Optional[str] = _common_cli_overrides()["filings_cik"],
    filings_form: Optional[str] = _common_cli_overrides()["filings_form"],
    filings_date: Optional[str] = _common_cli_overrides()["filings_date"],
    filings_acc: Optional[str] = _common_cli_overrides()["filings_acc"],
    docs_table: Optional[str] = _common_cli_overrides()["docs_table"],
    docs_acc: Optional[str] = _common_cli_overrides()["docs_acc"],
    docs_type: Optional[str] = _common_cli_overrides()["docs_type"],
    docs_desc: Optional[str] = _common_cli_overrides()["docs_desc"],
    docs_path: Optional[str] = _common_cli_overrides()["docs_path"],
):
    """Show which tables/columns will be used for filings & documents."""
    with get_session() as s:
        try:
            filings_tbl, fcol, docs_tbl, dcol = _resolve_sources(
                s,
                filings_table,
                {"cik": filings_cik, "form": filings_form, "date": filings_date, "accession": filings_acc},
                docs_table,
                {"accession": docs_acc, "doc_type": docs_type, "description": docs_desc, "path": docs_path},
            )
        except Exception as e:
            typer.echo(f"[detect error] {e}")
            raise typer.Exit(1)
        typer.echo("Using sources:")
        typer.echo(f"  filings  : {filings_tbl}  -> {fcol}")
        typer.echo(f"  documents: {docs_tbl}  -> {dcol}")


@app.command("build-subs")
def build_subs(
    since: str = typer.Option("2018-01-01", "--since", help="Only filings on/after this (YYYY-MM-DD)"),
    limit: int = typer.Option(2000, "--limit", help="Max exhibits to scan this run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Scan/parse but do not write aliases"),
    debug: bool = typer.Option(False, "--debug", help="Print per-exhibit parse counts"),
    filings_table: Optional[str] = _common_cli_overrides()["filings_table"],
    filings_cik: Optional[str] = _common_cli_overrides()["filings_cik"],
    filings_form: Optional[str] = _common_cli_overrides()["filings_form"],
    filings_date: Optional[str] = _common_cli_overrides()["filings_date"],
    filings_acc: Optional[str] = _common_cli_overrides()["filings_acc"],
    docs_table: Optional[str] = _common_cli_overrides()["docs_table"],
    docs_acc: Optional[str] = _common_cli_overrides()["docs_acc"],
    docs_type: Optional[str] = _common_cli_overrides()["docs_type"],
    docs_desc: Optional[str] = _common_cli_overrides()["docs_desc"],
    docs_path: Optional[str] = _common_cli_overrides()["docs_path"],
):
    """
    Scan SEC 10-K/20-F subsidiaries exhibits and insert aliases (alias_type='subsidiary').
    """
    found, wrote = 0, 0
    with get_session() as s:
        rows = _ex21_documents(
            s,
            since,
            limit,
            filings_table,
            {"cik": filings_cik, "form": filings_form, "date": filings_date, "accession": filings_acc},
            docs_table,
            {"accession": docs_acc, "doc_type": docs_type, "description": docs_desc, "path": docs_path},
        )
        for (parent_cid, _cik, _form, _fdate, _acc, doc_type, doc_descr, local_path) in rows:
            body = _load_doc_body(local_path)
            if not body:
                if debug:
                    typer.echo(f"[ex21] {local_path} -> 0 names (no body)")
                continue
            names = (
                _parse_html(body)
                if BeautifulSoup and ("<table" in body.lower() or "<html" in body.lower())
                else _parse_text(body)
            )
            # If no header-driven parse worked, try a forgiving line-by-line fallback
            if not names:
                names = _fallback_parse_naive(body)

            if debug:
                typer.echo(f"[ex21] {local_path} -> {len(names)} names")

            found += len(names)
            if not dry_run and names:
                wrote += _insert_aliases(s, parent_cid, names)
    typer.echo(
        f"Exhibits scanned={len(rows)}  names_found={found}  aliases_inserted={wrote}  dry_run={dry_run}"
    )


@app.command("dry")
def cli_dry(
    since: str = typer.Option("2018-01-01", "--since", help="Only filings on/after this date (YYYY-MM-DD)"),
    limit: int = typer.Option(200, "--limit", help="Max number of EX-21 docs to scan"),
):
    """Scan EX-21 documents and parse subsidiaries, but DO NOT write aliases."""
    from ncfd.ingest.subsidiaries import build_subs

    build_subs(
        dry_run=True,
        since=since,
        limit=limit,
        debug=True,
        # override Typer OptionInfo defaults with *actual* values
        filings_table="edgar.filings",
        filings_cik="cik",
        filings_form="form",
        filings_date="filed_at",
        filings_acc="accession_no",
        docs_table="edgar.documents",
        docs_acc="accession_no",
        docs_type="document_type",
        docs_desc="description",
        docs_path="local_path",
    )


@app.command("load")
def cli_load(
    since: str = typer.Option("2018-01-01", "--since", help="Only filings on/after this date (YYYY-MM-DD)"),
    limit: int = typer.Option(200, "--limit", help="Max number of EX-21 docs to load"),
):
    """Scan EX-21 documents and INSERT subsidiary aliases into company_aliases."""
    from ncfd.ingest.subsidiaries import build_subs

    build_subs(
        dry_run=False,
        since=since,
        limit=limit,
        debug=True,
        filings_table="edgar.filings",
        filings_cik="cik",
        filings_form="form",
        filings_date="filed_at",
        filings_acc="accession_no",
        docs_table="edgar.documents",
        docs_acc="accession_no",
        docs_type="document_type",
        docs_desc="description",
        docs_path="local_path",
    )

@app.command("check-deps")
def cli_check_deps():
    typer.echo(human_message())

if __name__ == "__main__":
    app()
