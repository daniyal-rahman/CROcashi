# ncfd/src/ncfd/mapping/llm_decider.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    # SDK v1.x
    from openai import OpenAI  # pip install openai>=1.40.0
except Exception as e:  # pragma: no cover
    OpenAI = None  # defer import error until first use


@dataclass
class LlmDecision:
    mode: str                    # "accept" | "review" | "reject"
    company_id: Optional[int]    # required when mode == "accept"
    confidence: float            # 0..1 (heuristic self-report)
    rationale: str               # short explanation
    flags: List[str]             # any extra signals


def _client() -> Any:
    if OpenAI is None:
        raise RuntimeError(
            "openai package not installed. `pip install openai>=1.40.0`"
        )
    kwargs = {}
    if os.getenv("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
    if os.getenv("OPENAI_ORG_ID"):
        kwargs["organization"] = os.getenv("OPENAI_ORG_ID")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"), **kwargs)


def _system_prompt() -> str:
    return (
        "You are a strict entity resolver for clinical trial sponsors. "
        "Given a sponsor string and candidate companies with features, "
        "choose a bucket: accept (if one candidate is a near-certain match), "
        "review (plausible but not certain), or reject (no plausible match). "
        "Prefer strong signals: exact/near-exact name; acronym exact; domain root match; "
        "ticker hit; high string similarity; presence of drug-code in context. "
        "Avoid matching academic groups, hospitals, foundations, or government institutes to companies. "
        "Output JSON only."
    )


def _user_prompt(nct_id: str, sponsor_text: str, context: Dict[str, Any], cands: List[Dict[str, Any]]) -> str:
    data = {
        "nct_id": nct_id,
        "sponsor_text": sponsor_text,
        "context": {
            "domains": context.get("domains", []),
            "drug_code_hit": bool(context.get("drug_code_hit")),
        },
        "candidates": [
            {
                "company_id": int(c.get("company_id")),
                "name": c.get("name"),
                "ticker": c.get("ticker"),
                "exchange": c.get("exchange"),
                "website_domain": c.get("website_domain") or (c.get("domains", [None])[0]),
                "sim": float(c.get("sim", 0.0)),
                "features": c.get("features") or {},
            }
            for c in cands
        ],
        "task": {
            "decision_buckets": ["accept", "review", "reject"],
            "accept_criteria": [
                "clear lexical match OR",
                "very high similarity WITH corroborating domain/ticker OR",
                "acronym exact AND other evidence"
            ],
            "review_criteria": [
                "top candidate plausible but not decisive",
                "signals conflict or are weak"
            ],
            "reject_criteria": [
                "all candidates weak or academic/government/non-company",
                "sponsor looks like a consortium, hospital, foundation"
            ],
            "return_schema": {
                "mode": "accept|review|reject",
                "chosen_company_id": "int|null",
                "confidence": "float in [0,1]",
                "rationale": "string",
                "flags": "string[]"
            }
        }
    }
    return json.dumps(data, ensure_ascii=False)


def decide_with_llm(
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    candidates: List[Dict[str, Any]],
    context: Dict[str, Any],
    topk: int = 10,
) -> Tuple[LlmDecision, Dict[str, Any]]:
    """
    Call OpenAI and return the decision + raw response JSON (for logging).
    `candidates` can be raw retrieval rows or scored; if scored, include 'features' and 'p' in each dict.
    """
    model = os.getenv("OPENAI_MODEL_RESOLVER", "gpt-4o-mini")
    cli = _client()

    # sort strongest first if we have 'p' or 'sim'
    def keyf(c):
        if "p" in c:
            return float(c.get("p", 0.0))
        return float(c.get("sim", 0.0))

    cands_sorted = sorted(candidates, key=keyf, reverse=True)[:topk]

    # Build prompts
    system = _system_prompt()
    user = _user_prompt(nct_id, sponsor_text, context, cands_sorted)

    # Ask for strict JSON output
    # Prefer Responses API; fall back to Chat Completions if needed.
    try:
        resp = cli.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            response_format={"type": "json_object"},
        )
        # Responses API: aggregated text is in output_text, or tool the first output_message
        try:
            content = resp.output_text  # SDK convenience property
        except Exception:
            # Fallback: try to stitch text from the first output message
            content = json.dumps(resp.to_dict())  # last-ditch for debugging
    except Exception:
        # fallback to chat.completions (older SDKs)
        chat = cli.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        content = chat.choices[0].message.content

    try:
        data = json.loads(content)
    except Exception:
        # If model hiccups, return review with a flag
        return (
            LlmDecision(mode="review", company_id=None, confidence=0.0,
                        rationale="Model did not return valid JSON; routed to review.",
                        flags=["bad_json"]),
            {"raw": content},
        )

    mode = str(data.get("mode", "")).lower()
    if mode not in {"accept", "review", "reject"}:
        mode = "review"

    company_id = data.get("chosen_company_id")
    if mode == "accept":
        try:
            company_id = int(company_id)
        except Exception:
            # Cannot accept without a concrete company id; downgrade to review.
            mode = "review"
            company_id = None

    conf = float(data.get("confidence", 0.0))
    rationale = str(data.get("rationale", ""))[:2000]
    flags = data.get("flags") or []

    decision = LlmDecision(
        mode=mode,
        company_id=company_id,
        confidence=max(0.0, min(1.0, conf)),
        rationale=rationale,
        flags=[str(x) for x in flags],
    )
    raw = data
    return decision, raw
