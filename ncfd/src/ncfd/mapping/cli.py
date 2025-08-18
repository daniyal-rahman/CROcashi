# ncfd/src/ncfd/mapping/cli.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from sqlalchemy import text

import typer
from rich.console import Console
from rich.table import Table

from ncfd.db.session import get_session
from ncfd.mapping.normalize import norm_name
from ncfd.mapping.candidates import candidate_retrieval
from ncfd.mapping.probabilistic import score_candidates, decide_probabilistic
from ncfd.mapping.resolve_service import resolve_sponsor  # optional (if you added it)
from ncfd.mapping.deterministic import resolve_company as det_resolve
from datetime import datetime
from ncfd.mapping.persist import persist_decision, persist_candidate_features, enqueue_review
# If you didn't add resolve_service.py yet, we won't use it here.

app = typer.Typer(add_completion=False)
console = Console()

def _load_yaml(path: str | Path) -> Dict[str, Any]:
    import yaml
    p = Path(path)
    candidates = [
        p,
        Path("config/resolver.yaml"),
        Path("ncfd/config/resolver.yaml"),
    ]
    for cand in candidates:
        if cand.exists():
            return yaml.safe_load(cand.read_text())
    raise FileNotFoundError(f"resolver config not found; tried: {', '.join(str(c) for c in candidates)}")

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
    table = Table(title=f"Top {min(topn, len(scored))} by p (probabilistic)")
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
        margin = (scored[i-1].p - scored[i].p) if i < len(scored) else s.p
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

def _print_deterministic(det, sponsor: str):
    table = Table(title="Deterministic Resolution")
    table.add_column("Method")
    table.add_column("Company ID", justify="right")
    table.add_column("Evidence")
    ev = ", ".join(f"{k}={v}" for k, v in det.evidence.items())
    table.add_row(det.method, str(det.company_id), ev)
    console.print(table)
    console.rule("Decision")
    console.print(
        "mode: [bold]deterministic:accept[/bold] | "
        f"leader company_id: [bold]{det.company_id}[/bold] | p: 1.0000 | margin: 1.0000"
    )

@app.command("resolve-one")
def resolve_one(
    sponsor: str = typer.Argument(..., help="Sponsor text from CT.gov"),
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg", help="Path to resolver.yaml"),
    k: int = typer.Option(25, help="Top-K candidates to consider"),
    json_out: bool = typer.Option(False, help="Print a JSON result blob"),
    skip_det: bool = typer.Option(False, help="Skip deterministic step (for testing)"),
    persist: bool = typer.Option(False, "--persist", help="Write decision/features to DB"),
    nct: Optional[str] = typer.Option(None, "--nct", help="NCT ID for persistence"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Resolver run ID"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm"),
):
    cfg = _load_yaml(cfg_path)
    run_id = run_id or datetime.utcnow().strftime("resolver-%Y%m%dT%H%M%SZ")

    with get_session() as s:
        # deterministic
        if not skip_det:
            det = det_resolve(s, sponsor)
            if det:
                _print_deterministic(det, sponsor)

                if persist and nct:
                    persist_decision(
                        s, run_id=run_id, nct_id=nct, sponsor_text=sponsor,
                        decision=det, leader_features={}, leader_meta={},
                        decided_by=decider, notes_md=None
                    )
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
        _print_candidates(cands, title="Candidate Retrieval (trigram on *_norm)")

        weights = cfg["model"]["weights"]; intercept = cfg["model"]["intercept"]
        scored = score_candidates(cands, sponsor, weights, intercept, context=None)
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
            # Always store candidate features for audit/calibration
            persist_candidate_features(s, run_id=run_id, nct_id=nct, sponsor_text=sponsor, scored_candidates=scored)

            if decision.mode == "accept":
                persist_decision(
                    s, run_id=run_id, nct_id=nct, sponsor_text=sponsor,
                    decision=decision, leader_features=decision.features, leader_meta=decision.leader_meta,
                    decided_by=decider, notes_md=None
                )
                console.print(f"[green]Persisted probabilistic ACCEPT[/green] run_id={run_id} nct={nct}")
            elif decision.mode == "review":
                enqueue_review(
                    s, run_id=run_id, nct_id=nct, sponsor_text=sponsor, candidates=scored, reason="prob_review"
                )
                console.print(f"[yellow]Enqueued review[/yellow] run_id={run_id} nct={nct}")
            else:
                console.print("[blue]Reject: not persisted (by design).[/blue]")
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

@app.command("resolve-batch")
def resolve_batch(
    cfg_path: str = typer.Option("config/resolver.yaml", "--cfg"),
    limit: int = typer.Option(25, help="How many unresolved trials to sample"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Tag all writes with this run"),
    persist: bool = typer.Option(False, "--persist/--dry-run", help="Write decisions/features/queue"),
    decider: str = typer.Option("auto", "--decider", help="auto|human|llm (audit field)"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial", help="Update trials.sponsor_company_id on accept"),
    skip_det: bool = typer.Option(False, "--skip-det", help="Skip deterministic step"),
    force_review_on_reject: bool = typer.Option(False, "--force-review-on-reject", help="Dev-only: enqueue even if reject"),
):
    """
    Pull unresolved trials and run det->prob workflow.
    With --persist, writes to resolver_decisions/resolver_features/review_queue (+trials if --apply-trial).
    """
    from ncfd.mapping.persist import persist_decision, persist_candidate_features, enqueue_review
    cfg = _load_yaml(cfg_path)
    th = cfg["thresholds"]

    with get_session() as s:
        rows = s.execute(
            text("""
                SELECT nct_id, sponsor_text
                FROM trials
                WHERE sponsor_text IS NOT NULL
                  AND (sponsor_company_id IS NULL OR sponsor_company_id = 0)
                ORDER BY nct_id
                LIMIT :lim
            """),
            {"lim": limit},
        ).fetchall()

        for nct_id, sponsor_text in rows:
            # deterministic first (unless skipped)
            det = None
            if not skip_det:
                det = det_resolve(s, sponsor_text)

            if det:
                console.print(f"[green]{nct_id}[/green] :: det:{det.method} -> cid={det.company_id}")
                if persist and run_id:
                    persist_decision(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        decision=det,
                        decided_by=decider,
                    )
                    if apply_trial:
                        s.execute(text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                                  {"cid": det.company_id, "nct": nct_id})
                continue  # next trial

            # probabilistic
            qnorm = norm_name(sponsor_text)
            cands = candidate_retrieval(s, qnorm, k=50)
            scored = score_candidates(cands, sponsor_text, cfg["model"]["weights"], cfg["model"]["intercept"])
            dec = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

            console.print(
                f"[cyan]{nct_id}[/cyan] :: {sponsor_text[:60]!r} -> {dec.mode} "
                f"(cid={dec.company_id}, p={dec.p:.3f}, margin={dec.top2_margin:.3f})"
            )

            if persist and run_id:
                persist_candidate_features(s, run_id=run_id, nct_id=nct_id, sponsor_text=sponsor_text, scored_candidates=scored)
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
                        s.execute(text("UPDATE trials SET sponsor_company_id=:cid WHERE nct_id=:nct"),
                                  {"cid": dec.company_id, "nct": nct_id})
                elif dec.mode == "review" or force_review_on_reject:
                    enqueue_review(
                        s,
                        run_id=run_id,
                        nct_id=nct_id,
                        sponsor_text=sponsor_text,
                        candidates=scored,
                        reason="prob_review" if dec.mode == "review" else "force_review",
                    )

# --- Review queue utilities ---------------------------------------------------
def _fetch_pending(session, limit: int = 20):
    rows = session.execute(
        text("""
            SELECT rq_id, run_id, nct_id, sponsor_text,
                   jsonb_array_length(candidates_jsonb) AS n_cands,
                   created_at
            FROM resolver_review_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :lim
        """),
        {"lim": limit},
    ).fetchall()
    return rows

def _fetch_review_item(session, rq_id: int):
    row = session.execute(
        text("""
            SELECT rq_id, run_id, nct_id, sponsor_text,
                   sponsor_text_norm, candidates_jsonb, created_at
            FROM resolver_review_queue
            WHERE rq_id = :rq
        """),
        {"rq": rq_id},
    ).first()
    return row

def _print_review_item(row):
    console.rule(f"[bold]Review #{row.rq_id}[/bold]  (run_id={row.run_id}  nct={row.nct_id})")
    console.print(f"[dim]{row.created_at}[/dim]")
    console.print(f"[cyan]Sponsor:[/cyan] {row.sponsor_text}")

    # Candidates
    table = Table(title="Candidates (sorted by p desc)")
    table.add_column("Rank", justify="right")
    table.add_column("Company ID", justify="right")
    table.add_column("p", justify="right")
    table.add_column("jw")
    table.add_column("tsr")
    table.add_column("acro")
    table.add_column("domain")
    table.add_column("ticker")
    table.add_column("strong_tok")

    cands = list(row.candidates_jsonb or [])
    cands.sort(key=lambda x: x.get("p", 0.0), reverse=True)
    for i, c in enumerate(cands, 1):
        f = c.get("features", {})
        table.add_row(
            str(i),
            str(c.get("company_id")),
            f"{c.get('p', 0.0):.3f}",
            f"{f.get('jw_primary', 0.0):.3f}",
            f"{f.get('token_set_ratio', 0.0):.3f}",
            f"{f.get('acronym_exact', 0.0):.0f}",
            f"{f.get('domain_root_match', 0.0):.0f}",
            f"{f.get('ticker_string_hit', 0.0):.0f}",
            f"{f.get('strong_token_overlap', 0.0):.3f}",
        )
    console.print(table)

# List pending items
@app.command("review-list")
def review_list(limit: int = typer.Option(20, help="How many pending to list")):
    with get_session() as s:
        rows = _fetch_pending(s, limit=limit)
        if not rows:
            console.print("[green]No pending items.[/green]")
            return
        table = Table(title="Pending resolver_review_queue items")
        table.add_column("rq_id", justify="right")
        table.add_column("run_id")
        table.add_column("nct_id")
        table.add_column("#cands", justify="right")
        table.add_column("created_at")
        for r in rows:
            table.add_row(str(r.rq_id), r.run_id, r.nct_id, str(r.n_cands), str(r.created_at))
        console.print(table)

# Show one pending item with features
@app.command("review-show")
def review_show(rq_id: int = typer.Argument(...)):
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)
        _print_review_item(row)

# Accept a review item (choose company_id; default = top candidate)
@app.command("review-accept")
def review_accept(
    rq_id: int = typer.Argument(...),
    company_id: Optional[int] = typer.Option(None, "--company-id", help="Override; default = top-p candidate"),
    decider: str = typer.Option("human", "--decider"),
    apply_trial: bool = typer.Option(False, "--apply-trial/--no-apply-trial",
                                     help="Update trials.sponsor_company_id"),
    label: bool = typer.Option(True, "--label/--no-label", help="Write resolver_labels = is_match=true"),
):
    from ncfd.mapping.persist import persist_decision
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        cands = list(row.candidates_jsonb or [])
        cands.sort(key=lambda x: x.get("p", 0.0), reverse=True)
        if not cands:
            console.print("[red]No candidates present.[/red]")
            raise typer.Exit(1)

        leader = cands[0]
        chosen_cid = int(company_id or leader.get("company_id"))
        chosen_p = float(leader.get("p", 0.0) if (company_id is None or chosen_cid == leader.get("company_id")) else 1.0)
        leader_features = leader.get("features", {}) if (company_id is None or chosen_cid == leader.get("company_id")) else {}

        # Persist decision (mark as human:accept)
        class _HumanDecision:
            def __init__(self, company_id, p, top2_margin, features):
                self.company_id = company_id
                self.p = p
                self.top2_margin = 1.0
                self.features = features
                self.leader_meta = {}

        dec = _HumanDecision(chosen_cid, chosen_p, 1.0, leader_features)
        persist_decision(
            s,
            run_id=row.run_id,
            nct_id=row.nct_id,
            sponsor_text=row.sponsor_text,
            decision=dec,
            leader_features=leader_features,
            leader_meta={"source": "review_queue", "rq_id": rq_id},
            decided_by=decider,
            notes_md=None,
        )

        # Mark queue as resolved
        s.execute(
            text("UPDATE resolver_review_queue SET status='resolved', resolved_at=now() WHERE rq_id=:rq"),
            {"rq": rq_id},
        )

        # Optional: apply to trials
        if apply_trial:
            s.execute(
                text("""
                    UPDATE trials
                       SET sponsor_company_id = :cid
                     WHERE nct_id = :nct
                """),
                {"cid": chosen_cid, "nct": row.nct_id},
            )

        # Optional: label for training
        if label:
            s.execute(
                text("""
                    INSERT INTO resolver_labels
                        (nct_id, sponsor_text_norm, company_id, is_match, source)
                    VALUES
                        (:nct, :s_norm, :cid, TRUE, 'human')
                """),
                {"nct": row.nct_id, "s_norm": norm_name(row.sponsor_text), "cid": chosen_cid},
            )

        console.print(f"[green]Accepted[/green] rq_id={rq_id} -> company_id={chosen_cid}")

# Reject a review item (mark resolved; optional negative label)
@app.command("review-reject")
def review_reject(
    rq_id: int = typer.Argument(...),
    label: bool = typer.Option(False, "--label/--no-label",
                               help="If true, write resolver_labels with is_match=false for top candidate"),
):
    with get_session() as s:
        row = _fetch_review_item(s, rq_id)
        if not row:
            console.print(f"[red]No review item rq_id={rq_id}[/red]")
            raise typer.Exit(1)

        s.execute(
            text("UPDATE resolver_review_queue SET status='resolved', resolved_at=now() WHERE rq_id=:rq"),
            {"rq": rq_id},
        )

        if label:
            cands = list(row.candidates_jsonb or [])
            cands.sort(key=lambda x: x.get("p", 0.0), reverse=True)
            if cands:
                top_cid = int(cands[0].get("company_id"))
                s.execute(
                    text("""
                        INSERT INTO resolver_labels
                            (nct_id, sponsor_text_norm, company_id, is_match, source)
                        VALUES
                            (:nct, :s_norm, :cid, FALSE, 'human')
                    """),
                    {"nct": row.nct_id, "s_norm": norm_name(row.sponsor_text), "cid": top_cid},
                )
        console.print(f"[blue]Rejected[/blue] rq_id={rq_id}")

if __name__ == "__main__":
    app()
