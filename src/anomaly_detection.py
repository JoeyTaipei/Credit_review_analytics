"""
anomaly_detection.py
=====================
Detects unusual year-over-year movements in three signals that
historically precede credit deterioration:
  1. Revenue YoY growth
  2. Total liabilities YoY growth
  3. Operating cash flow change

Defending the model choice:
- We use a per-company Z-score against that company's OWN 5-year history.
  Why?
    * Sample is 7 firms × 5 years = 35 firm-years total.  Cross-sectional
      ML (Isolation Forest, autoencoders) needs hundreds of samples to
      avoid overfitting.
    * Z-score is fully interpretable: "this year's revenue growth was
      2.5σ below this firm's normal rolling mean."  A credit officer
      can read that and challenge it.
    * The comparable in industry is exactly this: TEJ's "warning signal"
      module also uses simple statistical thresholds, not ML.
- We also expose an Isolation Forest comparison to show we considered it,
  but flag in the docstring why we didn't pick it for the primary path.
- Threshold |z| ≥ 2.0 — chosen because:
    * 2σ ≈ 95th percentile under normality
    * For 5-year window, expecting <1 false positive per series per firm
    * Bank credit officers internalize "two sigma" easily; less so
      "isolation score 0.62"

Output:
    DataFrame with columns:
      ticker, year, signal, value, z_score, direction, is_anomaly
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

# Signals we monitor (column name in financials → human-readable label)
SIGNALS = {
    "revenue_yoy":          "營收年增率",
    "liabilities_yoy":      "負債年增率",
    "ocf_change":           "營運現金流變動",
}

ANOMALY_THRESHOLD = 2.0   # absolute Z-score


# ---------------------------------------------------------------------------
# Build the signal series from raw financials
# ---------------------------------------------------------------------------
def build_signals(financials: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the three monitored signals per (ticker, year).

    YoY growth is undefined for the first year per company → NaN, dropped.
    """
    df = financials.sort_values(["ticker", "year"]).copy()

    df["revenue_yoy"] = df.groupby("ticker")["revenue"].pct_change()
    df["liabilities_yoy"] = df.groupby("ticker")["total_liabilities"].pct_change()
    df["ocf_change"] = df.groupby("ticker")["operating_cash_flow"].pct_change()

    return df[
        ["ticker", "company_name", "industry_zh", "broad_industry_zh",
         "year", "is_financial_sector",
         "revenue_yoy", "liabilities_yoy", "ocf_change"]
    ]


# ---------------------------------------------------------------------------
# Per-company Z-score detection (leave-one-out)
# ---------------------------------------------------------------------------
def detect_anomalies_zscore(
    signals: pd.DataFrame,
    threshold: float = ANOMALY_THRESHOLD,
) -> pd.DataFrame:
    """
    For each (ticker, signal, year), compute a leave-one-out Z-score:
        z_i = (x_i - mean(x_{j ≠ i})) / std(x_{j ≠ i})

    Why leave-one-out (LOO)?
    - With only 4 YoY observations per firm, an outlier observation
      inflates its own std, mathematically capping |z| at √((n-1)/n) ≈ 0.87
      — i.e. NOTHING ever crosses 2σ.  Unusable.
    - LOO removes the focal year before computing the reference distribution,
      which is also closer to how a credit officer thinks: "ignoring this
      year as the question, was last year's number unusual vs. the prior years?"
    - Trade-off: with n=3 reference points, std estimate is noisy.  We
      deliberately set threshold = 2.0 (not 3.0) to keep flagging useful
      while accepting some false positives.  Officers triage manually anyway.

    Returns long-format DataFrame: one row per (ticker, year, signal).
    """
    long = signals.melt(
        id_vars=["ticker", "company_name", "industry_zh", "broad_industry_zh",
                 "year", "is_financial_sector"],
        value_vars=list(SIGNALS.keys()),
        var_name="signal",
        value_name="value",
    ).dropna(subset=["value"])

    # Leave-one-out mean/std per (ticker, signal)
    # 這段程式碼是計算 leave-one-out（略去本身年度值）的 Z-score：
    # 
    # 在每家公司的每一個監控信號（如營收成長率）下，對其每一年觀測值 x_i：
    #    1. 先把這個值「移除」，以其餘年度作為參考母體，計算均值與標準差
    #    2. 用公式 z_i = (x_i - mean_{j≠i}) / std_{j≠i} 算出 Z 分數
    # 
    # 為什麼要做 leave-one-out？
    # - 因為小樣本下（例：僅 4~5 年），有極端值時，若把自己也算進母體，
    #   會低估異常，讓標準差被拉大，使任何一年的 z-score 都偏小，幾乎不可能被標註為異常
    # - leave-one-out 從統計上避免這個問題，也更符合覆審官「先看全部，檢查本年是否異常」的判斷方式
    # 
    # 具體來說，_loo_z 會跑在 groupby() 之後，每組（公司、信號）以 pd.Series 算每年 LOO z-score。
    def _loo_z(group: pd.Series) -> pd.Series:
        n = len(group)
        if n < 3:
            return pd.Series(np.nan, index=group.index)
        total_sum = group.sum()
        total_sq_sum = (group ** 2).sum()
        loo_mean = (total_sum - group) / (n - 1)
        loo_var = ((total_sq_sum - group ** 2) / (n - 1)) - loo_mean ** 2
        loo_var = loo_var.clip(lower=1e-10)
        loo_std = np.sqrt(loo_var)
        return (group - loo_mean) / loo_std

    long["z_score"] = (
        long.groupby(["ticker", "signal"])["value"]
        .transform(_loo_z)
    )

    # Mark anomalies and direction
    long["is_anomaly"] = long["z_score"].abs() >= threshold
    long["direction"] = np.where(long["z_score"] > 0, "上偏", "下偏")
    long["signal_zh"] = long["signal"].map(SIGNALS)

    # Sort: most extreme first, helps the dashboard prioritize
    long["abs_z"] = long["z_score"].abs()
    long = long.sort_values(["abs_z"], ascending=False).drop(columns="abs_z")

    return long.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Optional comparison: Isolation Forest (kept for defendability)
# ---------------------------------------------------------------------------
def detect_anomalies_isolation_forest(signals: pd.DataFrame, contamination: float = 0.1):
    """
    Cross-sectional Isolation Forest, trained on all firm-years × 3 signals.

    Run this ONLY to demonstrate the comparison; do not use it as the
    primary detector for this demo (sample size insufficient).

    Reasons we wouldn't ship this:
      - Black-box score (no decomposition by signal)
      - 35 samples is below the recommended n≥256 default trees per sample
      - Hyperparameter contamination is just a guess for our use case
    """
    from sklearn.ensemble import IsolationForest   # lazy import

    X = signals[list(SIGNALS.keys())].dropna()
    iso = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=200,
    )
    pred = iso.fit_predict(X)               # -1 = anomaly, +1 = normal
    score = iso.score_samples(X)            # higher = more normal

    out = signals.loc[X.index].copy()
    out["iso_anomaly"] = pred == -1
    out["iso_score"] = score
    return out


# ---------------------------------------------------------------------------
# Pretty summary for the dashboard / LLM
# ---------------------------------------------------------------------------
def anomaly_summary(anomalies: pd.DataFrame, latest_only: bool = True) -> pd.DataFrame:
    """
    Filter to anomalies only (optionally latest year), reformatted for
    the dashboard's "current alerts" page.
    """
    df = anomalies[anomalies["is_anomaly"]].copy()
    if latest_only:
        df = df[df["year"] == df["year"].max()]
    return df[
        ["ticker", "company_name", "industry_zh", "broad_industry_zh", "year",
         "signal_zh", "value", "z_score", "direction"]
    ].rename(columns={"signal_zh": "signal", "value": "yoy_value"})


# ---------------------------------------------------------------------------
# CLI for quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path
    fin = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "sample_financials_long.csv")
    fin["is_financial_sector"] = fin["is_financial_sector"].astype(bool)

    signals = build_signals(fin)
    anomalies = detect_anomalies_zscore(signals)
    summary = anomaly_summary(anomalies, latest_only=False)

    print(f"Detected {len(summary)} anomalies across all years:")
    print(summary.to_string(index=False))
