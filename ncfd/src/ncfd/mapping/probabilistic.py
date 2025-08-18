from __future__ import annotations
import math, re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ncfd.mapping.normalize import (
    norm_name, strip_legal, tokens_of, acronym_of,
    has_academic_keywords, ticker_in_text
)
from ncfd.mapping.candidates import candidate_retrieval

# ---------- tiny Jaro–Winkler (no external deps) ----------
def _jaro(s: str, t: str) -> float:
    if s == t:
        return 1.0
    ls, lt = len(s), len(t)
    if ls == 0 or lt == 0:
        return 0.0
    mmax = max(ls, lt)
    match_dist = max(mmax // 2 - 1, 0)
    s_matches = [False]*ls
    t_matches = [False]*lt
    matches = 0
    transpositions = 0
    for i, ch in enumerate(s):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, lt)
        for j in range(start, end):
            if t_matches[j] or t[j] != ch:
                continue
            s_matches[i] = True
            t_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = 0
    for i in range(ls):
        if not s_matches[i]:
            continue
        while not t_matches[k]:
            k += 1
        if s[i] != t[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    return (matches/ls + matches/lt + (matches - transpositions)/matches) / 3.0

def _jaro_winkler(s: str, t: str, p: float = 0.1, max_l: int = 4) -> float:
    j = _jaro(s, t)
    # common prefix length L (max 4)
    L = 0
    for a, b in zip(s, t):
        if a != b or L >= max_l:
            break
        L += 1
    return j + L * p * (1 - j)

# ---------- helper: domains and "strong token" overlap ----------
_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.IGNORECASE)

def extract_domains(text: str) -> List[str]:
    if not text:
        return []
    ds = []
    for m in _DOMAIN_RE.finditer(text):
        dom = m.group(1).lower()
        ds.append(dom[4:] if dom.startswith("www.") else dom)
    return list(dict.fromkeys(ds))  # dedupe, keep order

_GENERIC_WEAK = {
    "bio","biosciences","biotech","pharma","pharmaceutical","pharmaceuticals",
    "therapeutic","therapeutics","inc","corp","ltd","plc","llc","company","holding","holdings"
}

def strong_tokens(s: str) -> List[str]:
    toks = tokens_of(s)
    return [t for t in toks if len(t) >= 6 and t not in _GENERIC_WEAK]

# ---------- feature builder ----------
def _token_set_ratio(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    A, B = set(a), set(b)
    inter = len(A & B)
    return (2.0 * inter) / (len(A) + len(B))

def build_features(sponsor_text: str, cand: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    context = context or {}
    s_norm = norm_name(sponsor_text)
    c_name_norm = norm_name(cand.get("name") or "")
    s_stripped = strip_legal(sponsor_text)

    jw_primary = _jaro_winkler(s_norm, c_name_norm)
    tsr = _token_set_ratio(tokens_of(s_norm), tokens_of(c_name_norm))

    ac_s = acronym_of(s_stripped)
    ac_c = acronym_of(cand.get("name") or "")
    acronym_exact = 1.0 if (ac_s and ac_s == ac_c) else 0.0

    sponsor_domains = extract_domains(sponsor_text) + [d.lower() for d in context.get("domains", [])]

    # NEW: consider both website_domain and any alias domains attached by candidate_retrieval
    cand_domains: List[str] = []
    if cand.get("website_domain"):
        cand_domains.append(str(cand["website_domain"]).lower())
    cand_domains.extend([d.lower() for d in cand.get("domains", []) if d])

    domain_root_match = 1.0 if sponsor_domains and any(dom in sponsor_domains for dom in cand_domains) else 0.0

    ticker_hit = 1.0 if ticker_in_text(cand.get("ticker"), sponsor_text) else 0.0
    academic_pen = 1.0 if has_academic_keywords(sponsor_text) else 0.0
    sto = _token_set_ratio(strong_tokens(sponsor_text), strong_tokens(cand.get("name") or ""))

    drug_code_hit = 1.0 if context.get("drug_code_hit") else 0.0
    extra_domain_hit = 1.0 if any(d in cand_domains for d in context.get("domains", [])) and cand_domains else 0.0

    return {
        "jw_primary": jw_primary,
        "token_set_ratio": tsr,
        "acronym_exact": acronym_exact,
        "domain_root_match": domain_root_match,
        "ticker_string_hit": ticker_hit,
        "academic_keyword_penalty": academic_pen,
        "strong_token_overlap": sto,
        "drug_code_hit": drug_code_hit,
        "extra_domain_hit": extra_domain_hit,
    }

# ---------- scoring & policy ----------
@dataclass
class Scored:
    company_id: int
    p: float
    features: Dict[str, float]
    meta: Dict[str, Any]

def _linpred(weights: Dict[str, float], feats: Dict[str, float], intercept: float) -> float:
    z = intercept
    for k, w in weights.items():
        z += w * float(feats.get(k, 0.0))
    return z

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def score_candidates(
    candidates: List[Dict[str, Any]],
    sponsor_text: str,
    weights: Dict[str, float],
    intercept: float,
    context: Optional[Dict[str, Any]] = None,
) -> List[Scored]:
    out: List[Scored] = []
    for c in candidates:
        feats = build_features(sponsor_text, c, context=context)
        p = _sigmoid(_linpred(weights, feats, intercept))
        out.append(Scored(company_id=c["company_id"], p=p, features=feats, meta=c))
    # add top-2 margin for policy
    out.sort(key=lambda x: x.p, reverse=True)
    return out

@dataclass
class ProbDecision:
    mode: str             # "accept" | "review" | "reject"
    company_id: Optional[int]
    p: float
    top2_margin: float
    features: Dict[str, float]
    leader_meta: Dict[str, Any]

def decide_probabilistic(
    scored: List[Scored],
    tau_accept: float,
    review_low: float,
    min_top2_margin: float,
) -> ProbDecision:
    if not scored:
        return ProbDecision("reject", None, 0.0, 0.0, {}, {})
    leader = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    margin = leader.p - (runner.p if runner else 0.0)

    if leader.p >= tau_accept and margin >= min_top2_margin:
        return ProbDecision("accept", leader.company_id, leader.p, margin, leader.features, leader.meta)
    if leader.p >= review_low:
        return ProbDecision("review", leader.company_id, leader.p, margin, leader.features, leader.meta)
    return ProbDecision("reject", None, leader.p, margin, leader.features, leader.meta)

# ---------- end-to-end for a trial’s sponsor (Phase-3 1.4) ----------
def resolve_probabilistic(
    session: Session,
    sponsor_text: str,
    cfg: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    k: int = 50,
) -> ProbDecision:
    cands = candidate_retrieval(session, norm_name(sponsor_text), k=k)
    weights = cfg["model"]["weights"]
    intercept = cfg["model"]["intercept"]
    th = cfg["thresholds"]
    scored = score_candidates(cands, sponsor_text, weights, intercept, context=context)
    return decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])
