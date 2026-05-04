"""
data_pipeline.py
================
Fetches Taiwan listed-company financial statements and normalizes them
into a clean long-format DataFrame.

Two paths supported:
  1. Real API:  FinMind (free tier) or TWSE OpenAPI
  2. Sample:    Read pre-generated CSV from data/sample_financials_long.csv

Defending the design choices:
- We deliberately abstract the source behind `load_financials()`.  The
  rest of the codebase doesn't care whether numbers came from FinMind,
  MOPS, or a CSV — it only sees a clean long-format DataFrame.
- For partner demo we default to the sample CSV: it's reproducible, no
  network dependency, no API key.  In production we'd swap in the
  MOPS fetcher behind the same interface.

Why FinMind over MOPS direct?
- MOPS uses CSRF tokens + form-based pagination; building a robust
  scraper takes weeks and breaks every time MOPS redesigns
- FinMind is a community-maintained Python package that already wraps
  this; widely used by Taiwan fintech startups and academic researchers
- Trade-off: external dependency.  For a regulated bank we'd negotiate
  a direct MOPS data feed or use TEJ (台灣經濟新報) — both standard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Canonical column order — anything downstream relies on this contract
CANONICAL_COLUMNS = [
    "ticker", "company_name", "industry", "industry_zh",
    "broad_industry", "broad_industry_zh",
    "year",
    "is_financial_sector",
    "revenue", "cogs", "gross_profit", "operating_income", "net_income",
    "interest_expense",
    "total_assets", "total_liabilities", "total_equity",
    "current_assets", "current_liabilities",
    "cash_and_equivalents", "accounts_receivable", "inventory",
    "retained_earnings", "market_value_equity",
    "operating_cash_flow",
]


# ---------------------------------------------------------------------------
# Public entry point — what the rest of the codebase calls
# ---------------------------------------------------------------------------
def load_financials(
    source: str = "sample",
    sample_csv_path: Optional[Path] = None,
    finmind_token: Optional[str] = None,
    tickers: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Load financial statements in canonical long format.

    Parameters
    ----------
    source : {"sample", "finmind", "twse"}
        Where to pull data from. Default "sample" for reproducible demo.
    sample_csv_path : Path, optional
        Path to pre-generated CSV; only used when source="sample".
    finmind_token : str, optional
        FinMind API token; only used when source="finmind".
    tickers : list[str], optional
        Restrict to these tickers (useful for testing).

    Returns
    -------
    DataFrame with columns matching CANONICAL_COLUMNS.
    """
    if source == "sample":
        df = _load_from_sample(sample_csv_path)
    elif source == "finmind":
        df = _fetch_from_finmind(finmind_token, tickers)
    elif source == "twse":
        df = _fetch_from_twse(tickers)
    else:
        raise ValueError(f"Unknown source: {source}")

    df = _validate_and_clean(df)
    return df


# ---------------------------------------------------------------------------
# Source 1 — sample CSV (default for demo)
# ---------------------------------------------------------------------------
def _load_from_sample(csv_path: Optional[Path]) -> pd.DataFrame:
    if csv_path is None:
        # Default location relative to this file
        csv_path = Path(__file__).resolve().parent.parent / "data" / "sample_financials_long.csv"

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Sample CSV not found at {csv_path}. "
            "Run scripts/generate_sample_data.py first."
        )

    logger.info("Loading sample financials from %s", csv_path)
    return pd.read_csv(csv_path)


# ---------------------------------------------------------------------------
# Source 2 — FinMind API
# ---------------------------------------------------------------------------
FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"


def _fetch_from_finmind(
    token: Optional[str],
    tickers: Optional[list[str]],
) -> pd.DataFrame:
    """
    Fetch from FinMind. Free tier requires a token but is generous enough
    for 7 companies × 5 years of quarterly data.

    Note: FinMind returns Taiwan financial reports indexed by "date" with
    a quarterly cadence; we aggregate to annual here.

    For brevity this is a simplified fetcher — production version would
    handle:
      - Pagination
      - Quarterly to annual reconciliation (sum vs. last quarter for
        balance-sheet items)
      - Rate limit / retry with exponential backoff
      - Caching to disk to avoid hammering the API
    """
    if token is None:
        raise ValueError("FinMind requires a token. See https://finmindtrade.com")

    if not tickers:
        tickers = ["2330", "2317", "2308", "2882", "2891", "2912", "2412"]

    frames = []
    for ticker in tickers:
        for dataset in ("TaiwanStockFinancialStatements",
                        "TaiwanStockBalanceSheet"):
            params = {
                "dataset": dataset,
                "data_id": ticker,
                "start_date": "2020-01-01",
                "end_date": "2024-12-31",
                "token": token,
            }
            resp = requests.get(FINMIND_BASE, params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != 200:
                logger.warning("FinMind issue for %s/%s: %s", ticker, dataset, payload)
                continue
            frames.append(pd.DataFrame(payload["data"]))

    raw = pd.concat(frames, ignore_index=True)

    # FinMind returns long format with `type` = line item.  We need to pivot
    # to wide (one row per ticker-year), then map types to our canonical names.
    # Implementation left as TODO — this is where most of the engineering
    # effort would actually go in production.
    raise NotImplementedError(
        "Full FinMind integration is left as a TODO for the production build. "
        "For demo, use source='sample'. The mapping table from FinMind `type` "
        "values to CANONICAL_COLUMNS has 30+ entries and needs auditor sign-off."
    )


# ---------------------------------------------------------------------------
# Source 3 — TWSE OpenAPI
# ---------------------------------------------------------------------------
def _fetch_from_twse(tickers: Optional[list[str]]) -> pd.DataFrame:
    """
    TWSE OpenAPI (https://openapi.twse.com.tw) gives free access to
    aggregated company info but not full financial statements.  Most useful
    for current price (for Altman Z market_value_equity) and basic
    EPS / book value metrics.

    For full statements we'd combine TWSE OpenAPI + MOPS scraping, or use
    a paid feed like TEJ.
    """
    raise NotImplementedError(
        "TWSE OpenAPI doesn't provide full income statements. "
        "Use it as a supplement (price data) alongside FinMind/MOPS."
    )


# ---------------------------------------------------------------------------
# Validation — cheap defensive checks; saves hours of debugging later
# ---------------------------------------------------------------------------
def _validate_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Ensure all canonical columns present
    missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # 2. Type discipline
    df["year"] = df["year"].astype(int)
    df["ticker"] = df["ticker"].astype(str)
    df["is_financial_sector"] = df["is_financial_sector"].astype(bool)

    numeric_cols = [c for c in CANONICAL_COLUMNS
                    if c not in {"ticker", "company_name", "industry",
                                 "industry_zh", "broad_industry",
                                 "broad_industry_zh", "year",
                                 "is_financial_sector"}]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    # 3. Sanity: total_assets ≈ total_liabilities + total_equity
    eq_check = df["total_assets"] - (df["total_liabilities"] + df["total_equity"])
    bad = eq_check.abs() > df["total_assets"] * 0.01    # 1% tolerance
    if bad.any():
        logger.warning(
            "Balance sheet identity violated for %d rows; investigate before use",
            int(bad.sum()),
        )

    # 4. No duplicate (ticker, year)
    dups = df.duplicated(subset=["ticker", "year"])
    if dups.any():
        raise ValueError(f"Duplicate (ticker, year) rows: {df[dups][['ticker', 'year']].values.tolist()}")

    # 5. Sort
    df = df.sort_values(["ticker", "year"]).reset_index(drop=True)

    return df[CANONICAL_COLUMNS]


# ---------------------------------------------------------------------------
# CLI for quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    df = load_financials(source="sample")
    print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers, "
          f"years {df['year'].min()}–{df['year'].max()}")
    print(df.groupby("industry_zh").size().to_string())
