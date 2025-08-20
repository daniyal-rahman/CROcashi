# ncfd/src/ncfd/mapping/cli.py
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB

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
)
from ncfd.mapping.det import det_resolve, DetDecision
from ncfd.mapping.deterministic import resolve_company as det_exact_resolve
from ncfd.mapping.alias_promotion import upsert_alias_from_sponsor

app = typer.Typer(add_completion=False)
console = Console()

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _hydrate_company_facts(session, company_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not company_ids:
        return {}
    facts: Dict[int, Dict[str, Any]] = {cid: {} for cid in company_ids}

    # 1) canonical name + CIK
    rows = session.execute(
        text("""
            SELECT company_id, name, COALESCE(cik,0) AS cik
            FROM companies
            WHERE company_id = ANY(:ids)
        """),
        {"ids": company_ids},
    ).mappings().all()
    for r in rows:
        facts[int(r["company_id"])].update({"name": r["name"], "cik": int(r["cik"]) or None})

    # 2) aliases (top few: legal, aka, former_name)
    alias_rows = session.execute(
        text("""
            SELECT company_id, alias, alias_type
            FROM company_aliases
            WHERE company_id = ANY(:ids)
            ORDER BY CASE alias_type
                       WHEN 'legal' THEN 0
                       WHEN 'aka' THEN 1
                       WHEN 'former_name' THEN 2
                       ELSE 3
                     END, created_at DESC
        """),
        {"ids": company_ids},
    ).mappings().all()
    from collections import defaultdict
    group_alias: Dict[int, list] = defaultdict(list)
    for r in alias_rows:
        cid = int(r["company_id"])
        if len(group_alias[cid]) < 5:  # cap to keep output tidy
            group_alias[cid].append(f"{r['alias']} ({r['alias_type']})")
    for cid, arr in group_alias.items():
        facts[cid]["aliases"] = arr

    # 3) active tickers + exchange
    tick_rows = session.execute(
        text("""
            SELECT s.company_id, s.ticker, e.code AS exch
            FROM securities s
            JOIN exchanges e ON e.exchange_id = s.exchange_id
            WHERE s.company_id = ANY(:ids) AND s.status = 'active'
            ORDER BY lower(s.effective_range) DESC
        """),
        {"ids": company_ids},
    ).mappings().all()
    tmap: Dict[int, list] = defaultdict(list)
    for r in tick_rows:
        cid = int(r["company_id"])
        tmap[cid].append(f"{r['ticker']}:{r['exch']}")
    for cid, arr in tmap.items():
        facts[cid]["tickers"] = arr

    return facts

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
    for i, s in enumerate(scored[:topn], 1):
        f = s.features
        margin = (s.p - scored[i].p) if i < topn else s.p
        table.add_row(
            str(i),
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


def _print_deterministic(det: DetDecision, sponsor: str):
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
    stmt = (
        text(
            """
            INSERT INTO review_queue (run_id, nct_id, sponsor_text, candidates, reason)
            VALUES (:run_id, :nct_id, :sponsor_text, :candidates, :reason)
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
            "candidates": candidates,
            "reason": reason,
        },
    )

# --------------------------------------------------------------------------- #
# Commands
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
    """Resolve a single sponsor string."""
    cfg = _load_yaml(cfg_path)
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")

    with get_session() as s:
        # deterministic
        if not skip_det:
            # try exact/domain, then rules
            det: Optional[DetDecision] = None
            exact = det_exact_resolve(s, sponsor)
            if exact:
                det = DetDecision(company_id=exact.company_id, method=f"det_exact:{exact.method}", evidence=exact.evidence)
            else:
                det = det_resolve(s, sponsor)

            if det:
                _print_deterministic(det, sponsor)
                if persist and nct:
                    persist_decision(
                        s,
                        run_id=run_id,
                        nct_id=nct,
                        sponsor_text=sponsor,
                        decision=det,
                        leader_features={},
                        leader_meta={},
                        decided_by=decider,
                        notes_md=None,
                    )
                    # Promote accepted sponsor text as alias (legal/aka)
                    try:
                        if upsert_alias_from_sponsor(s, det.company_id, sponsor):
                            console.print(f"[dim][alias] + {nct} → company {det.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct} → company {det.company_id}: {e}[/dim]")
                    console.print(f"[green]Persisted deterministic decision[/green] run_id={run_id} nct={nct}")
                elif persist and not nct:
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
                        "nct_id": nct,
                    }
                    console.print_json(json.dumps(blob, ensure_ascii=False))
                return

        # probabilistic
        qnorm = norm_name(sponsor)
        cands = candidate_retrieval(s, qnorm, k=k)
        if not cands:
            console.print("[yellow]No candidates found.[/yellow]")
            raise typer.Exit(1)
        _print_candidates(cands, title="Candidate Retrieval")

        weights = cfg["model"]["weights"]
        intercept = cfg["model"]["intercept"]
        ctx = _make_context_for_prob(s, nct, sponsor)
        scored = score_candidates(cands, sponsor, weights, intercept, context=ctx)
        th = cfg["thresholds"]
        decision = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

        _print_top_features(scored, topn=min(10, len(scored)))
        console.rule("Decision")
        console.print(
            f"mode: [bold]{decision.mode}[/bold] | "
            f"leader company_id: [bold]{decision.company_id}[/bold] | "
            f"p: {decision.p:.4f} | margin: {decision.top2_margin:.4f}"
        )

        if persist and nct:
            persist_candidate_features(
                s,
                run_id=run_id,
                nct_id=nct,
                sponsor_text=sponsor,
                scored_candidates=_serialize_scored(scored, topn=25),
            )
            if decision.mode == "accept":
                persist_decision(
                    s,
                    run_id=run_id,
                    nct_id=nct,
                    sponsor_text=sponsor,
                    decision=decision,
                    leader_features=decision.features,
                    leader_meta=decision.leader_meta,
                    decided_by=decider,
                    notes_md=None,
                )
                # Promote accepted sponsor text as alias
                try:
                    if upsert_alias_from_sponsor(s, decision.company_id, sponsor):
                        console.print(f"[dim][alias] + {nct} → company {decision.company_id}[/dim]")
                except Exception as e:
                    console.print(f"[dim][alias] ! {nct} → company {decision.company_id}: {e}[/dim]")
                console.print(f"[green]Persisted probabilistic ACCEPT[/green] run_id={run_id} nct={nct}")
            elif decision.mode == "review":
                _enqueue_review(
                    s,
                    run_id=run_id,
                    nct_id=nct,
                    sponsor_text=sponsor,
                    candidates=_serialize_scored(scored, topn=25),
                    reason="prob_review",
                )
                console.print(f"[yellow]Enqueued review[/yellow] run_id={run_id} nct={nct}")
            else:
                console.print("[blue]Reject: not persisted.[/blue]")
        elif persist and not nct:
            console.print("[yellow]--persist requested but --nct missing; skipping DB write.[/yellow]")

        if json_out:
            blob = {
                "mode": decision.mode,
                "company_id": decision.company_id,
                "p": decision.p,
                "top2_margin": decision.top2_margin,
                "leader_features": decision.features,
                "leader_meta": decision.leader_meta,
                "run_id": run_id,
                "nct_id": nct,
            }
            console.print_json(json.dumps(blob, ensure_ascii=False))


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
    """
    Resolve a trial by NCT ID: fetch sponsor from trials, build context, run det → prob.
    """
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
        tp = load_trial_party(s, trial_id, nct_id, sponsor_text)
        ctx = derive_context(tp)

        # -------------------------- Deterministic path --------------------------
        det: Optional[DetDecision] = None
        if not skip_det and sponsor_text:
            exact = det_exact_resolve(s, sponsor_text)
            if exact:
                det = DetDecision(company_id=exact.company_id, method=f"det_exact:{exact.method}", evidence=exact.evidence)
            else:
                det = det_resolve(s, sponsor_text)

        if det:
            _print_deterministic(det, sponsor_text)
            if persist:
                persist_decision(
                    s,
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
                    s.execute(
                        text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                        {"cid": det.company_id, "nct": nct_id},
                    )
                # Promote accepted sponsor text as alias (legal/aka)
                try:
                    if upsert_alias_from_sponsor(s, det.company_id, sponsor_text):
                        console.print(f"[dim][alias] + {nct_id} → company {det.company_id}[/dim]")
                except Exception as e:
                    console.print(f"[dim][alias] ! {nct_id} → company {det.company_id}: {e}[/dim]")
            if json_out:
                console.print_json(
                    json.dumps(
                        {
                            "mode": f"deterministic:{det.method}",
                            "company_id": det.company_id,
                            "p": 1.0,
                            "top2_margin": 1.0,
                            "leader_features": {},
                            "leader_meta": {},
                            "evidence": det.evidence,
                            "run_id": run_id,
                            "nct_id": nct_id,
                            "context": {"domains": ctx.domains, "drug_codes": ctx.drug_codes},
                        },
                        ensure_ascii=False,
                    )
                )
            return
        # -----------------------------------------------------------------------

        # -------------------------- Probabilistic path --------------------------
        sponsor_for_match = sponsor_text or (tp.texts[0] if tp.texts else "")
        if not sponsor_for_match:
            console.print("[yellow]No sponsor text found; cannot resolve.[/yellow]")
            raise typer.Exit(1)

        cands = candidate_retrieval(s, norm_name(sponsor_for_match), k=k)
        if not cands:
            console.print("[yellow]No candidates found.[/yellow]")
            raise typer.Exit(1)
        _print_candidates(cands, title=f"Candidate Retrieval for {nct_id}")

        weights = cfg["model"]["weights"]
        intercept = cfg["model"]["intercept"]
        scored = score_candidates(
            cands,
            sponsor_for_match,
            weights,
            intercept,
            context={"domains": ctx.domains, "drug_code_hit": bool(ctx.drug_codes)},
        )
        th = cfg["thresholds"]
        dec = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

        _print_top_features(scored, topn=min(10, len(scored)))
        console.rule("Decision")
        console.print(
            f"mode: [bold]{dec.mode}[/bold] | leader company_id: [bold]{dec.company_id}[/bold] "
            f"| p: {dec.p:.4f} | margin: {dec.top2_margin:.4f}"
        )

        if persist:
            # skip if sponsor is ignored
            ignored = s.execute(
                text("SELECT EXISTS (SELECT 1 FROM resolver_ignore_sponsor WHERE :s ~* pattern)"),
                {"s": sponsor_text},
            ).scalar()
            if ignored:
                console.print(f"[dim]SKIP ignored sponsor[/dim] {nct_id} :: {sponsor_text!r}")
            else:
                persist_candidate_features(
                    s,
                    run_id=run_id,
                    nct_id=nct_id,
                    sponsor_text=sponsor_for_match,
                    scored_candidates=_serialize_scored(scored, topn=25),
                )
                if dec.mode == "accept":
                    persist_decision(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_for_match,
                        decision=dec,
                        leader_features=dec.features,
                        leader_meta=dec.leader_meta,
                        decided_by=decider,
                        notes_md=None,
                    )
                    if apply_trial:
                        s.execute(
                            text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                            {"cid": dec.company_id, "nct": nct_id},
                        )
                    # Promote accepted sponsor text as alias
                    try:
                        if upsert_alias_from_sponsor(s, dec.company_id, sponsor_for_match):
                            console.print(f"[dim][alias] + {nct_id} → company {dec.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct_id} → company {dec.company_id}: {e}[/dim]")
                elif dec.mode == "review":
                    _enqueue_review(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_for_match,
                        candidates=_serialize_scored(scored, topn=25),
                        reason="prob_review",
                    )

        if json_out:
            blob = {
                "mode": dec.mode,
                "company_id": dec.company_id,
                "p": dec.p,
                "top2_margin": dec.top2_margin,
                "leader_features": dec.features,
                "leader_meta": dec.leader_meta,
                "run_id": run_id,
                "nct_id": nct_id,
                "context": {"domains": ctx.domains, "drug_codes": ctx.drug_codes},
            }
            console.print_json(json.dumps(blob, ensure_ascii=False))
        # -----------------------------------------------------------------------


@app.command("resolve-batch")
def resolve_batch(
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg"),
    limit: int = typer.Option(25, help="How many unresolved trials to sample"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Tag all writes with this run"),
    persist: bool = typer.Option(False, "--persist/--dry-run", help="Write decisions/features/queue"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm (audit field)"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial", help="Update trials.sponsor_company_id on accept"),
    skip_det: bool = typer.Option(False, "--skip-det", help="Skip deterministic step"),
    force_review_on_reject: bool = typer.Option(False, "--force-review-on-reject", help="Also enqueue rejects"),
):
    """
    Pull unresolved trials and run det→prob. With --persist, writes to resolver_decisions /
    resolver_features / review_queue (+trials if --apply-trial).
    """
    cfg = _load_yaml(cfg_path)
    th = cfg["thresholds"]
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")

    with get_session() as s:
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

        for nct_id, sponsor_text in rows:
            det: Optional[DetDecision] = None
            if not skip_det and sponsor_text:
                exact = det_exact_resolve(s, sponsor_text)
                if exact:
                    det = DetDecision(company_id=exact.company_id, method=f"det_exact:{exact.method}", evidence=exact.evidence)
                else:
                    det = det_resolve(s, sponsor_text)

            if det and getattr(det, "company_id", None):
                console.print(f"[green]{nct_id}[/green] :: det:{det.method} -> cid={det.company_id}")
                if persist:
                    persist_decision(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        decision=det,
                        decided_by=decider,
                        leader_features={},
                        leader_meta={},
                    )
                    if apply_trial:
                        s.execute(
                            text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                            {"cid": det.company_id, "nct": nct_id},
                        )
                    # Promote accepted sponsor text as alias
                    try:
                        if upsert_alias_from_sponsor(s, det.company_id, sponsor_text):
                            console.print(f"[dim][alias] + {nct_id} → company {det.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct_id} → company {det.company_id}: {e}[/dim]")
                continue

            # probabilistic
            qnorm = norm_name(sponsor_text)
            cands = candidate_retrieval(s, qnorm, k=50)
            if not cands:
                console.print(f"[yellow]{nct_id}[/yellow] :: no candidates")
                if persist and force_review_on_reject:
                    _enqueue_review(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        candidates=[],  # nothing to show
                        reason="force_review",
                    )
                continue

            ctx = _make_context_for_prob(s, nct=None, sponsor_text=sponsor_text)
            scored = score_candidates(
                cands,
                sponsor_text,
                cfg["model"]["weights"],
                cfg["model"]["intercept"],
                context=ctx,
            )
            dec = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

            console.print(
                f"[cyan]{nct_id}[/cyan] :: {sponsor_text[:60]!r} -> {dec.mode} "
                f"(cid={dec.company_id}, p={dec.p:.3f}, margin={dec.top2_margin:.3f})"
            )

            if persist:
                # extra guard against ignoreds (race)
                ignored = s.execute(
                    text("SELECT EXISTS (SELECT 1 FROM resolver_ignore_sponsor WHERE :s ~* pattern)"),
                    {"s": sponsor_text},
                ).scalar()
                if ignored:
                    console.print(f"[dim]SKIP ignored sponsor[/dim] {nct_id} :: {sponsor_text!r}")
                    continue

                persist_candidate_features(
                    s,
                    run_id=run_id,
                    nct_id=nct_id,
                    sponsor_text=sponsor_text,
                    scored_candidates=_serialize_scored(scored, topn=25),
                )

                if dec.mode == "accept":
                    persist_decision(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        decision=dec,
                        leader_features=dec.features,
                        leader_meta=dec.leader_meta,
                        decided_by=decider,
                    )
                    if apply_trial:
                        s.execute(
                            text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                            {"cid": dec.company_id, "nct": nct_id},
                        )
                    # Promote accepted sponsor text as alias
                    try:
                        if upsert_alias_from_sponsor(s, dec.company_id, sponsor_text):
                            console.print(f"[dim][alias] + {nct_id} → company {dec.company_id}[/dim]")
                    except Exception as e:
                        console.print(f"[dim][alias] ! {nct_id} → company {dec.company_id}: {e}[/dim]")
                elif dec.mode == "review" or force_review_on_reject:
                    _enqueue_review(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        candidates=_serialize_scored(scored, topn=25),
                        reason="prob_review" if dec.mode == "review" else "force_review",
                    )

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


def _print_review_item(row):
    console.rule(f"[bold]Review #{row.rq_id}[/bold]  (run_id={row.run_id}  nct={row.nct_id})")
    console.print(f"[dim]{row.created_at}[/dim]")
    console.print(f"[cyan]Sponsor:[/cyan] {row.sponsor_text}")

    cands = list(row.candidates or [])
    cands.sort(key=lambda x: x.get("p", 0.0), reverse=True)

    # hydrate facts from DB
    ids = [int(c.get("company_id")) for c in cands if c.get("company_id")]
    facts = {}
    if ids:
        with get_session() as s2:
            facts = _hydrate_company_facts(s2, ids)

    table = Table(title="Candidates (human-readable)", show_lines=False)
    table.add_column("Rank", justify="right", no_wrap=True)
    table.add_column("p", justify="right", no_wrap=True)
    table.add_column("Company", overflow="fold")
    table.add_column("Aliases (few)", overflow="fold")
    table.add_column("Tickers", no_wrap=False)
    table.add_column("CIK", justify="right", no_wrap=True)
    table.add_column("Domain(s)", overflow="fold")
    table.add_column("jw", justify="right", no_wrap=True)
    table.add_column("tsr", justify="right", no_wrap=True)

    for i, c in enumerate(cands, 1):
        cid = c.get("company_id")
        f = c.get("features", {}) or {}
        meta = c.get("meta", {}) or {}

        # facts from DB (fallbacks to meta)
        ff = facts.get(int(cid), {}) if cid else {}
        name = ff.get("name") or meta.get("name") or f"company:{cid}"
        aliases = ", ".join(ff.get("aliases", [])[:3]) if ff.get("aliases") else ""
        tickers = ", ".join(ff.get("tickers", [])) if ff.get("tickers") else (meta.get("ticker") or "")
        cik = ff.get("cik") or ""
        # meta domains
        dom = ""
        if isinstance(meta.get("domains"), (list, tuple)) and meta["domains"]:
            dom = ", ".join(meta["domains"][:3])
        elif meta.get("website_domain"):
            dom = meta["website_domain"]

        table.add_row(
            str(i),
            f"{c.get('p', 0.0):.3f}",
            f"{name}  [dim](cid={cid})[/dim]",
            aliases,
            tickers,
            str(cik) if cik else "",
            dom or "",
            f"{f.get('jw_primary', 0.0):.3f}",
            f"{f.get('token_set_ratio', 0.0):.3f}",
        )

    console.print(table)


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
        _print_review_item(row)


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

        # minimal accept payload for persist_decision (probabilistic:accept semantics)
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

        # Promote accepted sponsor text as alias (legal/aka)
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
    label: bool = typer.Option(False, "--label/--no-label", help="If true and table exists, write resolver_labels negative for top candidate"),
):
    """Reject/skip a queue item (delete). Optionally record a negative label for the top candidate if resolver_labels exists."""
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        if label:
            # only if resolver_labels table exists
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
