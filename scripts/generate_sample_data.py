"""
generate_sample_data.py
========================
Produces a SIMULATED financials dataset shaped like real MOPS data,
so the rest of the pipeline (ratios → anomaly detection → dashboard)
can run end-to-end without API access.

Why simulated?
- MOPS scraping requires session management & is rate-limited
- This demo is for partner review; we want it to run reproducibly
- All numbers are plausible ballparks (TSMC has higher margins than
  Hon Hai etc.) but should NOT be cited as factual

Output: data/sample_financials_long.csv  (long format, ready for ratios)
        data/sample_industry_medians.csv (industry benchmarks)
"""

from pathlib import Path
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reproducibility — same seed → same numbers every run
# ---------------------------------------------------------------------------
RNG = np.random.default_rng(seed=20260504)

# ---------------------------------------------------------------------------
# Company profiles (anchors based on publicly known business model differences)
# These are the "true means" the simulator perturbs around — NOT real data.
# ---------------------------------------------------------------------------
COMPANIES = {
    "2330": {
        "name": "台積電",
        "industry": "semiconductors",
        "industry_zh": "半導體",
        "broad_industry": "manufacturing",
        "broad_industry_zh": "製造業",
        "is_financial": False,
        # Anchors: high margin, high ROE, low debt
        "revenue_2020": 1339,        # billion TWD
        "revenue_cagr": 0.20,
        "gross_margin_mean": 0.52,
        "op_margin_mean": 0.42,
        "net_margin_mean": 0.38,
        "asset_turnover": 0.55,
        "debt_ratio_mean": 0.30,
        "current_ratio_mean": 2.1,
        "quick_ratio_mean": 1.7,
        "ar_days_mean": 45,
        "inventory_days_mean": 90,
        "interest_coverage_mean": 95,
    },
    "2317": {
        "name": "鴻海",
        "industry": "electronics_manufacturing",
        "industry_zh": "電子代工",
        "broad_industry": "manufacturing",
        "broad_industry_zh": "製造業",
        "is_financial": False,
        # Anchors: low margin, high turnover, mid debt
        "revenue_2020": 5358,
        "revenue_cagr": 0.06,
        "gross_margin_mean": 0.06,
        "op_margin_mean": 0.027,
        "net_margin_mean": 0.022,
        "asset_turnover": 1.4,
        "debt_ratio_mean": 0.62,
        "current_ratio_mean": 1.4,
        "quick_ratio_mean": 1.0,
        "ar_days_mean": 65,
        "inventory_days_mean": 55,
        "interest_coverage_mean": 12,
    },
    "2308": {
        "name": "台達電",
        "industry": "electronics_components",
        "industry_zh": "電子零組件",
        "broad_industry": "manufacturing",
        "broad_industry_zh": "製造業",
        "is_financial": False,
        # Anchors: mid margin, moderate growth
        "revenue_2020": 282,
        "revenue_cagr": 0.10,
        "gross_margin_mean": 0.29,
        "op_margin_mean": 0.10,
        "net_margin_mean": 0.085,
        "asset_turnover": 0.85,
        "debt_ratio_mean": 0.45,
        "current_ratio_mean": 1.7,
        "quick_ratio_mean": 1.3,
        "ar_days_mean": 80,
        "inventory_days_mean": 70,
        "interest_coverage_mean": 35,
    },
    "2882": {
        "name": "國泰金",
        "industry": "financial_holding",
        "industry_zh": "金融控股",
        "broad_industry": "financials",
        "broad_industry_zh": "金融業",
        "is_financial": True,
        "revenue_2020": 670,
        "revenue_cagr": 0.04,
        "net_margin_mean": 0.13,
        "roe_mean": 0.09,
        "roa_mean": 0.006,
    },
    "2891": {
        "name": "中信金",
        "industry": "financial_holding",
        "industry_zh": "金融控股",
        "broad_industry": "financials",
        "broad_industry_zh": "金融業",
        "is_financial": True,
        "revenue_2020": 175,
        "revenue_cagr": 0.05,
        "net_margin_mean": 0.30,
        "roe_mean": 0.11,
        "roa_mean": 0.007,
    },
    "2912": {
        "name": "統一超",
        "industry": "retail",
        "industry_zh": "零售通路",
        "broad_industry": "services",
        "broad_industry_zh": "服務業",
        "is_financial": False,
        # Anchors: low margin, very high turnover, moderate debt
        "revenue_2020": 271,
        "revenue_cagr": 0.05,
        "gross_margin_mean": 0.34,
        "op_margin_mean": 0.043,
        "net_margin_mean": 0.038,
        "asset_turnover": 1.7,
        "debt_ratio_mean": 0.65,
        "current_ratio_mean": 0.9,   # retail typically has CR < 1
        "quick_ratio_mean": 0.55,
        "ar_days_mean": 8,           # mostly cash sales
        "inventory_days_mean": 25,
        "interest_coverage_mean": 22,
    },
    "2412": {
        "name": "中華電",
        "industry": "telecom",
        "industry_zh": "電信服務",
        "broad_industry": "services",
        "broad_industry_zh": "服務業",
        "is_financial": False,
        # Anchors: mid margin, low growth, very low debt
        "revenue_2020": 207,
        "revenue_cagr": 0.005,
        "gross_margin_mean": 0.36,
        "op_margin_mean": 0.20,
        "net_margin_mean": 0.155,
        "asset_turnover": 0.45,
        "debt_ratio_mean": 0.30,
        "current_ratio_mean": 1.1,
        "quick_ratio_mean": 1.0,
        "ar_days_mean": 40,
        "inventory_days_mean": 15,
        "interest_coverage_mean": 80,
    },
}

YEARS = [2020, 2021, 2022, 2023, 2024]


def _noise(scale: float = 0.05) -> float:
    """Multiplicative noise: 1 ± scale, clipped so ratios stay sensible."""
    return float(np.clip(RNG.normal(1.0, scale), 1 - 3 * scale, 1 + 3 * scale))


def _build_non_financial(ticker: str, profile: dict) -> list[dict]:
    """
    Build 5 years of plausible income-statement & balance-sheet line items
    for a non-financial company.  We generate the *raw items* (revenue,
    COGS, total assets, etc.) so the ratio module can recompute everything
    — that mirrors how a real pipeline works.
    """
    rows = []
    revenue_prev = profile["revenue_2020"]

    for i, year in enumerate(YEARS):
        # Revenue: grow at CAGR with noise, plus an injected stress year for some
        growth = profile["revenue_cagr"] * _noise(0.30)
        if ticker == "2308" and year == 2023:
            growth = -0.05            # simulate a soft year for Delta
        if ticker == "2317" and year == 2023:
            growth = -0.07            # Hon Hai 2023 dip
        revenue = revenue_prev * (1 + growth) if i > 0 else profile["revenue_2020"]
        revenue_prev = revenue

        gross_margin = profile["gross_margin_mean"] * _noise(0.04)
        op_margin = profile["op_margin_mean"] * _noise(0.06)
        net_margin = profile["net_margin_mean"] * _noise(0.06)

        gross_profit = revenue * gross_margin
        operating_income = revenue * op_margin
        net_income = revenue * net_margin
        cogs = revenue - gross_profit

        # Balance sheet — derived from asset turnover + debt ratio
        total_assets = revenue / profile["asset_turnover"] * _noise(0.04)
        total_liabilities = total_assets * profile["debt_ratio_mean"] * _noise(0.05)
        total_equity = total_assets - total_liabilities

        # Working capital items — derived from days metrics
        accounts_receivable = revenue * profile["ar_days_mean"] / 365 * _noise(0.08)
        inventory = cogs * profile["inventory_days_mean"] / 365 * _noise(0.08)

        # Approximate current assets / current liabilities from current ratio
        current_liabilities = total_liabilities * 0.55 * _noise(0.05)
        current_assets = current_liabilities * profile["current_ratio_mean"] * _noise(0.05)
        # Quick assets = current assets - inventory; back-solve cash from quick ratio
        quick_assets = current_liabilities * profile["quick_ratio_mean"] * _noise(0.05)
        cash_and_equivalents = max(quick_assets - accounts_receivable, total_assets * 0.05)

        # Interest expense from interest coverage
        interest_expense = max(operating_income / profile["interest_coverage_mean"], 0.001)

        # Cash flow proxies
        operating_cash_flow = net_income * _noise(0.15) + total_assets * 0.04
        retained_earnings = total_equity * 0.7 * _noise(0.05)

        # Market value proxy (for Altman Z): use 2x book equity as a rough P/B
        # Not perfect but acceptable for demo; in production pull from TWSE
        market_value_equity = total_equity * 2.0 * _noise(0.10)

        rows.append({
            "ticker": ticker,
            "company_name": profile["name"],
            "industry": profile["industry"],
            "industry_zh": profile["industry_zh"],
            "broad_industry": profile["broad_industry"],
            "broad_industry_zh": profile["broad_industry_zh"],
            "year": year,
            "is_financial_sector": profile["is_financial"],
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "operating_income": round(operating_income, 2),
            "net_income": round(net_income, 2),
            "interest_expense": round(interest_expense, 3),
            "total_assets": round(total_assets, 2),
            "total_liabilities": round(total_liabilities, 2),
            "total_equity": round(total_equity, 2),
            "current_assets": round(current_assets, 2),
            "current_liabilities": round(current_liabilities, 2),
            "cash_and_equivalents": round(cash_and_equivalents, 2),
            "accounts_receivable": round(accounts_receivable, 2),
            "inventory": round(inventory, 2),
            "retained_earnings": round(retained_earnings, 2),
            "market_value_equity": round(market_value_equity, 2),
            "operating_cash_flow": round(operating_cash_flow, 2),
        })

    return rows


def _build_financial(ticker: str, profile: dict) -> list[dict]:
    """
    Financial-sector firms have fundamentally different statements.
    For demo we only populate fields that make sense (revenue ≈ net interest
    + fee income; assets are huge and dominated by financial assets; no
    inventory, no COGS).  Inventory/AR-related ratios will be N/A downstream.
    """
    rows = []
    revenue_prev = profile["revenue_2020"]

    for i, year in enumerate(YEARS):
        growth = profile["revenue_cagr"] * _noise(0.40)
        revenue = revenue_prev * (1 + growth) if i > 0 else profile["revenue_2020"]
        revenue_prev = revenue

        net_margin = profile["net_margin_mean"] * _noise(0.10)
        net_income = revenue * net_margin

        # Financial firms are highly leveraged — equity is small fraction of assets
        roa = profile["roa_mean"] * _noise(0.10)
        total_assets = net_income / roa

        roe = profile["roe_mean"] * _noise(0.08)
        total_equity = net_income / roe
        total_liabilities = total_assets - total_equity

        rows.append({
            "ticker": ticker,
            "company_name": profile["name"],
            "industry": profile["industry"],
            "industry_zh": profile["industry_zh"],
            "broad_industry": profile["broad_industry"],
            "broad_industry_zh": profile["broad_industry_zh"],
            "year": year,
            "is_financial_sector": True,
            "revenue": round(revenue, 2),
            "cogs": np.nan,
            "gross_profit": np.nan,
            "operating_income": round(net_income * 1.25, 2),  # rough
            "net_income": round(net_income, 2),
            "interest_expense": np.nan,            # interest is core business, not expense
            "total_assets": round(total_assets, 2),
            "total_liabilities": round(total_liabilities, 2),
            "total_equity": round(total_equity, 2),
            "current_assets": np.nan,
            "current_liabilities": np.nan,
            "cash_and_equivalents": round(total_assets * 0.08, 2),
            "accounts_receivable": np.nan,
            "inventory": np.nan,
            "retained_earnings": round(total_equity * 0.6, 2),
            "market_value_equity": round(total_equity * 1.2, 2),
            "operating_cash_flow": round(net_income * _noise(0.20), 2),
        })

    return rows


def build_dataset() -> pd.DataFrame:
    """Build the full long-format financials table."""
    all_rows = []
    for ticker, profile in COMPANIES.items():
        if profile["is_financial"]:
            all_rows.extend(_build_financial(ticker, profile))
        else:
            all_rows.extend(_build_non_financial(ticker, profile))

    df = pd.DataFrame(all_rows)
    return df.sort_values(["ticker", "year"]).reset_index(drop=True)


def build_industry_medians(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute industry-level medians for non-financial firms.
    These are the benchmarks the dashboard will use for peer comparison.
    Computed BEFORE ratios — we'll let the ratio module compute them
    consistently from these benchmark line items.
    """
    non_fin = df[~df["is_financial_sector"]].copy()
    medians = (
        non_fin.groupby(["industry", "industry_zh", "year"], as_index=False)
        .median(numeric_only=True)
    )
    medians["ticker"] = "INDUSTRY_MEDIAN"
    medians["company_name"] = medians["industry_zh"] + "_中位數"
    medians["is_financial_sector"] = False
    return medians


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_dataset()
    medians = build_industry_medians(df)

    df.to_csv(out_dir / "sample_financials_long.csv", index=False)
    medians.to_csv(out_dir / "sample_industry_medians.csv", index=False)

    print(f"✓ Generated {len(df)} firm-year rows across {df['ticker'].nunique()} companies")
    print(f"  → {out_dir / 'sample_financials_long.csv'}")
    print(f"  → {out_dir / 'sample_industry_medians.csv'}")
    print()
    print("Sample preview:")
    print(df.head(3).to_string())
