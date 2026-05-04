"""
financial_ratios.py
====================
Computes the financial ratios used in the credit review.

Coverage (8 required + Altman Z' as the bonus):

  Solvency / Liquidity
    - current_ratio
    - quick_ratio
    - debt_ratio
    - interest_coverage

  Profitability
    - gross_margin
    - operating_margin
    - roe
    - roa

  Efficiency
    - ar_days   (應收帳款週轉天數)
    - inventory_days

  Distress
    - altman_z_prime    (Altman 1983 — private-firm version)

Defending the design choices:
- Output is LONG format: (ticker, year, ratio_name, value).
  Tableau handles long format much more cleanly when you want multiple
  ratios as filterable / parameter-driven series.
- For financial-sector firms we explicitly emit NaN for ratios that
  don't apply (no inventory, no separate cogs).  We do NOT silently
  zero them out — that would mislead the dashboard.
- Average balance for ROE/ROA: we use (beginning + ending) / 2 when
  prior year is available, else year-end.  This matches CFA / IFRS
  conventions and is what TEJ and credit analysts use.
- Altman Z' (private-firm version) chosen over original Z:
    * Original Z assumes US listed companies, uses market value of equity
    * Z' replaces market value with book value → works for SMEs / private
      firms, which is closer to our future client base
    * For the 7 listed firms in our portfolio we still apply Z' for
      consistency and because the bank's actual SME book is private
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helper: safe division (avoid divide-by-zero, NaN out instead)
# ---------------------------------------------------------------------------
def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    den = den.replace(0, np.nan)
    return num / den


# ---------------------------------------------------------------------------
# Per-ticker computations (need lag for average balance)
# ---------------------------------------------------------------------------
def _compute_for_ticker(g: pd.DataFrame) -> pd.DataFrame:
    """
    g = financials for a single ticker, sorted by year ascending.
    Returns same index but with ratio columns added.
    """
    g = g.sort_values("year").copy()

    # Lagged values for average balance
    prev_assets = g["total_assets"].shift(1)
    prev_equity = g["total_equity"].shift(1)
    avg_assets = (g["total_assets"] + prev_assets) / 2
    avg_equity = (g["total_equity"] + prev_equity) / 2
    # First year: fall back to year-end (no prior year available)
    avg_assets = avg_assets.fillna(g["total_assets"])
    avg_equity = avg_equity.fillna(g["total_equity"])

    # ---------- Solvency / Liquidity ----------
    g["current_ratio"]    = _safe_div(g["current_assets"], g["current_liabilities"])
    g["quick_ratio"]      = _safe_div(g["current_assets"] - g["inventory"],
                                      g["current_liabilities"])
    g["debt_ratio"]       = _safe_div(g["total_liabilities"], g["total_assets"])
    g["interest_coverage"] = _safe_div(g["operating_income"], g["interest_expense"])

    # ---------- Profitability ----------
    g["gross_margin"]     = _safe_div(g["gross_profit"], g["revenue"])
    g["operating_margin"] = _safe_div(g["operating_income"], g["revenue"])
    g["roe"]              = _safe_div(g["net_income"], avg_equity)
    g["roa"]              = _safe_div(g["net_income"], avg_assets)

    # ---------- Efficiency (in days) ----------
    g["ar_days"]          = _safe_div(g["accounts_receivable"], g["revenue"]) * 365
    g["inventory_days"]   = _safe_div(g["inventory"], g["cogs"]) * 365

    # ---------- Altman Z' (private firm / non-financial only) ----------
    # Z' = 0.717 X1 + 0.847 X2 + 3.107 X3 + 0.420 X4 + 0.998 X5
    #   X1 = working capital / total assets
    #   X2 = retained earnings / total assets
    #   X3 = EBIT / total assets
    #   X4 = book value of equity / total liabilities  (← private-firm version)
    #   X5 = sales / total assets
    working_capital = g["current_assets"] - g["current_liabilities"]
    x1 = _safe_div(working_capital, g["total_assets"])
    x2 = _safe_div(g["retained_earnings"], g["total_assets"])
    x3 = _safe_div(g["operating_income"], g["total_assets"])    # EBIT ~ operating_income
    x4 = _safe_div(g["total_equity"], g["total_liabilities"])
    x5 = _safe_div(g["revenue"], g["total_assets"])
    g["altman_z_prime"] = 0.717*x1 + 0.847*x2 + 3.107*x3 + 0.420*x4 + 0.998*x5

    return g


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
RATIO_COLUMNS = [
    "current_ratio", "quick_ratio", "debt_ratio", "interest_coverage",
    "gross_margin", "operating_margin", "roe", "roa",
    "ar_days", "inventory_days",
    "altman_z_prime",
]

# Used downstream by Tableau / dashboard for grouping
RATIO_CATEGORIES = {
    "current_ratio":     "solvency",
    "quick_ratio":       "solvency",
    "debt_ratio":        "solvency",
    "interest_coverage": "solvency",
    "gross_margin":      "profitability",
    "operating_margin":  "profitability",
    "roe":               "profitability",
    "roa":               "profitability",
    "ar_days":           "efficiency",
    "inventory_days":    "efficiency",
    "altman_z_prime":    "distress",
}


def compute_ratios(financials: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all ratios for every (ticker, year).

    For financial-sector tickers, only ROE / ROA / debt_ratio are kept.
    Others are forced to NaN — the dashboard then renders them as N/A,
    not as misleading zeros.

    Returns
    -------
    DataFrame in WIDE format with one row per (ticker, year) and one
    column per ratio.  Use `pivot_to_long(...)` if you need long format
    for Tableau.
    """
    # Per-ticker computation. We use an explicit loop instead of
    # groupby().apply() because pandas 2+ silently drops the grouping
    # column from the result, which has bitten us before.
    pieces = [_compute_for_ticker(g) for _, g in financials.groupby("ticker")]
    out = pd.concat(pieces, ignore_index=True)

    # Mask non-applicable ratios for financial sector
    fin_mask = out["is_financial_sector"]
    not_applicable_for_financials = [
        "current_ratio", "quick_ratio", "interest_coverage",
        "gross_margin", "operating_margin",
        "ar_days", "inventory_days",
        "altman_z_prime",
    ]
    out.loc[fin_mask, not_applicable_for_financials] = np.nan

    return out


def pivot_to_long(ratios_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Convert wide ratios → long format ready for Tableau.

    Output columns:
      ticker, company_name, industry_zh, year, ratio_name, ratio_value, ratio_category
    """
    keep = ["ticker", "company_name", "industry", "industry_zh",
            "broad_industry", "broad_industry_zh",
            "year", "is_financial_sector"]
    long = ratios_wide.melt(
        id_vars=keep,
        value_vars=RATIO_COLUMNS,
        var_name="ratio_name",
        value_name="ratio_value",
    )
    long["ratio_category"] = long["ratio_name"].map(RATIO_CATEGORIES)
    # Drop NaN rows so Tableau doesn't try to plot empty cells
    long = long.dropna(subset=["ratio_value"]).reset_index(drop=True)
    return long


# ---------------------------------------------------------------------------
# Industry benchmarking
# ---------------------------------------------------------------------------
def add_industry_benchmark(ratios_long: pd.DataFrame) -> pd.DataFrame:
    """
    For each (broad_industry_zh, year, ratio_name), compute the median of
    non-financial peers.  Add it as a column so Tableau can plot
    company vs. peer median.

    Why broad_industry not narrow industry?
    - Each narrow sub-industry in our 7-firm portfolio has only 1 firm,
      making the "median" meaningless (= the firm itself).
    - Broad industry (manufacturing / services / financials) gives 2-3
      firms per group.  Still small, but methodologically valid.
    - In production with hundreds of firms in each TWSE bucket,
      narrow-industry medians become statistically robust again.
    """
    fin = ratios_long[~ratios_long["is_financial_sector"]]
    medians = (
        fin.groupby(["broad_industry_zh", "year", "ratio_name"], as_index=False)
        ["ratio_value"]
        .median()
        .rename(columns={"ratio_value": "industry_median"})
    )
    return ratios_long.merge(
        medians, on=["broad_industry_zh", "year", "ratio_name"], how="left"
    )


# ---------------------------------------------------------------------------
# Risk scoring (heuristic, not ML)
# ---------------------------------------------------------------------------
def compute_risk_score(ratios_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Simple rule-based composite risk score in [0, 100], where 100 = highest risk.

    Why rule-based, not ML?
    - With 35 firm-years and zero default labels, supervised ML is unjustifiable
    - Rules are auditable: a credit officer can read the formula and challenge
      individual weights; ML would be a black box
    - This MUST be auditable for any future regulatory examination

    Components (each scaled 0-100, then weighted):
      - Altman Z' band      35%   (lower Z' → higher risk)
      - Debt ratio          25%   (higher → higher risk)
      - Interest coverage   20%   (lower → higher risk)
      - Profit trend        20%   (declining ROE → higher risk)
    """
    out = ratios_wide.copy()

    # Altman: Z' < 1.23 → distress zone (35%)
    z = out["altman_z_prime"]
    altman_score = np.where(z.isna(), np.nan,
                            np.clip((2.9 - z) / (2.9 - 0.5) * 100, 0, 100))

    # Debt ratio: 0.7+ → high risk (25%)
    dr = out["debt_ratio"]
    debt_score = np.clip((dr - 0.3) / (0.8 - 0.3) * 100, 0, 100)

    # Interest coverage: < 3 → risky (20%)
    ic = out["interest_coverage"]
    ic_score = np.where(ic.isna(), np.nan,
                        np.clip((10 - ic) / (10 - 1) * 100, 0, 100))

    # ROE trend: 3-year change.  If declining sharply, raise score.
    out_sorted = out.sort_values(["ticker", "year"])
    roe_trend = out_sorted.groupby("ticker")["roe"].diff().fillna(0)
    out_sorted["roe_3y_chg"] = (
        out_sorted.groupby("ticker")["roe"].rolling(3).apply(
            lambda x: x.iloc[-1] - x.iloc[0] if len(x) == 3 else np.nan, raw=False
        ).reset_index(level=0, drop=True)
    )
    out = out_sorted
    trend_score = np.clip(-out["roe_3y_chg"] * 500, 0, 100)   # 20pp ROE drop → 100

    # Combine — using nan-aware mean of available components
    components = pd.DataFrame({
        "altman": altman_score,
        "debt":   debt_score,
        "ic":     ic_score,
        "trend":  trend_score,
    })
    weights = pd.Series({"altman": 0.35, "debt": 0.25, "ic": 0.20, "trend": 0.20})

    # Weighted mean ignoring NaN per row
    available = ~components.isna()
    used_weights = available.mul(weights, axis=1)
    norm = used_weights.sum(axis=1).replace(0, np.nan)
    score = (components.fillna(0) * used_weights).sum(axis=1) / norm

    out["risk_score"] = score.round(1)

    # Financial-sector firms naturally have ~95% debt ratios (deposits are
    # liabilities!) — this rule-based model would unfairly flag them. NaN
    # them out and require a separate model (NPL, CAR, etc.) for banks.
    out.loc[out["is_financial_sector"], "risk_score"] = np.nan

    # Risk band — what shows up on the dashboard heatmap
    out["risk_band"] = pd.cut(
        out["risk_score"],
        bins=[-1, 25, 50, 75, 101],
        labels=["低風險", "關注", "警示", "高風險"],
    )
    # Add a separate label for financials so dashboard doesn't show blank.
    # Need to extend categories first — pandas categorical doesn't let
    # you assign an unknown level.
    out["risk_band"] = out["risk_band"].cat.add_categories(["金融業(另採模型)"])
    out.loc[out["is_financial_sector"], "risk_band"] = "金融業(另採模型)"
    return out


# ---------------------------------------------------------------------------
# CLI for quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path
    csv_path = Path(__file__).resolve().parent.parent / "data" / "sample_financials_long.csv"
    fin = pd.read_csv(csv_path)
    fin["is_financial_sector"] = fin["is_financial_sector"].astype(bool)

    wide = compute_ratios(fin)
    wide = compute_risk_score(wide)
    long = pivot_to_long(wide)
    long = add_industry_benchmark(long)

    print(f"Wide: {wide.shape}")
    print(f"Long: {long.shape}")
    print()
    print("Latest year risk scores:")
    latest = wide[wide["year"] == wide["year"].max()][
        ["ticker", "company_name", "risk_score", "risk_band"]
    ].sort_values("risk_score", ascending=False)
    print(latest.to_string(index=False))
