"""
risk_flags.py
==============
Layer 3: Rule-based Anomaly Flags + Anomaly Score (0-1)

This module produces two things:

A) Boolean flags — transparent, auditable rules:
    is_revenue_drop     revenue_yoy < -10%
    is_profit_negative  net_income < 0
    is_debt_spike       debt_yoy > 30%
    is_cash_low         cash < 5% of total assets
    is_ratio_abnormal   current_ratio < 1 AND not retail sector

B) anomaly_score (0–1)
    Weighted average of normalised signals.
    0 = perfectly normal, 1 = extreme distress.

C) Final decision fields (Layer 7):
    final_risk_level     low / medium / high / critical
    recommended_action   approve / monitor / reduce_exposure / escalate
    summary_text         one-sentence conclusion

Why rule-based baseline matters (interview answer)
---------------------------------------------------
"Before any ML, I establish a rule-based baseline.  It does three things:
(1) gives auditors an explainable floor — every alert can be traced to a
    named rule;
(2) catches obvious cases without model uncertainty;
(3) gives a benchmark to compare ML against — if my ML model doesn't beat
    the rules, I shouldn't ship it."

Why anomaly_score separately from risk_score
--------------------------------------------
risk_score (financial_ratios.py) = forward-looking credit risk
anomaly_score (this file)        = backward-looking unusual behaviour
They are correlated but different: a company can have high credit risk
(lots of debt) but no anomalies (stable and predictable debt level).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Thresholds — centralised so they can be tuned / audited
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "revenue_drop_pct":    -0.10,   # -10% YoY
    "debt_spike_pct":       0.30,   # +30% YoY
    "cash_low_pct":         0.05,   # cash < 5% of total assets
    "current_ratio_min":    1.00,   # below 1 = short-term pressure
}

# Retail sector is exempt from current_ratio < 1 flag (structurally < 1 is normal)
RETAIL_INDUSTRIES = {"retail", "food_service"}

# Weights for anomaly_score components (must sum to 1.0)
ANOMALY_WEIGHTS = {
    "revenue_component":   0.30,
    "profit_component":    0.30,
    "debt_component":      0.20,
    "cash_component":      0.10,
    "ratio_component":     0.10,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_risk_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds rule-based flags, anomaly_score, and decision fields to df.

    Parameters
    ----------
    df : DataFrame
        Must have feature_engineering columns already added
        (revenue_yoy, profit_yoy, debt_yoy, current_ratio, etc.)

    Returns
    -------
    DataFrame with original columns + flag + score + decision columns.
    """
    out = df.copy()

    out = _boolean_flags(out)
    out = _anomaly_score(out)
    out = _decision_layer(out)

    return out


# ---------------------------------------------------------------------------
# A) Boolean flags
# ---------------------------------------------------------------------------

def _boolean_flags(df: pd.DataFrame) -> pd.DataFrame:

    # Revenue drop: worse than threshold
    df["is_revenue_drop"] = (
        df["revenue_yoy"].notna() &
        (df["revenue_yoy"] < THRESHOLDS["revenue_drop_pct"])
    )

    # Profit negative
    df["is_profit_negative"] = df["net_income"] < 0

    # Debt spike
    df["is_debt_spike"] = (
        df["debt_yoy"].notna() &
        (df["debt_yoy"] > THRESHOLDS["debt_spike_pct"])
    )

    # Cash low: cash < 5% of total assets
    df["is_cash_low"] = (
        df["cash_and_equivalents"].notna() &
        df["total_assets"].notna() &
        ((df["cash_and_equivalents"] / df["total_assets"]) < THRESHOLDS["cash_low_pct"])
    )

    # Ratio abnormal: current_ratio < 1 for non-retail companies
    is_retail = df["industry"].isin(RETAIL_INDUSTRIES)
    df["is_ratio_abnormal"] = (
        df["current_ratio"].notna() &
        (df["current_ratio"] < THRESHOLDS["current_ratio_min"]) &
        ~is_retail
    )

    # Flag count: total number of flags triggered this year
    flag_cols = [
        "is_revenue_drop", "is_profit_negative",
        "is_debt_spike", "is_cash_low", "is_ratio_abnormal"
    ]
    df["flag_count"] = df[flag_cols].sum(axis=1).astype(int)

    return df


# ---------------------------------------------------------------------------
# B) Anomaly score (0-1)
# ---------------------------------------------------------------------------

def _anomaly_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts each flag/signal into a 0-1 component, then weights them.

    Design choice: sigmoid-style clipping rather than min-max normalisation,
    because min-max would make the worst company always score 1.0 regardless
    of actual severity.  We use domain-anchored scales instead.

    Financial sector gets NaN — the rules don't apply to banking balance sheets.
    """

    def _clip01(series: pd.Series) -> pd.Series:
        return series.clip(0, 1)

    # Revenue: how far below threshold? (0 = normal, 1 = -50% drop)
    rev_component = _clip01(
        (THRESHOLDS["revenue_drop_pct"] - df["revenue_yoy"].fillna(0))
        / abs(THRESHOLDS["revenue_drop_pct"])
    ).where(df["revenue_yoy"].notna(), other=0.0)

    # Profit: negative income → 0.5 base; deeper loss → higher score
    profit_max_loss = 0.10   # 10% loss margin = score 1.0
    profit_component = _clip01(
        np.where(
            df["net_income"] < 0,
            0.5 + (-df["net_income"] / df["revenue"].replace(0, np.nan)) / profit_max_loss * 0.5,
            0.0
        )
    )

    # Debt spike: how far above threshold?
    debt_component = _clip01(
        (df["debt_yoy"].fillna(0) - THRESHOLDS["debt_spike_pct"])
        / THRESHOLDS["debt_spike_pct"]
    ).where(df["debt_yoy"].notna(), other=0.0)

    # Cash low: 0 if cash >= 10% assets; 1 if cash = 0
    cash_ratio = (df["cash_and_equivalents"] / df["total_assets"].replace(0, np.nan)).fillna(0)
    cash_component = _clip01(1 - cash_ratio / 0.10)

    # Ratio: current_ratio < 1 for non-retail
    is_retail = df["industry"].isin(RETAIL_INDUSTRIES)
    ratio_component = np.where(
        is_retail | df["current_ratio"].isna(),
        0.0,
        _clip01(1 - df["current_ratio"].fillna(1))
    )

    # Weighted sum
    score = (
        ANOMALY_WEIGHTS["revenue_component"] * rev_component +
        ANOMALY_WEIGHTS["profit_component"]  * profit_component +
        ANOMALY_WEIGHTS["debt_component"]    * debt_component +
        ANOMALY_WEIGHTS["cash_component"]    * cash_component +
        ANOMALY_WEIGHTS["ratio_component"]   * pd.Series(ratio_component, index=df.index)
    )

    # Financial sector: NaN
    df["anomaly_score"] = np.where(df["is_financial_sector"], np.nan, score.round(3))

    return df


# ---------------------------------------------------------------------------
# C) Decision / Output layer (Layer 7)
# ---------------------------------------------------------------------------

# Combined risk score blending rule-based anomaly + Altman-based risk_score
def _decision_layer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produce final_risk_level, recommended_action, summary_text.

    Blending logic:
        combined = 0.6 × risk_score (from financial_ratios)
                 + 0.4 × anomaly_score × 100

    This intentionally gives more weight to the structural Altman-based risk
    because anomaly_score is more volatile year-to-year.

    For financial sector: use internal_rating as proxy (scale 1-10 → 0-100).
    """

    # Non-financial: blend risk_score + anomaly_score
    combined_non_fin = (
        0.6 * df["risk_score"].fillna(50) +
        0.4 * df["anomaly_score"].fillna(0) * 100
    )

    # 修正：internal_rating 不存在時用 neutral 預設值
    if "internal_rating" in df.columns:
        combined_fin = (df["internal_rating"] - 1) / 9 * 100
    else:
        combined_fin = pd.Series(50.0, index=df.index)

    df["combined_score"] = np.where(
        df["is_financial_sector"],
        combined_fin.round(1),
        combined_non_fin.round(1)
    )

    # final_risk_level
    conditions = [
        df["combined_score"] >= 70,
        df["combined_score"] >= 45,
        df["combined_score"] >= 20,
    ]
    choices = ["critical", "high", "medium"]
    df["final_risk_level"] = np.select(conditions, choices, default="low")

    # recommended_action
    action_map = {
        "critical": "escalate",
        "high":     "reduce_exposure",
        "medium":   "monitor",
        "low":      "approve",
    }
    df["recommended_action"] = df["final_risk_level"].map(action_map)

    # summary_text — deterministic template (LLM will enrich this in Day 5)
    def _summary(row) -> str:
        company = row["company_name"]
        level   = row["final_risk_level"].upper()
        action  = row["recommended_action"].replace("_", " ")
        flags   = int(row.get("flag_count", 0))
        score   = row["combined_score"]
        return (
            f"{company} 綜合風險評級 {level}（評分 {score:.0f}），"
            f"觸發 {flags} 項異常規則，建議行動：{action}。"
        )

    df["summary_text"] = df.apply(_summary, axis=1)

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from feature_engineering import engineer_features
    from financial_ratios import compute_ratios, compute_risk_score

    fin = pd.read_csv(
        Path(__file__).resolve().parent.parent / "data" / "sample_financials_long.csv"
    )
    fin["is_financial_sector"] = fin["is_financial_sector"].astype(bool)

    # Build feature set
    fe  = engineer_features(fin)
    rat = compute_ratios(fin)
    rat = compute_risk_score(rat)

    # Merge features + ratios
    merged = fe.merge(
        rat[["ticker", "year", "current_ratio", "risk_score",
             "altman_z_prime", "debt_ratio", "risk_band"]],
        on=["ticker", "year"], how="left"
    )

    out = compute_risk_flags(merged)
    latest = out[out["year"] == 2024][[
        "company_name", "flag_count", "anomaly_score",
        "combined_score", "final_risk_level", "recommended_action"
    ]].sort_values("combined_score", ascending=False)

    print("=== 2024 Risk Flags + Decision ===")
    print(latest.to_string(index=False))
    print()
    print("=== Summary Texts ===")
    for _, row in out[out["year"] == 2024].iterrows():
        print(" •", row["summary_text"])
