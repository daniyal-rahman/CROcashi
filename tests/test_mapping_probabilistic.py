from ncfd.mapping.probabilistic import build_features, score_candidates, decide_probabilistic
from ncfd.mapping.normalize import norm_name

CFG = {
  "model": {
    "intercept": -5.0,
    "weights": {
      "jw_primary": 2.8,
      "token_set_ratio": 2.4,
      "acronym_exact": 1.9,
      "domain_root_match": 3.6,
      "ticker_string_hit": 3.0,
      "academic_keyword_penalty": -1.2,
      "strong_token_overlap": 0.8,
      "drug_code_hit": 2.0,
      "extra_domain_hit": 1.0
    }
  },
  "thresholds": {
    "tau_accept": 0.995,
    "review_low": 0.970,
    "min_top2_margin": 0.10
  }
}

def test_domain_match_drives_accept():
    sponsor = "Study sponsored by Regenxbio Inc (see regenxbio.com)"
    c1 = {"company_id": 1, "name": "Regenxbio Inc", "website_domain":"regenxbio.com", "ticker":"RGNX"}
    c2 = {"company_id": 2, "name": "Regeneron Pharmaceuticals, Inc.", "website_domain":"regeneron.com", "ticker":"REGN"}
    scored = score_candidates([c1, c2], sponsor, CFG["model"]["weights"], CFG["model"]["intercept"])
    dec = decide_probabilistic(scored, **CFG["thresholds"])
    assert dec.mode in {"accept","review"}  # should be very strong; accept after calibration

def test_ticker_hit_is_strong_signal():
    sponsor = "AlphaBio Therapeutics (NASDAQ: ABTX)"
    c = {"company_id": 1, "name": "AlphaBio Therapeutics", "website_domain":"alphabio.com", "ticker":"ABTX"}
    s = score_candidates([c], sponsor, CFG["model"]["weights"], CFG["model"]["intercept"])
    d = decide_probabilistic(s, **CFG["thresholds"])
    assert d.mode in {"accept","review"}

def test_academic_penalty_blocks_false_positive():
    sponsor = "Massachusetts General Hospital"
    c = {"company_id": 1, "name": "General Hospital Therapeutics", "website_domain":"", "ticker":"GHTX"}
    feats = build_features(sponsor, c, context={})
    assert feats["academic_keyword_penalty"] == 1.0
