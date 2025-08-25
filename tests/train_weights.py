# scripts/train_weights.py
import json, yaml, numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import precision_recall_curve
from sklearn.model_selection import GroupKFold

TRAIN_CSV = Path("training.csv")
OUT_YAML  = Path("config/resolver.yaml")

def load():
    df = pd.read_csv(TRAIN_CSV)
    feats = df["features_jsonb"].apply(json.loads)

    # Flat feature space
    keys = sorted({k for d in feats for k in d.keys()})
    X = np.array([[d.get(k, 0.0) for k in keys] for d in feats], dtype=float)
    y = df["label"].astype(int).to_numpy()
    groups = df["sponsor_text_norm"].fillna("").astype(str).to_numpy()
    return df, X, y, groups, keys

def fit_and_calibrate(X, y, groups):
    n_pos = int(y.sum())
    n_neg = int((1 - y).sum())
    method = "isotonic" if n_pos >= 100 and n_neg >= 100 else "sigmoid"

    base = LogisticRegression(max_iter=500)
    # Use grouped CV to reduce leakage across the same sponsor text
    # If too few groups, CalibratedClassifierCV will internally refit.
    cv = GroupKFold(n_splits=min(5, max(2, len(np.unique(groups)))))
    clf = CalibratedClassifierCV(base, method=method, cv=cv)
    clf.fit(X, y, groups=groups)
    return clf, method

def choose_threshold_for_precision(y_true, p_hat, target_precision=0.95):
    prec, rec, thr = precision_recall_curve(y_true, p_hat)
    tau = 0.90
    for P, T in zip(prec, np.r_[thr, 1.0]):
        if P >= target_precision:
            tau = float(T)
            break
    # A conservative floor
    return float(max(0.5, tau))

def main():
    df, X, y, groups, keys = load()
    clf, method = fit_and_calibrate(X, y, groups)
    base = clf.base_estimator
    intercept = float(base.intercept_[0])
    weights = {k: float(w) for k, w in zip(keys, base.coef_[0])}

    p_hat = clf.predict_proba(X)[:, 1]
    tau_accept = choose_threshold_for_precision(y, p_hat, target_precision=0.95)

    cfg = {
        "model": {
            "intercept": intercept,
            "weights": weights
        },
        "thresholds": {
            "tau_accept": tau_accept,
            "review_low": max(0.60, tau_accept - 0.20),
            "min_top2_margin": 0.05,
            "require_unique_winner": True
        },
        "calibration": {"method": method}
    }
    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    with OUT_YAML.open("w") as f:
        yaml.safe_dump(cfg, f, sort_keys=True)

    # quick report
    est_prec = ( (p_hat >= tau_accept).sum() and
                 ( ( (y==1) & (p_hat >= tau_accept) ).sum() / (p_hat >= tau_accept).sum() ) )
    coverage = float((p_hat >= tau_accept).mean())
    print(f"Wrote {OUT_YAML}")
    print(f"Calib: {method} | est precision@accept≈{est_prec:.3f} | coverage≈{coverage:.3f}")

if __name__ == "__main__":
    main()
