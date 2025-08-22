# ncfd/src/ncfd/ingest/subs_link.py
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from dataclasses import dataclass

import typer
from sqlalchemy import text
from sqlalchemy.orm import Session

from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name

app = typer.Typer(add_completion=False)


# ------------------------------- data helpers -------------------------------

@dataclass(frozen=True)
class SubsAlias:
    parent_id: int        # registrant / ultimate parent (dst of subsidiary_of)
    alias: str            # raw subsidiary name as found in EX-21
    alias_norm: str       # normalized name


def _fetch_subsidiary_aliases(session: Session) -> List[SubsAlias]:
    rows = session.execute(
        text("""
            SELECT ca.company_id    AS parent_id,
                   ca.alias         AS alias,
                   ca.alias_norm    AS alias_norm
            FROM company_aliases ca
            WHERE ca.alias_type = 'subsidiary'
        """)
    ).fetchall()
    out: List[SubsAlias] = []
    for parent_id, alias, alias_norm in rows:
        alias_norm = alias_norm or norm_name(alias) or ""
        if alias_norm:
            out.append(SubsAlias(int(parent_id), alias, alias_norm))
    return out


def _fetch_canonical_map(session: Session, name_types: Sequence[str]) -> Dict[str, List[int]]:
    """
    Map alias_norm -> [company_id] using canonical alias types (e.g. legal, aka).
    """
    if not name_types:
        name_types = ("legal", "aka")

    rows = session.execute(
        text("""
            SELECT alias_norm, company_id
            FROM company_aliases
            WHERE alias_type::text = ANY(:types)
              AND alias_norm IS NOT NULL
        """),
        {"types": list(name_types) or ["legal", "aka"]},
    ).fetchall()
    out: Dict[str, List[int]] = {}
    for alias_norm, cid in rows:
        if not alias_norm:
            continue
        out.setdefault(alias_norm, []).append(int(cid))
    return out


# ------------------------------- core linking -------------------------------

@dataclass
class Candidate:
    child_id: int
    parent_id: int
    source: str


def _make_candidates(
    subs: Iterable[SubsAlias],
    canon: Dict[str, List[int]],
    source: str,
) -> List[Candidate]:
    cands: List[Candidate] = []
    for sa in subs:
        for child in canon.get(sa.alias_norm, []):
            # Edge orientation: child --> parent  (edge_type='subsidiary_of')
            cands.append(Candidate(child_id=child, parent_id=sa.parent_id, source=source))
    return cands


def _insert_edges(session: Session, cands: Iterable[Candidate]) -> int:
    inserted = 0
    for c in cands:
        session.execute(
            text("""
                INSERT INTO company_edges (src_company_id, dst_company_id, edge_type, source)
                SELECT :child, :parent, 'subsidiary_of', :src
                WHERE NOT EXISTS (
                    SELECT 1 FROM company_edges e
                    WHERE e.src_company_id = :child
                      AND e.dst_company_id = :parent
                      AND e.edge_type = 'subsidiary_of'
                )
                ON CONFLICT DO NOTHING
            """),
            {"child": c.child_id, "parent": c.parent_id, "src": c.source},
        )
        inserted += 1
    return inserted


# ------------------------------- stub creation -------------------------------

@dataclass
class StubPlan:
    alias: str
    alias_norm: str
    parent_id: int


def _plan_stubs(subs: Iterable[SubsAlias], canon: Dict[str, List[int]]) -> List[StubPlan]:
    to_create: List[StubPlan] = []
    seen_norms: set[str] = set(canon.keys())
    for sa in subs:
        if sa.alias_norm not in seen_norms:
            to_create.append(StubPlan(alias=sa.alias, alias_norm=sa.alias_norm, parent_id=sa.parent_id))
    return to_create


def _create_stub_company(session: Session, alias: str) -> int:
    # companies.name_norm is NOT NULL → populate it
    nn = norm_name(alias) or alias.strip().lower()
    row = session.execute(
        text("""
            INSERT INTO companies (name, name_norm, cik)
            VALUES (:name, :name_norm, NULL)
            RETURNING company_id
        """),
        {"name": alias, "name_norm": nn},
    ).fetchone()
    return int(row[0])


def _ensure_legal_alias(session: Session, company_id: int, alias: str, alias_norm: str) -> None:
    session.execute(
        text("""
            INSERT INTO company_aliases (company_id, alias_type, alias, alias_norm, source)
            VALUES (:cid, 'legal', :alias, :alias_norm, 'exhibit21_stub')
            ON CONFLICT (company_id, alias_norm, alias_type) DO NOTHING
        """),
        {"cid": company_id, "alias": alias[:500], "alias_norm": alias_norm},
    )


def _create_stubs_and_edges(
    session: Session,
    stubs: Iterable[StubPlan],
    source: str,
) -> Tuple[int, int]:
    """
    Returns (companies_created, edges_inserted)
    For each planned stub:
      - create company
      - add legal alias
      - insert child->parent edge
    """
    new_companies, new_edges = 0, 0
    for sp in stubs:
        child_id = _create_stub_company(session, sp.alias)
        _ensure_legal_alias(session, child_id, sp.alias, sp.alias_norm)
        session.execute(
            text("""
                INSERT INTO company_edges (src_company_id, dst_company_id, edge_type, source)
                SELECT :child, :parent, 'subsidiary_of', :src
                WHERE NOT EXISTS (
                    SELECT 1 FROM company_edges e
                    WHERE e.src_company_id = :child
                      AND e.dst_company_id = :parent
                      AND e.edge_type = 'subsidiary_of'
                )
                ON CONFLICT DO NOTHING
            """),
            {"child": child_id, "parent": sp.parent_id, "src": source},
        )
        new_companies += 1
        new_edges += 1
    return new_companies, new_edges


# --------------------------------- CLI ---------------------------------

def _common_options():
    return {
        "name_type": typer.Option(
            None,
            "--name-type",
            help="Canonical alias types to match against (repeatable). Default: legal, aka",
        ),
        "limit": typer.Option(50, "--limit", help="Only show up to this many rows in dry runs"),
        "source": typer.Option("exhibit21", "--source", help="Source label recorded on company_edges"),
        "create_stubs": typer.Option(
            False,
            "--create-stubs",
            help="If a subsidiary name doesn't match an existing company, create a stub company + legal alias, then link it.",
        ),
    }


@app.command("dry")
def cli_dry(
    name_type: Optional[List[str]] = _common_options()["name_type"],
    limit: int = _common_options()["limit"],
    source: str = _common_options()["source"],
    create_stubs: bool = _common_options()["create_stubs"],
):
    """
    Preview subsidiary link candidates; optionally show how many stubs would be created.
    """
    with get_session() as s:
        subs = _fetch_subsidiary_aliases(s)
        canon = _fetch_canonical_map(s, name_type or ("legal", "aka"))
        cands = _make_candidates(subs, canon, source)
        stub_plans = _plan_stubs(subs, canon) if create_stubs else []

        typer.echo(f"candidates={len(cands)}  (showing up to {limit})")
        shown = 0
        for c in cands[:limit]:
            typer.echo(f"  child={c.child_id} -> parent={c.parent_id}  edge=subsidiary_of source={c.source}")
            shown += 1
        if create_stubs:
            typer.echo(f"stubs_needed={len(stub_plans)}  (no DB writes in dry mode)")
            for sp in stub_plans[: max(0, limit - shown)]:
                typer.echo(f"  [stub] '{sp.alias}' (norm='{sp.alias_norm}') -> parent={sp.parent_id}")


@app.command("load")
def cli_load(
    name_type: Optional[List[str]] = _common_options()["name_type"],
    source: str = _common_options()["source"],
    create_stubs: bool = _common_options()["create_stubs"],
):
    """
    Insert subsidiary_of edges; if --create-stubs is set, also create companies & legal aliases for unmatched names.
    """
    with get_session() as s:
        subs = _fetch_subsidiary_aliases(s)
        canon = _fetch_canonical_map(s, name_type or ("legal", "aka"))
        cands = _make_candidates(subs, canon, source)

        edges_from_matches = _insert_edges(s, cands)

        edges_from_stubs = 0
        stubs_created = 0
        if create_stubs:
            stub_plans = _plan_stubs(subs, canon)
            stubs_created, edges_from_stubs = _create_stubs_and_edges(s, stub_plans, source)

        typer.echo(
            f"edges_inserted={edges_from_matches + edges_from_stubs}  "
            f"(from_matches={edges_from_matches}, from_stubs={edges_from_stubs})  "
            f"stubs_created={stubs_created}  edge_type='subsidiary_of'  source='{source}'"
        )


if __name__ == "__main__":
    app()
