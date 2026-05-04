"""
run_full_pipeline.py
=====================
End-to-end runner: data → ratios → anomalies → outputs for Tableau & LLM.

Usage:
    python scripts/run_full_pipeline.py

Outputs (all in outputs/):
    ratios_long.csv          ← main Tableau source: ratios over time
    ratios_wide.csv          ← per (ticker, year) snapshot with risk score
    anomalies.csv            ← all detected anomalies, all years
    sample_llm_input.json    ← example LLM input for one focal company
    sample_llm_output.md     ← LLM stub output for that focal company
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Path bootstrap: allow running as `python scripts/run_full_pipeline.py`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_pipeline import load_financials                # noqa: E402
from src.financial_ratios import (                           # noqa: E402
    compute_ratios, compute_risk_score,
    pivot_to_long, add_industry_benchmark,
)
from src.anomaly_detection import (                          # noqa: E402
    build_signals, detect_anomalies_zscore,
)
from src.llm_summary import CompanyAnalysisInput, stub_review_summary  # noqa: E402


def main():
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)

    print("[1/5] Loading financials …")
    fin = load_financials(source="sample")
    print(f"      {len(fin)} firm-year rows, {fin['ticker'].nunique()} tickers")

    print("[2/5] Computing ratios …")
    wide = compute_ratios(fin)
    wide = compute_risk_score(wide)
    long = pivot_to_long(wide)
    long = add_industry_benchmark(long)

    wide.to_csv(out_dir / "ratios_wide.csv", index=False)
    long.to_csv(out_dir / "ratios_long.csv", index=False)
    print(f"      → {out_dir/'ratios_wide.csv'}  ({wide.shape})")
    print(f"      → {out_dir/'ratios_long.csv'}  ({long.shape})")

    print("[3/5] Detecting anomalies …")
    signals = build_signals(fin)
    anomalies = detect_anomalies_zscore(signals)
    anomalies.to_csv(out_dir / "anomalies.csv", index=False)
    n_flagged = anomalies["is_anomaly"].sum()
    print(f"      → {out_dir/'anomalies.csv'}  ({len(anomalies)} rows, {n_flagged} flagged)")

    print("[4/5] Building LLM input for focal company (2317 鴻海) …")
    focal = "2317"
    review_year = wide["year"].max()
    focal_row = wide[(wide["ticker"] == focal) & (wide["year"] == review_year)].iloc[0]

    # Industry medians for the focal company's industry (broad grouping)
    medians = (
        long[
            (long["broad_industry_zh"] == focal_row["broad_industry_zh"])
            & (long["year"] == review_year)
        ]
        .groupby("ratio_name")["industry_median"]
        .first()
        .to_dict()
    )

    # Anomalies for the focal company (latest year only)
    focal_anomalies = anomalies[
        (anomalies["ticker"] == focal)
        & (anomalies["is_anomaly"])
    ][["signal_zh", "year", "z_score", "direction"]].rename(
        columns={"signal_zh": "signal"}
    )

    # 5y CAGR
    revenue_series = fin[fin["ticker"] == focal].sort_values("year")["revenue"]
    revenue_5y_cagr = (
        (revenue_series.iloc[-1] / revenue_series.iloc[0]) ** (1 / 4) - 1
        if len(revenue_series) >= 5 else None
    )
    debt_5y_change = (
        fin[fin["ticker"] == focal].sort_values("year")["total_liabilities"].iloc[-1]
        / fin[fin["ticker"] == focal].sort_values("year")["total_liabilities"].iloc[0]
        - 1
    )

    payload = CompanyAnalysisInput(
        ticker=focal,
        company_name=focal_row["company_name"],
        industry_zh=focal_row["industry_zh"],
        broad_industry_zh=focal_row["broad_industry_zh"],
        review_year=int(review_year),
        current_ratio=round(float(focal_row["current_ratio"]), 3),
        debt_ratio=round(float(focal_row["debt_ratio"]), 3),
        interest_coverage=round(float(focal_row["interest_coverage"]), 1),
        operating_margin=round(float(focal_row["operating_margin"]), 3),
        roe=round(float(focal_row["roe"]), 3),
        altman_z_prime=round(float(focal_row["altman_z_prime"]), 2),
        revenue_5y_cagr=round(float(revenue_5y_cagr), 3) if revenue_5y_cagr else None,
        debt_5y_change=round(float(debt_5y_change), 3),
        risk_score=float(focal_row["risk_score"]),
        risk_band=str(focal_row["risk_band"]),
        anomalies=focal_anomalies.to_dict(orient="records"),
        industry_median_debt_ratio=round(float(medians.get("debt_ratio", 0)), 3),
        industry_median_operating_margin=round(float(medians.get("operating_margin", 0)), 3),
        industry_median_roe=round(float(medians.get("roe", 0)), 3),
    )

    with open(out_dir / "sample_llm_input.json", "w", encoding="utf-8") as f:
        json.dump(payload.__dict__, f, ensure_ascii=False, indent=2, default=str)
    print(f"      → {out_dir/'sample_llm_input.json'}")

    print("[5/5] Generating stub LLM output (no API call) …")
    summary = stub_review_summary(payload)
    with open(out_dir / "sample_llm_output.md", "w", encoding="utf-8") as f:
        f.write(f"# {payload.company_name} ({payload.ticker}) {payload.review_year} 年度授信覆審意見草稿\n\n")
        f.write(summary)
        f.write("\n")
    print(f"      → {out_dir/'sample_llm_output.md'}")

    print("\n✓ Pipeline complete.  Open outputs/ratios_long.csv in Tableau to start.")


if __name__ == "__main__":
    main()
