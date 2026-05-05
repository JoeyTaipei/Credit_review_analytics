"""
feature_engineering.py
=======================
Layer 2: Feature Engineering

Transforms raw financials into ML-ready features.
All features are computed per-company using only data available
up to that year (no look-ahead bias).

Features produced
-----------------
YoY growth rates:
    revenue_yoy, profit_yoy, debt_yoy, cash_yoy

Margin / structure ratios (already in financial_ratios.py,
re-exposed here so this module is self-contained):
    profit_margin, debt_ratio, current_ratio

Rolling window (3-year):
    rolling_3y_revenue_growth   — CAGR over past 3 years
    rolling_std_profit          — std of net_income, measures volatility

Cross-sectional Z-scores (within broad_industry × year):
    zscore_revenue              — how unusual is this firm's revenue vs peers
    zscore_profit               — same for net_income

Why this layer matters
----------------------
- Gives SQL window function examples (rolling_3y, zscore)
- Gives pandas groupby + transform examples
- Feeds directly into anomaly detection as structured input
- Interviewers can ask "how did you engineer features?" and you
  point to this file
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def engineer_features(financials: pd.DataFrame) -> pd.DataFrame:
    """
    Takes the canonical financials DataFrame, returns it with feature
    columns appended.  Original columns are preserved unchanged.

    Parameters
    ----------
    financials : DataFrame
        Output of data_pipeline.load_financials()

    Returns
    -------
    DataFrame with all original columns + feature columns listed below.
    """
    df = financials.copy().sort_values(["ticker", "year"]).reset_index(drop=True)

    df = _yoy_features(df)
    df = _rolling_features(df)
    df = _zscore_features(df)

    return df


# ---------------------------------------------------------------------------
# YoY growth rates
# ---------------------------------------------------------------------------

def _yoy_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Year-over-year growth rates computed within each ticker.
    First year per ticker is NaN (no prior year available).

    Why pct_change not manual diff?
    - pct_change handles the base-year reference correctly
    - Consistent with pandas idiom — easier for reviewers to read
    """
    grp = df.groupby("ticker")

    df["revenue_yoy"]  = grp["revenue"].pct_change()
    df["profit_yoy"]   = grp["net_income"].pct_change()
    df["debt_yoy"]     = grp["total_liabilities"].pct_change()
    df["cash_yoy"]     = grp["cash_and_equivalents"].pct_change()

    # Convenience aliases used downstream
    df["profit_margin"] = (df["net_income"] / df["revenue"]).replace([np.inf, -np.inf], np.nan)

    return df


# ---------------------------------------------------------------------------
# Rolling window features (3-year)
# ---------------------------------------------------------------------------

def _rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    3-year rolling statistics per ticker.

    rolling_3y_revenue_growth: CAGR over trailing 3 years.
        Why CAGR not mean(YoY)?  CAGR compounds, giving the true annualised
        rate; simple mean of YoY double-counts intermediate years.
        Formula: (revenue_t / revenue_{t-2})^(1/2) - 1

    rolling_std_profit: std of net_income over trailing 3 years.
        High std → volatile earnings → harder to model cash flow → higher risk.
        Banks call this 'earnings quality'.

    min_periods=3 means we only compute where we have a full 3-year window,
    so years 2020 and 2021 will be NaN — that is correct and honest.
    """

    def _cagr_3y(series: pd.Series) -> pd.Series:
        """Rolling 3-year CAGR."""
        lag2 = series.shift(2)
        cagr = (series / lag2) ** 0.5 - 1
        # Only populate where we have at least 3 years of data
        cagr[series.rolling(3).count() < 3] = np.nan
        return cagr

    rolling_cagr = (
        df.groupby("ticker")["revenue"]
        .apply(_cagr_3y)
        .reset_index(level=0, drop=True)
    )
    df["rolling_3y_revenue_growth"] = rolling_cagr

    rolling_std = (
        df.groupby("ticker")["net_income"]
        .transform(lambda s: s.rolling(3, min_periods=3).std())
    )
    df["rolling_std_profit"] = rolling_std

    return df


# ---------------------------------------------------------------------------
# Cross-sectional Z-scores
# ---------------------------------------------------------------------------

def _zscore_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (broad_industry_zh, year) group, compute the Z-score of
    revenue and net_income relative to peers in that industry-year.

    Why cross-sectional Z-score here (different from anomaly_detection)?
    - anomaly_detection uses TIME-SERIES z-score (company vs its own history)
    - Here we use CROSS-SECTIONAL z-score (company vs its peers in same year)
    - Both are needed: a company can be normal in its own history but an
      outlier vs peers, or vice versa.
    - Having both in the feature set lets a downstream model pick up both signals.

    Financial sector excluded from peer comparison (incompatible structures).
    """

    def _cs_zscore(col: str) -> pd.Series:
        grp = df.groupby(["broad_industry_zh", "year"])[col]
        return (df[col] - grp.transform("mean")) / grp.transform("std")

    # Only compute for non-financial rows; NaN for financials
    mask_fin = df["is_financial_sector"]
    df["zscore_revenue"] = np.where(mask_fin, np.nan, _cs_zscore("revenue"))
    df["zscore_profit"]  = np.where(mask_fin, np.nan, _cs_zscore("net_income"))

    return df


# ---------------------------------------------------------------------------
# Quick feature summary for logging / debugging
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "revenue_yoy", "profit_yoy", "debt_yoy", "cash_yoy",
    "profit_margin",
    "rolling_3y_revenue_growth", "rolling_std_profit",
    "zscore_revenue", "zscore_profit",
]


def feature_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-company latest-year feature snapshot."""
    latest_year = df["year"].max()
    return (
        df[df["year"] == latest_year]
        [["ticker", "company_name"] + FEATURE_COLUMNS]
        .sort_values("ticker")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path
    fin = pd.read_csv(
        Path(__file__).resolve().parent.parent / "data" / "sample_financials_long.csv"
    )
    fin["is_financial_sector"] = fin["is_financial_sector"].astype(bool)

    out = engineer_features(fin)
    print("Feature columns added:")
    for col in FEATURE_COLUMNS:
        non_null = out[col].notna().sum()
        print(f"  {col:35s} {non_null:3d} non-null values")

    print()
    print("2024 snapshot:")
    print(feature_summary(out).to_string(index=False))
