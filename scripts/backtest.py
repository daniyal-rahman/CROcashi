#!/usr/bin/env python3
"""
Run backtests on the system.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config


def load_config(config_path: str) -> Dict[str, Any]:
    """Load backtest configuration."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_outcomes_config(config_path: str) -> Dict[str, Any]:
    """Load outcomes configuration."""
    outcomes_path = Path(config_path).parent / "backtest_outcomes.yaml"
    if outcomes_path.exists():
        with open(outcomes_path, 'r') as f:
            return yaml.safe_load(f)
    else:
        # Return default config
        return {
            "endpoints": {
                "continuous": {
                    "sigma_default": 0.5,
                    "mcid_lookup": {
                        "ADAS-Cog11": 1.5,
                        "MMSE": 1.0
                    }
                },
                "binary": {
                    "sigma_default": 0.3,
                    "mcid_abs_default": 0.05
                },
                "tte": {
                    "sigma_default": 0.2
                }
            },
            "penalties": {
                "subgroup_only": 0.10,
                "non_itt_or_pp_only": 0.10,
                "underpowered_or_no_primary": 0.05,
                "endpoint_changed_post_reg": 0.10,
                "non_significant": 0.15,
                "missing_primary_result": 0.20
            },
            "weights": {
                "effect": 0.7,
                "pvalue": 0.3
            },
            "grades": {
                "SS": [0.0, 0.2],
                "LS": [0.2, 0.4],
                "A": [0.4, 0.6],
                "LF": [0.6, 0.8],
                "FF": [0.8, 1.0]
            }
        }


def load_json_files(glob_pattern: str, base_dir: str) -> List[Dict[str, Any]]:
    """Load JSON files matching pattern."""
    import glob
    
    files = glob.glob(str(Path(base_dir) / glob_pattern))
    data = []
    
    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                file_data = json.load(f)
                # Handle both single objects and lists
                if isinstance(file_data, list):
                    data.extend(file_data)
                else:
                    data.append(file_data)
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")
    
    return data


def index_trials_by_doc_id(trial_files: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index trials by doc_id."""
    by_id = {}
    for trial in trial_files:
        doc_id = trial.get("doc_id") or trial.get("study_card", {}).get("study_id")
        if doc_id:
            by_id[doc_id] = trial
    return by_id


def compute_outcomes_for_trials(
    trials: List[Dict[str, Any]], 
    outcomes_cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute outcome severity for all trials."""
    outcomes = {}
    
    for trial in trials:
        doc_id = trial.get("doc_id") or trial.get("study_card", {}).get("study_id")
        if doc_id:
            try:
                outcome = compute_outcome_severity(trial, outcomes_cfg)
                outcomes[doc_id] = {
                    "severity": outcome.severity,
                    "grade": outcome.grade,
                    "confidence": outcome.confidence,
                    "components": outcome.components
                }
            except Exception as e:
                print(f"Warning: Could not compute outcome for {doc_id}: {e}")
                outcomes[doc_id] = {
                    "severity": 0.5,
                    "grade": "A",
                    "confidence": 0.0,
                    "error": str(e)
                }
    
    return outcomes


def run_stage_ctgov(
    config: Dict[str, Any], 
    logger: Any,
    **kwargs
) -> Dict[str, Any]:
    """Run CTGov discovery stage evaluation."""
    logger.info("Running CTGov discovery and public company wiring evaluation")
    
    # Load trial files
    trial_files = load_json_files(config["trial_glob"], config["fixtures_dir"])
    
    # Enhanced CTGov analysis
    discovery_metrics = {
        "total_trials_discovered": len(trial_files),
        "trials_with_nct_id": 0,
        "trials_with_sponsor_info": 0,
        "trials_with_phase_info": 0,
        "trials_with_indication": 0,
        "trials_with_completion_date": 0,
        "trials_with_public_us_sponsor": 0,
        "trials_with_public_us_filter": 0
    }
    
    # Detailed audit
    audit_details = {
        "missing_nct_ids": [],
        "missing_sponsor_info": [],
        "missing_phase_info": [],
        "missing_indication": [],
        "missing_completion_date": [],
        "non_public_us_sponsors": [],
        "public_us_sponsors": [],
        "trial_versions": [],
        "endpoint_changes": []
    }
    
    for i, trial in enumerate(trial_files):
        # Check for NCT ID (doc_id)
        if trial.get("doc_id"):
            discovery_metrics["trials_with_nct_id"] += 1
        else:
            audit_details["missing_nct_ids"].append({
                "file_index": i,
                "trial_data": trial
            })
        
        # Check for sponsor information
        sponsor_info = _extract_sponsor_info(trial)
        if sponsor_info:
            discovery_metrics["trials_with_sponsor_info"] += 1
            if sponsor_info.get("is_public_us"):
                discovery_metrics["trials_with_public_us_sponsor"] += 1
                audit_details["public_us_sponsors"].append({
                    "nct_id": trial.get("doc_id"),
                    "sponsor": sponsor_info.get("sponsor_name"),
                    "exchange": sponsor_info.get("exchange"),
                    "cik": sponsor_info.get("cik")
                })
            else:
                audit_details["non_public_us_sponsors"].append({
                    "nct_id": trial.get("doc_id"),
                    "sponsor": sponsor_info.get("sponsor_name"),
                    "reason": sponsor_info.get("reason")
                })
        else:
            audit_details["missing_sponsor_info"].append({
                "file_index": i,
                "nct_id": trial.get("doc_id")
            })
        
        # Check for phase information
        phase_info = _extract_phase_info(trial)
        if phase_info:
            discovery_metrics["trials_with_phase_info"] += 1
        else:
            audit_details["missing_phase_info"].append({
                "file_index": i,
                "nct_id": trial.get("doc_id")
            })
        
        # Check for indication
        indication = _extract_indication(trial)
        if indication:
            discovery_metrics["trials_with_indication"] += 1
        else:
            audit_details["missing_indication"].append({
                "file_index": i,
                "nct_id": trial.get("doc_id")
            })
        
        # Check for completion date
        completion_date = _extract_completion_date(trial)
        if completion_date:
            discovery_metrics["trials_with_completion_date"] += 1
        else:
            audit_details["missing_completion_date"].append({
                "file_index": i,
                "nct_id": trial.get("doc_id")
            })
        
        # Check for trial versions and endpoint changes
        trial_versions = _extract_trial_versions(trial)
        if trial_versions:
            audit_details["trial_versions"].append({
                "nct_id": trial.get("doc_id"),
                "versions": trial_versions
            })
        
        endpoint_changes = _extract_endpoint_changes(trial)
        if endpoint_changes:
            audit_details["endpoint_changes"].append({
                "nct_id": trial.get("doc_id"),
                "changes": endpoint_changes
            })
    
    # Calculate coverage percentages
    total_trials = discovery_metrics["total_trials_discovered"]
    if total_trials > 0:
        discovery_metrics["nct_id_coverage"] = discovery_metrics["trials_with_nct_id"] / total_trials
        discovery_metrics["sponsor_info_coverage"] = discovery_metrics["trials_with_sponsor_info"] / total_trials
        discovery_metrics["phase_info_coverage"] = discovery_metrics["trials_with_phase_info"] / total_trials
        discovery_metrics["indication_coverage"] = discovery_metrics["trials_with_indication"] / total_trials
        discovery_metrics["completion_date_coverage"] = discovery_metrics["trials_with_completion_date"] / total_trials
        discovery_metrics["public_us_sponsor_rate"] = discovery_metrics["trials_with_public_us_sponsor"] / total_trials
    
    # Public US filter analysis
    if discovery_metrics["trials_with_sponsor_info"] > 0:
        discovery_metrics["public_us_filter_rate"] = discovery_metrics["trials_with_public_us_sponsor"] / discovery_metrics["trials_with_sponsor_info"]
    
    metrics = {
        **discovery_metrics,
        "stage": "ctgov"
    }
    
    audit = {
        **audit_details,
        "summary": {
            "total_trials_analyzed": total_trials,
            "trials_passing_public_us_filter": discovery_metrics["trials_with_public_us_sponsor"],
            "trials_failing_public_us_filter": discovery_metrics["trials_with_sponsor_info"] - discovery_metrics["trials_with_public_us_sponsor"]
        }
    }
    
    return {
        "metrics": metrics,
        "audit": audit,
        "trials": trial_files
    }


def run_stage_lit(
    config: Dict[str, Any], 
    logger: Any,
    trials: List[Dict[str, Any]],
    **kwargs
) -> Dict[str, Any]:
    """Run literature review stage evaluation."""
    logger.info("Running literature review stage evaluation")
    
    required_fields = config["stages"]["lit"]["required_fields"]
    
    # Check field coverage
    field_coverage = {}
    missing_fields = []
    
    for trial in trials:
        doc_id = trial.get("doc_id") or trial.get("study_card", {}).get("study_id")
        if not doc_id:
            continue
            
        trial_missing = []
        for field in required_fields:
            if not _has_field(trial, field):
                trial_missing.append(field)
        
        if trial_missing:
            missing_fields.append({
                "doc_id": doc_id,
                "missing_fields": trial_missing
            })
        
        for field in required_fields:
            if field not in field_coverage:
                field_coverage[field] = {"present": 0, "total": 0}
            field_coverage[field]["total"] += 1
            if _has_field(trial, field):
                field_coverage[field]["present"] += 1
    
    # Compute coverage percentages
    for field, counts in field_coverage.items():
        if counts["total"] > 0:
            counts["coverage"] = counts["present"] / counts["total"]
    
    metrics = {
        "total_trials": len(trials),
        "field_coverage": field_coverage,
        "trials_with_all_required": len([t for t in trials if _has_all_fields(t, required_fields)]),
        "stage": "lit"
    }
    
    audit = {
        "missing_fields": missing_fields
    }
    
    return {
        "metrics": metrics,
        "audit": audit
    }


def run_stage_cards(
    config: Dict[str, Any], 
    logger: Any,
    trials: List[Dict[str, Any]],
    mode: str = "scraped",
    **kwargs
) -> Dict[str, Any]:
    """Run cards quality evaluation."""
    logger.info(f"Running cards stage evaluation (mode: {mode})")
    
    critical_fields = config["stages"]["cards"]["critical_fields"]
    
    # For now, just check field presence
    # In oracle mode, this would compare against curated cards
    field_accuracy = {}
    field_diffs = []
    
    for trial in trials:
        doc_id = trial.get("doc_id") or trial.get("study_card", {}).get("study_id")
        if not doc_id:
            continue
        
        for field in critical_fields:
            if field not in field_accuracy:
                field_accuracy[field] = {"present": 0, "total": 0}
            
            field_accuracy[field]["total"] += 1
            if _has_field(trial, field):
                field_accuracy[field]["present"] += 1
    
    # Compute accuracy percentages
    for field, counts in field_accuracy.items():
        if counts["total"] > 0:
            counts["accuracy"] = counts["present"] / counts["total"]
    
    metrics = {
        "total_trials": len(trials),
        "field_accuracy": field_accuracy,
        "mode": mode,
        "stage": "cards"
    }
    
    audit = {
        "field_diffs": field_diffs
    }
    
    return {
        "metrics": metrics,
        "audit": audit
    }


def run_stage_pred(
    config: Dict[str, Any], 
    logger: Any,
    trials: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    outcomes: Dict[str, Any],
    mode: str = "scraped",
    **kwargs
) -> Dict[str, Any]:
    """Run prediction stage evaluation."""
    logger.info(f"Running prediction stage evaluation (mode: {mode})")
    
    thresholds = config["thresholds"]
    k_values = config["k_values"]
    
    # Create trial rows with P_fail and outcomes
    rows = []
    for signal in signals:
        doc_id = signal.get("doc_id") or signal.get("study_card", {}).get("study_id")
        if not doc_id:
            continue
        
        # Extract P_fail
        p_fail = (
            signal.get("p_fail") or 
            signal.get("score", {}).get("p_fail") or
            signal.get("scoring", {}).get("score", {}).get("p_fail")
        )
        if isinstance(p_fail, str):
            try:
                p_fail = float(p_fail)
            except:
                p_fail = None
        
        # Get outcome
        outcome = outcomes.get(doc_id, {})
        severity = outcome.get("severity", 0.5)
        grade = outcome.get("grade", "A")
        
        rows.append({
            "doc_id": doc_id,
            "p_fail": p_fail,
            "severity": severity,
            "grade": grade
        })
    
    # Sort by P_fail (descending)
    ranked = sorted([r for r in rows if r["p_fail"] is not None], 
                   key=lambda x: x["p_fail"], reverse=True)
    
    # Compute precision@K
    precision_at_k = {}
    for k in k_values:
        if k > len(ranked):
            precision_at_k[str(k)] = {"precision": None, "n": 0}
            continue
        
        topk = ranked[:k]
        # Count FF and LF as "positive" (failures)
        tp = sum(1 for r in topk if r["grade"] in ["FF", "LF"])
        precision = tp / len(topk) if topk else None
        
        precision_at_k[str(k)] = {
            "precision": round(precision, 4) if precision is not None else None,
            "n": len(topk)
        }
    
    # Compute threshold metrics
    threshold_metrics = {}
    for threshold in thresholds:
        selected = [r for r in rows if r["p_fail"] is not None and r["p_fail"] >= threshold]
        
        if not selected:
            threshold_metrics[str(threshold)] = {
                "selected": 0,
                "tp": 0,
                "precision": None,
                "hit_rate_recall": None,
                "coverage_all": 0.0
            }
            continue
        
        tp = sum(1 for r in selected if r["grade"] in ["FF", "LF"])
        total_ff_lf = sum(1 for r in rows if r["grade"] in ["FF", "LF"])
        
        precision = tp / len(selected) if selected else None
        recall = tp / total_ff_lf if total_ff_lf > 0 else None
        coverage = len(selected) / len(rows) if rows else None
        
        threshold_metrics[str(threshold)] = {
            "selected": len(selected),
            "tp": tp,
            "precision": round(precision, 4) if precision is not None else None,
            "hit_rate_recall": round(recall, 4) if recall is not None else None,
            "coverage_all": round(coverage, 4) if coverage is not None else None
        }
    
    # Compute ranking correlation
    if len(ranked) > 1:
        import scipy.stats
        p_fails = [r["p_fail"] for r in ranked]
        severities = [r["severity"] for r in ranked]
        spearman_corr = scipy.stats.spearmanr(p_fails, severities)[0]
    else:
        spearman_corr = None
    
    metrics = {
        "total_trials": len(rows),
        "trials_with_p_fail": len([r for r in rows if r["p_fail"] is not None]),
        "precision_at_k": precision_at_k,
        "thresholds": threshold_metrics,
        "spearman_correlation": round(spearman_corr, 4) if spearman_corr is not None else None,
        "mode": mode,
        "stage": "pred"
    }
    
    # Audit: false positives/negatives at highest threshold
    audit_threshold = max(thresholds)
    selected_ids = set(r["doc_id"] for r in rows 
                      if r["p_fail"] is not None and r["p_fail"] >= audit_threshold)
    
    false_positives = [r for r in rows 
                       if r["doc_id"] in selected_ids and r["grade"] in ["SS", "LS"]]
    false_negatives = [r for r in rows 
                       if r["doc_id"] not in selected_ids and r["grade"] in ["FF", "LF"]]
    
    audit = {
        "false_positives_at_thr": false_positives,
        "false_negatives_at_thr": false_negatives,
        "audit_threshold": audit_threshold
    }
    
    return {
        "metrics": metrics,
        "audit": audit
    }


def run_stage_e2e(
    config: Dict[str, Any], 
    logger: Any,
    pred_results: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """Run end-to-end evaluation."""
    logger.info("Running end-to-end evaluation")
    
    rec_threshold = config["rec_threshold"]
    
    # Use prediction results to compute final recommendation metrics
    threshold_metrics = pred_results["metrics"]["thresholds"]
    rec_metrics = threshold_metrics.get(str(rec_threshold), {})
    
    metrics = {
        "recommendation_threshold": rec_threshold,
        "precision_rec": rec_metrics.get("precision"),
        "coverage_rec": rec_metrics.get("coverage_all"),
        "selected_count": rec_metrics.get("selected", 0),
        "stage": "e2e"
    }
    
    audit = {
        "recommended_trials": pred_results["audit"]["false_positives_at_thr"],
        "dropped_failures": pred_results["audit"]["false_negatives_at_thr"]
    }
    
    return {
        "metrics": metrics,
        "audit": audit
    }


def _has_field(trial: Dict[str, Any], field: str) -> bool:
    """Check if trial has a field."""
    # Check multiple possible locations
    if field in trial:
        return True
    
    if "study_card" in trial and field in trial["study_card"]:
        return True
    
    if "method_card" in trial and field in trial["method_card"]:
        return True
    
    if "primary_result" in trial and field in trial["primary_result"]:
        return True
    
    return False


def _has_all_fields(trial: Dict[str, Any], fields: List[str]) -> bool:
    """Check if trial has all required fields."""
    return all(_has_field(trial, field) for field in fields)


def _extract_sponsor_info(trial: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract sponsor information from trial data."""
    # Check multiple possible locations for sponsor info
    sponsor_name = (
        trial.get("sponsor") or
        trial.get("method_card", {}).get("sponsor") or
        trial.get("study_card", {}).get("sponsor")
    )
    
    if not sponsor_name:
        return None
    
    # For now, use a simple heuristic to identify public US companies
    # In production, this would query a company database
    public_us_indicators = [
        "inc", "corp", "corporation", "company", "ltd", "limited",
        "pharmaceuticals", "pharma", "biotech", "therapeutics"
    ]
    
    sponsor_lower = sponsor_name.lower()
    is_public_us = any(indicator in sponsor_lower for indicator in public_us_indicators)
    
    return {
        "sponsor_name": sponsor_name,
        "is_public_us": is_public_us,
        "exchange": "NASDAQ" if is_public_us else None,  # Placeholder
        "cik": None,  # Would be looked up in production
        "reason": "Not identified as public US company" if not is_public_us else None
    }


def _extract_phase_info(trial: Dict[str, Any]) -> Optional[str]:
    """Extract phase information from trial data."""
    return (
        trial.get("phase") or
        trial.get("method_card", {}).get("study_phase") or
        trial.get("study_card", {}).get("phase")
    )


def _extract_indication(trial: Dict[str, Any]) -> Optional[str]:
    """Extract indication information from trial data."""
    return (
        trial.get("indication") or
        trial.get("method_card", {}).get("indication") or
        trial.get("study_card", {}).get("indication")
    )


def _extract_completion_date(trial: Dict[str, Any]) -> Optional[str]:
    """Extract completion date from trial data."""
    return (
        trial.get("completion_date") or
        trial.get("method_card", {}).get("completion_date") or
        trial.get("study_card", {}).get("completion_date") or
        trial.get("est_primary_completion_date")
    )


def _extract_trial_versions(trial: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Extract trial version information."""
    versions = []
    
    # Check for version_id field
    if trial.get("version_id"):
        versions.append({
            "version_id": trial["version_id"],
            "captured_at": trial.get("captured_at"),
            "is_late_change": trial.get("is_late_change", False)
        })
    
    # Check for multiple versions in the data
    if isinstance(trial.get("versions"), list):
        versions.extend(trial["versions"])
    
    return versions if versions else None


def _extract_endpoint_changes(trial: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Extract endpoint change information."""
    changes = []
    
    # Check for endpoint changes in claims
    claims = trial.get("claims", [])
    for claim in claims:
        if "endpoint" in claim.get("proposition", "").lower() and "change" in claim.get("proposition", "").lower():
            changes.append({
                "claim": claim.get("proposition"),
                "type": claim.get("type"),
                "evidence": claim.get("evidence_ids", [])
            })
    
    # Check for endpoint changes in method card
    method_card = trial.get("method_card", {})
    if method_card.get("endpoint_changes"):
        changes.extend(method_card["endpoint_changes"])
    
    return changes if changes else None


def main():
    """Main backtest function."""
    parser = argparse.ArgumentParser(description="NCFD Pipeline Backtest")
    parser.add_argument("--config", default="config/backtest.yaml", help="Config file")
    parser.add_argument("--stage", default="all", 
                       choices=["all", "ctgov", "lit", "cards", "pred", "e2e"],
                       help="Stage to run")
    parser.add_argument("--mode", default="scraped",
                       choices=["scraped", "oracle", "both"],
                       help="Evaluation mode")
    parser.add_argument("--outdir", default="backtest", help="Output directory")
    
    args = parser.parse_args()
    
    # Load configurations
    config = load_config(args.config)
    outcomes_cfg = load_outcomes_config(args.config)
    
    # Setup logging
    log_config = config.get("logging", {})
    logger = setup_logging(
        level=log_config.get("level", "INFO"),
        format_str=log_config.get("format"),
        log_file=log_config.get("file"),
        console=True
    )
    
    # Create output directory
    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)
    
    logger.info(f"Starting backtest - stage: {args.stage}, mode: {args.mode}")
    
    # Load data
    trials = load_json_files(config["trial_glob"], config["fixtures_dir"])
    signals = load_json_files(config["signals_glob"], config["fixtures_dir"])
    
    logger.info(f"Loaded {len(trials)} trials and {len(signals)} signals")
    
    # Compute outcomes
    outcomes = compute_outcomes_for_trials(trials, outcomes_cfg)
    logger.info(f"Computed outcomes for {len(outcomes)} trials")
    
    # Run stages
    results = {}
    
    if args.stage in ["all", "ctgov"]:
        results["ctgov"] = run_stage_ctgov(config, logger, trials=trials)
    
    if args.stage in ["all", "lit"]:
        results["lit"] = run_stage_lit(config, logger, trials=trials)
    
    if args.stage in ["all", "cards"]:
        results["cards"] = run_stage_cards(config, logger, trials=trials, mode=args.mode)
    
    if args.stage in ["all", "pred"]:
        results["pred"] = run_stage_pred(config, logger, trials=trials, 
                                       signals=signals, outcomes=outcomes, mode=args.mode)
    
    if args.stage in ["all", "e2e"]:
        if "pred" in results:
            results["e2e"] = run_stage_e2e(config, logger, pred_results=results["pred"])
    
    # Write results
    metrics = {}
    for stage, result in results.items():
        metrics[stage] = result["metrics"]
    
    # Add summary metrics
    metrics["summary"] = {
        "total_trials": len(trials),
        "total_signals": len(signals),
        "outcomes_computed": len(outcomes),
        "stages_run": list(results.keys())
    }
    
    # Write metrics
    with open(outdir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    
    # Write per-stage audits
    for stage, result in results.items():
        audit_file = outdir / f"audit_{stage}.json"
        with open(audit_file, "w") as f:
            json.dump(result["audit"], f, indent=2)
    
    # Write outcomes
    with open(outdir / "outcomes.json", "w") as f:
        json.dump(outcomes, f, indent=2)
    
    logger.info(f"Backtest completed. Results written to {outdir}")
    print(f"✅ Backtest completed. Results written to {outdir}")
    print(f"📊 Metrics: {outdir}/metrics.json")
    print(f"🔍 Audits: {outdir}/audit_*.json")
    print(f"📈 Outcomes: {outdir}/outcomes.json")


if __name__ == "__main__":
    main()
