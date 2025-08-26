# src/ncfd/mapping/cli.py
from __future__ import annotations

import json
import re
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import ProgrammingError, DBAPIError
from sqlalchemy.orm import Session

from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name
from ncfd.mapping.candidates import candidate_retrieval
from ncfd.mapping.probabilistic import (
    score_candidates,
    decide_probabilistic,
    extract_domains,
)
from ncfd.mapping.blocks import load_trial_party, derive_context
from ncfd.mapping.persist import (
    persist_decision,
    persist_candidate_features,
    create_resolver_run,
    create_resolver_input,
)
from ncfd.mapping.deterministic import resolve_company as det_resolve, Resolution
from ncfd.mapping.alias_promotion import upsert_alias_from_sponsor
from ncfd.mapping.llm_decider import decide_with_llm_research

app = typer.Typer(add_completion=False)
console = Console()

# --------------------------------------------------------------------------- #
# Helpers (config, printing, enrichment)
# --------------------------------------------------------------------------- #

def _llm_enabled(decider: str) -> bool:
    if decider.lower() == "llm":
        return True
    # Feature flag: if probabilistic path is disabled, fall back to LLM
    if os.getenv("RESOLVER_DISABLE_PROB", "0").lower() in ("1", "true", "yes"):
        return True
    # For "auto" mode, enable LLM as a fallback for low-confidence cases
    if decider.lower() == "auto":
        return True
    return False


def _load_yaml(path: str | Path) -> Dict[str, Any]:
    import yaml
    p = Path(path)
    candidates = [p, Path("config/resolver.yaml"), Path("ncfd/config/resolver.yaml")]
    for cand in candidates:
        if cand.exists():
            return yaml.safe_load(cand.read_text())
    raise FileNotFoundError(
        f"resolver config not found; tried: {', '.join(str(c) for c in candidates)}"
    )


def _ignored_sponsor(session: Session, sponsor_text: str) -> bool:
    # Centralized to avoid repetition and drift
    return bool(
        session.execute(
            text("SELECT EXISTS (SELECT 1 FROM resolver_ignore_sponsor WHERE :s ~* pattern)"),
            {"s": sponsor_text},
        ).scalar()
    )


def _print_deterministic(det: Resolution):
    table = Table(title="Deterministic Resolution")
    table.add_column("Method")
    table.add_column("Company ID", justify="right")
    table.add_column("Evidence")
    ev = ", ".join(f"{k}={v}" for k, v in (det.evidence or {}).items())
    table.add_row(det.method, str(det.company_id), ev)
    console.print(table)
    console.rule("Decision")
    console.print(
        "mode: [bold]deterministic:accept[/bold] | "
        f"leader company_id: [bold]{det.company_id}[/bold] | p: 1.0000 | margin: 1.0000"
    )


def _print_candidates(cands: List[Dict[str, Any]], title: str = "Candidates"):
    table = Table(title=title)
    table.add_column("Rank", justify="right")
    table.add_column("Company ID", justify="right")
    table.add_column("sim", justify="right")
    table.add_column("Name")
    table.add_column("Ticker")
    table.add_column("Exchange")
    table.add_column("Domain")
    for i, c in enumerate(cands, 1):
        dom = c.get("website_domain") or (c.get("domains")[0] if c.get("domains") else "")
        table.add_row(
            str(i),
            str(c["company_id"]),
            f"{c.get('sim', 0):.3f}",
            c.get("name") or "",
            c.get("ticker") or "",
            c.get("exchange") or "",
            dom or "",
        )
    console.print(table)


def _print_top_features(scored, topn: int = 10):
    # Fixed margin off-by-one: compute next_p safely using index-0 enumeration
    topn = min(topn, len(scored))
    table = Table(title=f"Top {topn} by p (probabilistic)")
    table.add_column("Rank", justify="right")
    table.add_column("Company ID", justify="right")
    table.add_column("p", justify="right")
    table.add_column("Δ (margin)", justify="right")
    table.add_column("jw")
    table.add_column("tsr")
    table.add_column("acro")
    table.add_column("domain")
    table.add_column("ticker")
    table.add_column("acad_pen")
    table.add_column("strong_tok")

    for idx in range(topn):
        s = scored[idx]
        f = s.features
        next_p = scored[idx + 1].p if idx + 1 < len(scored) else 0.0
        margin = s.p - next_p
        table.add_row(
            str(idx + 1),
            str(s.company_id),
            f"{s.p:.3f}",
            f"{margin:.3f}",
            f"{f.get('jw_primary', 0):.3f}",
            f"{f.get('token_set_ratio', 0):.3f}",
            f"{f.get('acronym_exact', 0):.0f}",
            f"{f.get('domain_root_match', 0):.0f}",
            f"{f.get('ticker_string_hit', 0):.0f}",
            f"{f.get('academic_keyword_penalty', 0):.0f}",
            f"{f.get('strong_token_overlap', 0):.3f}",
        )
    console.print(table)


def _print_trial_header(nct_id: Optional[str], sponsor_text: str):
    """Print a clear trial separator with basic trial information."""
    # Create a visual separator
    console.rule(f"[bold blue]TRIAL: {nct_id or 'NO_NCT_ID'}[/bold blue]")
    
    # Print trial info in a compact format
    if nct_id:
        console.print(f"[cyan]NCT ID:[/cyan] {nct_id}")
    console.print(f"[cyan]Sponsor Text:[/cyan] {sponsor_text or '(empty)'}")
    
    # Add a small separator line
    console.print("")


def _print_trial_footer():
    """Print a clear trial separator at the end of each trial."""
    # Add a visual separator line
    console.rule("[dim]END OF TRIAL[/dim]")
    # Add extra spacing for better readability
    console.print("")
    console.print("")


def _print_trial_overview(console, nct_id: str, sponsor_text: str, ctx: dict):
    table = Table(title=f"Trial Overview — {nct_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Lead sponsor (raw)", sponsor_text or "")
    ds = ", ".join(ctx.get("domains") or []) or "—"
    dc = ", ".join(ctx.get("drug_codes") or []) or "no"
    table.add_row("Domain hints", ds)
    table.add_row("Drug codes", dc)
    table.add_row("NIH/NCI hint", "yes" if ctx.get("nih_or_nci_hint") else "no")
    console.print(table)


def _hydrate_company_facts(session, company_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Stable superset select with COALESCE to avoid trial-and-error probing.
    """
    if not company_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT
              company_id,
              COALESCE(name, '') AS name,
              COALESCE(website_domain, '') AS website_domain,
              COALESCE(ticker, '') AS ticker,
              COALESCE(exchange, '') AS exchange,
              COALESCE(cik, 0) AS cik
            FROM companies
            WHERE company_id = ANY(:ids)
            """
        ),
        {"ids": company_ids},
    ).mappings().all()

    facts: Dict[int, Dict[str, Any]] = {int(r["company_id"]): dict(r) for r in rows}

    # aliases: top few
    alias_rows = session.execute(
        text(
            """
            SELECT company_id, alias, alias_type
            FROM company_aliases
            WHERE company_id = ANY(:ids)
            ORDER BY CASE alias_type
                       WHEN 'legal' THEN 0
                       WHEN 'aka' THEN 1
                       WHEN 'former_name' THEN 2
                       ELSE 3
                     END, created_at DESC
            """
        ),
        {"ids": company_ids},
    ).mappings().all()
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in alias_rows:
        cid = int(r["company_id"])
        if len(grouped[cid]) < 5:
            grouped[cid].append(f"{r['alias']} ({r['alias_type']})")
    for cid, arr in grouped.items():
        facts.setdefault(cid, {})["aliases"] = arr

    # active tickers
    tick_rows = session.execute(
        text(
            """
            SELECT s.company_id, s.ticker, e.code AS exch
            FROM securities s
            JOIN exchanges e ON e.exchange_id = s.exchange_id
            WHERE s.company_id = ANY(:ids) AND s.status = 'active'
            ORDER BY lower(s.effective_range) DESC
            """
        ),
        {"ids": company_ids},
    ).mappings().all()
    tmap: Dict[int, list] = {}
    for r in tick_rows:
        cid = int(r["company_id"])
        tmap.setdefault(cid, []).append(f"{r['ticker']}:{r['exch']}")
    for cid, arr in tmap.items():
        facts.setdefault(cid, {})["tickers"] = arr

    return facts


def _enrich_candidates_human(session, cands: list[dict], sponsor_norm: str):
    if not cands:
        return []

    c_sorted = sorted(cands, key=lambda x: x.get("p", 0.0), reverse=True)
    ids = [int(c["company_id"]) for c in c_sorted if c.get("company_id")]

    comp = _hydrate_company_facts(session, ids)

    # prior linked trials
    link_rows = session.execute(
        text(
            """
            SELECT sponsor_company_id AS company_id, COUNT(*) AS n
            FROM trials
            WHERE sponsor_company_id = ANY(:ids)
            GROUP BY sponsor_company_id
            """
        ),
        {"ids": ids},
    ).fetchall()
    linked = {int(r.company_id): int(r.n) for r in link_rows}

    # prior accepts for this sponsor text
    acc_rows = session.execute(
        text(
            """
            SELECT company_id, COUNT(*) AS n
            FROM resolver_decisions
            WHERE sponsor_text_norm = :s_norm
              AND (match_type = 'probabilistic:accept' OR match_type LIKE 'deterministic:%')
              AND company_id = ANY(:ids)
            GROUP BY company_id
            """
        ),
        {"s_norm": sponsor_norm, "ids": ids},
    ).fetchall()
    prior_accepts_for_text = {int(r.company_id): int(r.n) for r in acc_rows}

    enriched = []
    for c in c_sorted:
        cid = int(c.get("company_id") or 0)
        f_info = comp.get(cid, {})
        meta = (c.get("meta") or {}) or {}
        name = f_info.get("name") or meta.get("name") or ""
        domain = (f_info.get("website_domain") or meta.get("website_domain") or
                  (",".join(meta.get("domains", [])) if meta.get("domains") else ""))
        ticker = f_info.get("ticker") or meta.get("ticker") or ""
        exchange = f_info.get("exchange") or meta.get("exchange") or ""
        cik = f_info.get("cik") or meta.get("cik") or ""
        aliases = ", ".join(f_info.get("aliases", [])[:3]) if f_info.get("aliases") else ""
        tick_s = f"{ticker}:{exchange}" if ticker and exchange else ticker

        enriched.append({
            "company_id": cid,
            "p": float(c.get("p", 0.0)),
            "jw": float((c.get("features") or {}).get("jw_primary", 0.0)),
            "tsr": float((c.get("features") or {}).get("token_set_ratio", 0.0)),
            "name": name,
            "aliases": aliases,
            "ticker": tick_s,
            "cik": cik,
            "domain": domain,
            "linked_trials": linked.get(cid, 0),
            "prior_accepts_for_text": prior_accepts_for_text.get(cid, 0),
        })
    return enriched


def _print_candidates_human(console, rows: list[dict]):
    table = Table(title="Candidates (human-readable)")
    table.add_column("Rank", justify="right")
    table.add_column("p", justify="right")
    table.add_column("Company")
    table.add_column("Aliases (few)")
    table.add_column("Tickers")
    table.add_column("CIK", justify="right")
    table.add_column("Domain(s)")
    table.add_column("Linked trials", justify="right")
    table.add_column("Prior accepts (this text)", justify="right")
    table.add_column("jw", justify="right")
    table.add_column("tsr", justify="right")

    for i, r in enumerate(rows, 1):
        table.add_row(
            str(i),
            f"{r['p']:.3f}",
            f"{r['name']}  (cid={r['company_id']})",
            r["aliases"] or "",
            r["ticker"] or "",
            str(r["cik"] or ""),
            r["domain"] or "",
            str(r["linked_trials"]),
            str(r["prior_accepts_for_text"]),
            f"{r['jw']:.3f}",
            f"{r['tsr']:.3f}",
        )
    console.print(table)


def _print_candidates_simple(console, cands: List[Dict[str, Any]]):
    """Fallback simple table for review-show when enrichment fails."""
    table = Table(title="Candidates (simple)")
    table.add_column("Rank", justify="right")
    table.add_column("Company ID", justify="right")
    table.add_column("p", justify="right")
    table.add_column("jw")
    table.add_column("tsr")
    table.add_column("Ticker")
    table.add_column("Domain")
    for i, c in enumerate(sorted(cands, key=lambda x: x.get("p", 0.0), reverse=True), 1):
        f = c.get("features", {}) or {}
        meta = c.get("meta", {}) or {}
        dom = ""
        if isinstance(meta.get("domains"), (list, tuple)) and meta["domains"]:
            dom = ", ".join(meta["domains"][:3])
        elif meta.get("website_domain"):
            dom = meta["website_domain"]
        table.add_row(
            str(i),
            str(c.get("company_id") or ""),
            f"{c.get('p', 0.0):.3f}",
            f"{f.get('jw_primary', 0.0):.3f}",
            f"{f.get('token_set_ratio', 0.0):.3f}",
            meta.get("ticker") or "",
            dom or "",
        )
    console.print(table)


_DRUG_CODE_RE = re.compile(r"\b[A-Z]{1,5}-\d{2,5}[A-Z]?\b")

def _make_context_for_prob(session, nct: Optional[str], sponsor_text: str) -> Dict[str, Any]:
    """
    Prefer full context (domains, drug-code hits) when we know nct_id.
    Fallback to a light context extracted from sponsor text only.
    """
    if nct:
        row = session.execute(text("SELECT trial_id FROM trials WHERE nct_id = :nct"), {"nct": nct}).first()
        if row:
            tp = load_trial_party(session, int(row[0]), nct, sponsor_text or "")
            ctx = derive_context(tp)
            return {"domains": ctx.domains, "drug_code_hit": bool(ctx.drug_codes)}
    doms = extract_domains(sponsor_text or "")
    code_hit = bool(_DRUG_CODE_RE.search((sponsor_text or "").upper()))
    return {"domains": doms, "drug_code_hit": code_hit}


def _serialize_scored(scored, topn: int = 10) -> List[Dict[str, Any]]:
    """Convert Scored dataclasses to plain dicts for JSONB persistence (top-N only)."""
    out: List[Dict[str, Any]] = []
    for s in scored[:topn]:
        out.append(
            {
                "company_id": s.company_id,
                "p": float(s.p),
                "features": {k: float(v) for k, v in s.features.items()},
                "meta": s.meta,
            }
        )
    return out


def _enqueue_review(session, *, run_id: str, nct_id: str, sponsor_text: str, candidates: List[Dict[str, Any]], reason: str):
    """Stable queue writer: insert into review_queue (JSONB-bound)."""
    # Normalize sponsor text
    s_norm = " ".join(sponsor_text.split()).lower() if sponsor_text else ""
    
    stmt = (
        text(
            """
            INSERT INTO review_queue (run_id, nct_id, sponsor_text, sponsor_text_norm, candidates, reason, status, decided_by)
            VALUES (:run_id, :nct_id, :sponsor_text, :s_norm, :candidates, :reason, 'pending', 'auto')
            """
        )
        .bindparams(bindparam("candidates", type_=JSONB))
    )
    session.execute(
        stmt,
        {
            "run_id": run_id,
            "nct_id": nct_id,
            "sponsor_text": sponsor_text,
            "s_norm": s_norm,
            "candidates": candidates,
            "reason": reason,
        },
    )

# --------------------------------------------------------------------------- #
# Unified resolution core
# --------------------------------------------------------------------------- #

@dataclass
class FlowOptions:
    cfg: Dict[str, Any]
    run_id: str
    persist: bool
    decider: str
    apply_trial: bool
    skip_det: bool
    k: int
    json_out: bool


def run_resolution(
    session: Session,
    *,
    sponsor_text: str,
    nct_id: Optional[str],
    options: FlowOptions,
    ctx_override: Optional[Dict[str, Any]] = None,
) -> None:
    """
    The single source of truth for:
    det → candidate retrieval → scoring → probabilistic decision → (optional LLM)
    Includes printing, persistence, applying trials, enqueueing review, and JSON output.
    """
    cfg = options.cfg
    run_id = options.run_id
    decider = options.decider
    persist = options.persist
    apply_trial = options.apply_trial
    skip_det = options.skip_det
    k = options.k
    json_out = options.json_out

    # (0) Print trial header with separation and basic info
    _print_trial_header(nct_id, sponsor_text)

    # (1) Deterministic
    det: Optional[Resolution] = None
    if not skip_det and sponsor_text:
        det = det_resolve(session, sponsor_text)

    if det:
        _print_deterministic(det)
        # Deterministic persistence
        if persist:
            if nct_id:
                if nct_id and _ignored_sponsor(session, sponsor_text):
                    console.print(f"[dim]SKIP ignored sponsor[/dim] {nct_id} :: {sponsor_text!r}")
                else:
                    persist_decision(
                        session,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        decision=det,
                        leader_features={},
                        leader_meta={},
                        decided_by=decider,
                        notes_md=None,
                    )
                    if apply_trial:
                        session.execute(
                            text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                            {"cid": det.company_id, "nct": nct_id},
                        )
                    try:
                        if upsert_alias_from_sponsor(session, det.company_id, sponsor_text):
                            console.print(f"[dim][alias] + {nct_id} → company {det.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct_id} → company {det.company_id}: {e}[/dim]")
            else:
                console.print("[yellow]--persist requested but --nct missing; skipping DB write.[/yellow]")

        if json_out:
            blob = {
                "mode": f"deterministic:{det.method}",
                "company_id": det.company_id,
                "p": 1.0,
                "top2_margin": 1.0,
                "leader_features": {},
                "leader_meta": {},
                "evidence": det.evidence,
                "run_id": run_id,
                "nct_id": nct_id,
            }
            console.print_json(json.dumps(blob, ensure_ascii=False))
        return

    # (2) Probabilistic
    if os.getenv("RESOLVER_DISABLE_PROB", "0").lower() in ("1", "true", "yes"):
        console.rule("[yellow]Probabilistic (logistic) path disabled[/yellow]")

    qnorm = norm_name(sponsor_text or "")
    cands = candidate_retrieval(session, qnorm, k=k)
    if not cands:
        console.print("[yellow]No candidates found.[/yellow]")
        if persist and nct_id and options.decider != "llm" and _llm_enabled(decider):
            # Allow LLM to take a shot even if no cands
            pass
        else:
            raise typer.Exit(1)

    if cands:
        _print_candidates(cands, title="Candidate Retrieval")

    weights = cfg.get("model", {}).get("weights", {})
    intercept = cfg.get("model", {}).get("intercept", 0.0)
    ctx = ctx_override or _make_context_for_prob(session, nct_id, sponsor_text)
    scored = score_candidates(cands or [], sponsor_text, weights, intercept, context=ctx)
    if scored:
        _print_top_features(scored, topn=min(10, len(scored)))

    # (3) Probabilistic decision
    th = cfg["thresholds"]
    prob_dec = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

    if prob_dec.mode == "accept":
        console.rule("Decision (Probabilistic)")
        console.print(
            f"mode: [bold]{prob_dec.mode}[/bold] | leader company_id: [bold]{prob_dec.company_id}[/bold] "
            f"| p: {prob_dec.p:.4f} | margin: {prob_dec.top2_margin:.4f}"
        )
        if persist:
            if nct_id:
                if _ignored_sponsor(session, sponsor_text):
                    console.print(f"[dim]SKIP ignored sponsor[/dim] {nct_id} :: {sponsor_text!r}")
                else:
                    persist_candidate_features(
                        session,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        scored_candidates=_serialize_scored(scored, topn=25),
                    )
                    persist_decision(
                        session,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        decision=prob_dec,
                        leader_features=prob_dec.features,
                        leader_meta=prob_dec.leader_meta,
                        decided_by=decider,
                        notes_md=None,
                    )
                    if apply_trial:
                        session.execute(
                            text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                            {"cid": prob_dec.company_id, "nct": nct_id},
                        )
                    try:
                        if upsert_alias_from_sponsor(session, prob_dec.company_id, sponsor_text):
                            console.print(f"[dim][alias] + {nct_id} → company {prob_dec.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct_id} → company {prob_dec.company_id}: {e}[/dim]")
            else:
                console.print("[yellow]--persist requested but --nct missing; skipping DB write.[/yellow]")

        if json_out:
            blob = {
                "mode": prob_dec.mode,
                "company_id": prob_dec.company_id,
                "p": prob_dec.p,
                "top2_margin": prob_dec.top2_margin,
                "leader_features": prob_dec.features,
                "leader_meta": prob_dec.leader_meta,
                "run_id": run_id,
                "nct_id": nct_id,
            }
            console.print_json(json.dumps(blob, ensure_ascii=False))
        return

    # (4) Non-accept path: maybe LLM, else review/reject handling
    use_llm = _llm_enabled(decider)

    # Always show probabilistic decision first
    console.rule("Decision (Probabilistic)")
    console.print(
        f"mode: [bold]{prob_dec.mode}[/bold] | leader company_id: [bold]{prob_dec.company_id}[/bold] "
        f"| p: {prob_dec.p:.4f} | margin: {prob_dec.top2_margin:.4f}"
    )
    
    # Persist probabilistic features and decisions
    if persist and nct_id:
        if prob_dec.mode == "review":
            _enqueue_review(
                session,
                run_id=run_id,
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                candidates=_serialize_scored(scored, topn=25),
                reason="prob_review",
            )
            console.print(f"[yellow]Enqueued review[/yellow] run_id={run_id} nct={nct_id}")
        else:
            console.print("[blue]Reject: not persisted.[/blue]")
    elif persist and not nct_id:
        console.print("[yellow]--persist requested but --nct missing; skipping DB write.[/yellow]")

    # Handle JSON output for probabilistic decision
    if json_out:
        blob = {
            "mode": prob_dec.mode,
            "company_id": prob_dec.company_id,
            "p": prob_dec.p,
            "top2_margin": prob_dec.top2_margin,
            "leader_features": prob_dec.features,
            "leader_meta": prob_dec.leader_meta,
            "run_id": run_id,
            "nct_id": nct_id,
        }
        console.print_json(json.dumps(blob, ensure_ascii=False))
    
    # If LLM is not enabled, stop here
    if not use_llm:
        return

    # (5) LLM research path
    console.print("[dim]Probabilistic didn't accept, trying LLM Research...[/dim]")
    llm_dec, raw = decide_with_llm_research(
        run_id=run_id,
        nct_id=nct_id or "<none>",
        session=session,
        context=ctx,
    )
    console.rule("LLM Decision")
    console.print(
        f"mode: [bold]{llm_dec.mode}[/bold] "
        f"| company_id: [bold]{llm_dec.company_id}[/bold] "
        f"| conf: {llm_dec.confidence:.2f}"
    )
    if llm_dec.rationale:
        console.print(f"[dim]{llm_dec.rationale}[/dim]")

    if persist:
        if nct_id:
            # Always persist features for training
            persist_candidate_features(
                session,
                run_id=run_id,
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                scored_candidates=_serialize_scored(scored, topn=25),
            )

            if llm_dec.mode == "accept" and llm_dec.company_id:
                decision = {
                    "mode": "accept",
                    "company_id": llm_dec.company_id,
                    "p": 1.0,
                    "top2_margin": 1.0,
                    "features": {},
                    "leader_meta": {"source": "llm", "confidence": llm_dec.confidence},
                }
                persist_decision(
                    session,
                    run_id=run_id,
                    nct_id=nct_id,
                    sponsor_text=sponsor_text,
                    decision=decision,
                    leader_features=decision["features"],
                    leader_meta=decision["leader_meta"],
                    decided_by="llm",
                    notes_md=(llm_dec.rationale or "")[:2000] or None,
                )
                if apply_trial:
                    session.execute(
                        text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                        {"cid": llm_dec.company_id, "nct": nct_id},
                    )
                try:
                    if upsert_alias_from_sponsor(session, llm_dec.company_id, sponsor_text):
                        console.print(f"[dim][alias] + {nct_id} → company {llm_dec.company_id}[/dim]")
                except Exception as e:
                    console.print(f"[dim][alias] ! {nct_id} → company {llm_dec.company_id}: {e}[/dim]")
            elif llm_dec.mode == "review":
                _enqueue_review(
                    session,
                    run_id=run_id,
                    nct_id=nct_id,
                    sponsor_text=sponsor_text,
                    candidates=_serialize_scored(scored, topn=25),
                    reason="llm_review",
                )
            else:
                console.print("[blue]LLM reject: not persisted.[/blue]")
        else:
            console.print("[yellow]--persist requested but --nct missing; skipping DB write.[/yellow]")

    if json_out:
        blob = {
            "mode": llm_dec.mode,
            "company_id": llm_dec.company_id,
            "p": 1.0 if llm_dec.mode == "accept" else 0.0,
            "top2_margin": 1.0 if llm_dec.mode == "accept" else 0.0,
            "leader_features": {},
            "leader_meta": {"source": "llm", "confidence": llm_dec.confidence},
            "run_id": run_id,
            "nct_id": nct_id,
        }
        console.print_json(json.dumps(blob, ensure_ascii=False))
    
    # Print trial footer for clear separation
    _print_trial_footer()


# --------------------------------------------------------------------------- #
# Commands (thin wrappers)
# --------------------------------------------------------------------------- #

@app.command("resolve-one")
def resolve_one(
    sponsor: str = typer.Argument(..., help="Sponsor text (use `resolve-nct` if you have an NCT ID)"),
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg", help="Path to resolver.yaml"),
    k: int = typer.Option(25, help="Top-K candidates to consider"),
    json_out: bool = typer.Option(False, help="Print a JSON result blob"),
    skip_det: bool = typer.Option(False, help="Skip deterministic step"),
    persist: bool = typer.Option(False, "--persist", help="Write decision/features to DB"),
    nct: Optional[str] = typer.Option(None, "--nct", help="NCT ID for persistence/context"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Resolver run ID"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm"),
):
    cfg = _load_yaml(cfg_path)
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")
    with get_session() as s:
        # Create resolver run record if persisting
        if persist:
            create_resolver_run(s, run_id=run_id, decider=decider)
        
        opts = FlowOptions(
            cfg=cfg,
            run_id=run_id,
            persist=persist,
            decider=decider,
            apply_trial=False,
            skip_det=skip_det,
            k=k,
            json_out=json_out,
        )
        run_resolution(
            s,
            sponsor_text=sponsor,
            nct_id=nct,
            options=opts,
            ctx_override=None,
        )


@app.command("resolve-nct")
def resolve_nct(
    nct_id: str = typer.Argument(..., help="NCT ID (e.g., NCT01234567)"),
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg", help="Path to resolver.yaml"),
    k: int = typer.Option(50, help="Top-K candidates to consider"),
    json_out: bool = typer.Option(False, help="Print a JSON result blob"),
    persist: bool = typer.Option(False, "--persist", help="Write decision/features/queue"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial", help="Update trials.sponsor_company_id on accept"),
    skip_det: bool = typer.Option(False, help="Skip deterministic step"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Resolver run ID"),
):
    cfg = _load_yaml(cfg_path)
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")
    with get_session() as s:
        row = s.execute(
            text("SELECT trial_id, sponsor_text FROM trials WHERE nct_id = :nct"),
            {"nct": nct_id},
        ).first()
        if not row:
            console.print(f"[red]nct_id not found: {nct_id}[/red]")
            raise typer.Exit(1)

        trial_id, sponsor_text = int(row[0]), (row[1] or "")
        
        # Create resolver run record if persisting
        if persist:
            create_resolver_run(s, run_id=run_id, decider=decider)
            # Create resolver input record
            create_resolver_input(s, run_id=run_id, nct_id=nct_id, sponsor_text=sponsor_text)
        
        tp = load_trial_party(s, trial_id, nct_id, sponsor_text)
        ctx_full = derive_context(tp)

        # Trial overview printout (unchanged behavior)
        tctx = {
            "domains": ctx_full.domains,
            "drug_codes": ctx_full.drug_codes,
            "nih_or_nci_hint": any(k in (sponsor_text or "").lower() for k in ("nih", "national cancer institute", "nci")),
        }
        _print_trial_overview(console, nct_id, sponsor_text, tctx)

        opts = FlowOptions(
            cfg=cfg,
            run_id=run_id,
            persist=persist,
            decider=decider,
            apply_trial=apply_trial,
            skip_det=skip_det,
            k=k,
            json_out=json_out,
        )
        run_resolution(
            s,
            sponsor_text=sponsor_text,
            nct_id=nct_id,
            options=opts,
            ctx_override={"domains": ctx_full.domains, "drug_code_hit": bool(ctx_full.drug_codes)},
        )


@app.command("resolve-batch")
def resolve_batch(
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg"),
    limit: int = typer.Option(25, help="How many unresolved trials to sample"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Tag all writes with this run"),
    persist: bool = typer.Option(False, "--persist/--dry-run", help="Write decisions/features/queue"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm (audit field)"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial", help="Update trials.sponsor_company_id on accept"),
    skip_det: bool = typer.Option(False, "--skip-det", help="Skip deterministic step"),
    k: int = typer.Option(50, help="Top-K candidates to consider"),
    force_review_on_reject: bool = typer.Option(False, "--force-review-on-reject", help="Also enqueue rejects"),
):
    cfg = _load_yaml(cfg_path)
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")
    with get_session() as s:
        # Create resolver run record if persisting
        if persist:
            create_resolver_run(s, run_id=run_id, decider=decider)
        
        rows = s.execute(
            text(
                """
                SELECT t.nct_id, t.sponsor_text
                  FROM trials t
                 WHERE t.sponsor_text IS NOT NULL
                   AND (t.sponsor_company_id IS NULL OR t.sponsor_company_id = 0)
                   AND NOT EXISTS (
                         SELECT 1
                           FROM resolver_ignore_sponsor ig
                          WHERE t.sponsor_text ~* ig.pattern
                   )
                 ORDER BY t.nct_id
                 LIMIT :lim
                """
            ),
            {"lim": limit},
        ).fetchall()

        opts = FlowOptions(
            cfg=cfg,
            run_id=run_id,
            persist=persist,
            decider=decider,
            apply_trial=apply_trial,
            skip_det=skip_det,
            k=k,
            json_out=False,  # batch: keep console output only
        )

        for nct_id, sponsor_text in rows:
            # Create resolver input record if persisting
            if persist:
                create_resolver_input(s, run_id=run_id, nct_id=nct_id, sponsor_text=sponsor_text or "")
            
            # Thin wrapper—delegate to unified flow
            try:
                run_resolution(
                    s,
                    sponsor_text=sponsor_text or "",
                    nct_id=nct_id,
                    options=opts,
                    ctx_override=None,  # will compute short context if needed
                )
            except typer.Exit:
                # No candidates case: optionally enqueue empty review
                if persist and force_review_on_reject:
                    _enqueue_review(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text or "",
                        candidates=[],
                        reason="force_review",
                    )
                continue

# --- Review queue (stable: review_queue) ------------------------------------- #

def _fetch_pending(session, limit: int = 20):
    rows = session.execute(
        text(
            """
            SELECT rq_id, run_id, nct_id, sponsor_text,
                   jsonb_array_length(candidates) AS n_cands,
                   created_at
            FROM review_queue
            ORDER BY created_at ASC
            LIMIT :lim
            """
        ),
        {"lim": limit},
    ).fetchall()
    return rows


def _fetch_review_item(session, rq_id: int):
    row = session.execute(
        text(
            """
            SELECT rq_id, run_id, nct_id, sponsor_text, candidates, created_at
            FROM review_queue
            WHERE rq_id = :rq
            """
        ),
        {"rq": rq_id},
    ).first()
    return row


@app.command("review-list")
def review_list(limit: int = typer.Option(20, help="How many pending to list")):
    with get_session() as s:
        rows = _fetch_pending(s, limit=limit)
        if not rows:
            console.print("[green]No pending items.[/green]")
            return
        table = Table(title="Pending review_queue items")
        table.add_column("rq_id", justify="right")
        table.add_column("run_id")
        table.add_column("nct_id")
        table.add_column("#cands", justify="right")
        table.add_column("created_at")
        for r in rows:
            table.add_row(str(r.rq_id), r.run_id, r.nct_id, str(r.n_cands), str(r.created_at))
        console.print(table)


@app.command("review-show")
def review_show(rq_id: int = typer.Argument(...)):
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        console.rule(f"[bold]Review #{row.rq_id}[/bold]  (run_id={row.run_id}  nct={row.nct_id})")
        console.print(f"[dim]{row.created_at}[/dim]")
        console.print(f"[cyan]Sponsor:[/cyan] {row.sponsor_text}")

        # Trial overview (best effort)
        sponsor_norm = norm_name(row.sponsor_text or "")
        tctx = _fetch_trial_overview(s, row.nct_id, row.sponsor_text or "")
        _print_trial_overview(console, row.nct_id, row.sponsor_text or "", tctx)

        # Human-readable candidates
        cands = list(row.candidates or [])
        printed = False
        try:
            human = _enrich_candidates_human(s, cands, sponsor_norm)
            if human:
                _print_candidates_human(console, human)
                printed = True
        except (ProgrammingError, DBAPIError):
            s.rollback()

        if not printed:
            _print_candidates_simple(console, cands)


@app.command("review-accept")
def review_accept(
    rq_id: int = typer.Argument(..., help="review_queue.rq_id to accept"),
    company_id: int = typer.Option(..., "--company-id", "-c", help="Chosen company_id"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial"),
    decider: str = typer.Option("human", "--decider"),
):
    """Accept a review_queue item, write resolver_decisions (+update trials if requested), then delete from queue."""
    with get_session() as s:
        row = s.execute(
            text("SELECT nct_id, sponsor_text FROM review_queue WHERE rq_id=:id"),
            {"id": rq_id},
        ).first()
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        nct_id, sponsor_text = row
        run_id = datetime.utcnow().strftime("review-%Y%m%dT%H%M%SZ")

        dec = {
            "mode": "accept",
            "company_id": company_id,
            "p": 1.0,
            "top2_margin": 1.0,
            "features": {},
            "leader_meta": {"source": "review", "rq_id": rq_id},
        }

        persist_decision(
            s,
            run_id=run_id,
            nct_id=nct_id,
            sponsor_text=sponsor_text,
            decision=dec,
            decided_by=decider,
            leader_features=dec["features"],
            leader_meta=dec["leader_meta"],
        )

        if apply_trial and company_id:
            s.execute(
                text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                {"cid": company_id, "nct": nct_id},
            )

        try:
            if upsert_alias_from_sponsor(s, company_id, sponsor_text or ""):
                console.print(f"[dim][alias] + rq:{rq_id} → company {company_id}[/dim]")
        except Exception as e:
            console.print(f"[dim][alias] ! rq:{rq_id} → company {company_id}: {e}[/dim]")

        s.execute(text("DELETE FROM review_queue WHERE rq_id=:id"), {"id": rq_id})
        s.commit()

        console.print(
            f"[green]Accepted[/green] rq_id={rq_id} nct={nct_id} -> cid={company_id}"
            + (" [dim](trials updated)[/dim]" if apply_trial else "")
        )


@app.command("review-reject")
def review_reject(
    rq_id: int = typer.Argument(...),
    label: bool = typer.Option(False, "--label/--no-label", help="If true and table exists, write resolver_labels negative for the top candidate"),
):
    """Reject/skip a queue item (delete). Optionally record a negative label for the top candidate if resolver_labels exists."""
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        if label:
            exists = s.execute(text("SELECT to_regclass('resolver_labels')")).scalar()
            if exists:
                cands = list(row.candidates or [])
                cands.sort(key=lambda x: x.get("p", 0.0), reverse=True)
                if cands:
                    top_cid = int(cands[0].get("company_id"))
                    s.execute(
                        text(
                            """
                            INSERT INTO resolver_labels
                                (nct_id, sponsor_text_norm, company_id, is_match, source)
                            VALUES
                                (:nct, :s_norm, :cid, FALSE, 'human')
                            """
                        ),
                        {"nct": row.nct_id, "s_norm": norm_name(row.sponsor_text), "cid": top_cid},
                    )
            else:
                console.print("[dim]resolver_labels not present; skipping label write.[/dim]")

        s.execute(text("DELETE FROM review_queue WHERE rq_id=:rq"), {"rq": rq_id})
        s.commit()
        console.print(f"[blue]Rejected[/blue] rq_id={rq_id}")


if __name__ == "__main__":
    app()
