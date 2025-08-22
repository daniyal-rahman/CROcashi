# ncfd/mapping/cli_orgs.py
import json
import typer
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from ncfd.db import get_session

app = typer.Typer(help="Org graph tools: companies, aliases, subsidiaries")

def _upsert_company(s, name: str, website_domain: Optional[str]) -> int:
    row = s.execute(
        text("SELECT company_id FROM companies WHERE name = :n"),
        {"n": name}
    ).fetchone()
    if row:
        cid = row[0]
    else:
        cid = s.execute(
            text("INSERT INTO companies (name, website_domain) VALUES (:n, :d) RETURNING company_id"),
            {"n": name, "d": website_domain or None}
        ).scalar()
    return int(cid)

def _add_aliases(s, company_id: int, aliases: List[str]):
    if not aliases: return
    s.execute(
        text("""
        INSERT INTO company_aliases (company_id, alias)
        SELECT :cid, x.alias FROM jsonb_to_recordset(:aliases::jsonb) AS x(alias text)
        ON CONFLICT DO NOTHING
        """),
        {"cid": company_id, "aliases": json.dumps([{"alias": a} for a in aliases])}
    )

def _link_sub(s, parent_id: int, child_id: int, rel_type: str = "subsidiary", start_date: Optional[str] = None):
    s.execute(
        text("""
        INSERT INTO company_relationships (parent_company_id, child_company_id, rel_type, start_date)
        VALUES (:p, :c, :t, :sd)
        ON CONFLICT DO NOTHING
        """),
        {"p": parent_id, "c": child_id, "t": rel_type, "sd": start_date}
    )

@app.command("seed-one")
def seed_one(
    name: str,
    website: Optional[str] = typer.Option(None, "--website"),
    aliases: List[str] = typer.Option([], "--alias")
):
    "Insert or update a single company with optional aliases"
    with get_session() as s:
        cid = _upsert_company(s, name, website)
        _add_aliases(s, cid, aliases)
        typer.echo(f"company_id={cid} name={name}")

@app.command("add-subsidiary")
def add_subsidiary(
    parent: str = typer.Argument(..., help="Parent company name"),
    child: str = typer.Argument(..., help="Child company name"),
    parent_website: Optional[str] = typer.Option(None, "--parent-website"),
    child_website: Optional[str] = typer.Option(None, "--child-website"),
    child_alias: List[str] = typer.Option([], "--child-alias"),
    start_date: Optional[str] = typer.Option(None, "--start-date")
):
    "Create/ensure parent+child companies, alias child, link as subsidiary"
    with get_session() as s:
        pid = _upsert_company(s, parent, parent_website)
        cid = _upsert_company(s, child, child_website)
        _add_aliases(s, cid, child_alias)
        _link_sub(s, pid, cid, "subsidiary", start_date)
        typer.echo(f"linked {cid} -> {pid}")

@app.command("import-yaml")
def import_yaml(path: Path):
    """
    YAML format:
    groups:
      - parent:
          name: "F. Hoffmann-La Roche Ltd"
          website: "roche.com"
          aliases: ["Roche", "Hoffmann-La Roche", "F. Hoffmann-La Roche"]
        subsidiaries:
          - name: "Genentech, Inc."
            website: "gene.com"
            aliases: ["Genentech", "Genentech, Inc."]
            start_date: "2009-03-26"
    """
    import yaml
    data = yaml.safe_load(path.read_text())
    with get_session() as s:
        for g in data.get("groups", []):
            p = g["parent"]
            pid = _upsert_company(s, p["name"], p.get("website"))
            _add_aliases(s, pid, p.get("aliases", []))
            for sub in g.get("subsidiaries", []):
                cid = _upsert_company(s, sub["name"], sub.get("website"))
                _add_aliases(s, cid, sub.get("aliases", []))
                _link_sub(s, pid, cid, "subsidiary", sub.get("start_date"))
    typer.echo("import complete")
