"""
Generate company-level credit review Markdown reports.

Purpose:
- Read outputs/dashboard_credit_review.csv
- Generate one Markdown report per company-year
- Add report_path and optional report_url columns back to dashboard_credit_review.csv

Usage:
    python scripts/generate_company_reports.py

Optional:
    python scripts/generate_company_reports.py --github-base-url "https://github.com/JoeyTaipei/Credit_review_analytics/blob/main/reports"

Notes:
- Tableau cannot directly "run Python" when you click a dashboard.
- The practical design is:
  1. Generate reports before the Tableau demo.
  2. Add report_path / report_url to the Tableau data source.
  3. Use Tooltip or URL Action in Tableau to open the report.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV = PROJECT_ROOT / "outputs" / "dashboard_credit_review.csv"
REPORT_DIR = PROJECT_ROOT / "reports"


def safe_filename(value: str) -> str:
    """Convert company/ticker text into a safe filename."""
    value = str(value).strip()
    value = re.sub(r"[^\w\-.]+", "_", value, flags=re.UNICODE)
    return value.strip("_") or "company"


def pick_col(df: pd.DataFrame, candidates: list[str], default: str | None = None) -> str | None:
    """Find the first matching column name from candidates."""
    lower_map = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return default


def fmt(value, digits: int = 2) -> str:
    """Format values safely for Markdown."""
    if pd.isna(value):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def generate_report(row: pd.Series, cols: dict[str, str | None]) -> str:
    company = row.get(cols["company"], "Unknown Company") if cols["company"] else "Unknown Company"
    ticker = row.get(cols["ticker"], company) if cols["ticker"] else company
    year = row.get(cols["year"], "N/A") if cols["year"] else "N/A"
    industry = row.get(cols["industry"], "N/A") if cols["industry"] else "N/A"
    risk_score = row.get(cols["risk_score"], "N/A") if cols["risk_score"] else "N/A"
    risk_level = row.get(cols["risk_level"], "N/A") if cols["risk_level"] else "N/A"
    suggested_action = row.get(cols["suggested_action"], "Further Review") if cols["suggested_action"] else "Further Review"
    review_reason = row.get(cols["review_reason"], "Risk indicators require analyst review.") if cols["review_reason"] else "Risk indicators require analyst review."

    debt_ratio = row.get(cols["debt_ratio"], "N/A") if cols["debt_ratio"] else "N/A"
    interest_coverage = row.get(cols["interest_coverage"], "N/A") if cols["interest_coverage"] else "N/A"
    current_ratio = row.get(cols["current_ratio"], "N/A") if cols["current_ratio"] else "N/A"
    altman = row.get(cols["altman"], "N/A") if cols["altman"] else "N/A"

    return f"""# 授信覆審報告｜{company}

## 1. 基本資訊

| 項目 | 內容 |
|---|---|
| 公司 | {company} |
| Ticker | {ticker} |
| 年度 | {year} |
| 產業 | {industry} |
| 風險等級 | {risk_level} |
| 綜合風險分數 | {fmt(risk_score)} |

---

## 2. 核心財務指標

| 指標 | 數值 | 解讀 |
|---|---:|---|
| Debt Ratio | {fmt(debt_ratio)} | 衡量槓桿程度，越高代表負債壓力越大 |
| Interest Coverage | {fmt(interest_coverage)} | 衡量利息償付能力，越低代表償債壓力越高 |
| Current Ratio | {fmt(current_ratio)} | 衡量短期流動性 |
| Altman Z' Score | {fmt(altman)} | 衡量企業財務壓力與破產風險 |

---

## 3. 系統建議行動

**Suggested Action：** {suggested_action}

**Review Reason：**  
{review_reason}

---

## 4. 分析師覆核重點

- 檢查該公司近 5 年風險分數是否持續上升
- 比較同產業其他公司，確認是否為產業共同壓力或公司個別問題
- 重新檢視授信額度、擔保品、還款能力與最新財報
- 若風險等級為 High / Critical，建議進入人工覆審流程

---

## 5. 重要聲明

本報告由 Python pipeline 根據模擬財務資料自動產生，僅作為 AI-assisted credit review demo。  
此報告不是正式授信決策，最終判斷仍需由授信分析師或授信委員會覆核。
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(OUTPUT_CSV),
        help="Path to dashboard_credit_review.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPORT_DIR),
        help="Directory to save Markdown reports",
    )
    parser.add_argument(
        "--github-base-url",
        default="",
        help="Optional GitHub folder URL for Tableau URL action, e.g. https://github.com/USER/REPO/blob/main/reports",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Cannot find input CSV: {input_path}")

    df = pd.read_csv(input_path)

    cols = {
        "company": pick_col(df, ["Company Name", "company_name", "company", "Company"]),
        "ticker": pick_col(df, ["Ticker", "ticker"]),
        "year": pick_col(df, ["Year", "year"]),
        "industry": pick_col(df, ["Industry", "industry"]),
        "risk_score": pick_col(df, ["Risk Score", "risk_score", "combined_score", "Combined Score"]),
        "risk_level": pick_col(df, ["Risk Level", "risk_level", "Risk Band", "risk_band"]),
        "suggested_action": pick_col(df, ["suggested_action", "Suggested Action", "credit_action"]),
        "review_reason": pick_col(df, ["review_reason", "Review Reason", "action_reason"]),
        "debt_ratio": pick_col(df, ["debt_ratio", "Debt Ratio"]),
        "interest_coverage": pick_col(df, ["interest_coverage", "Interest Coverage"]),
        "current_ratio": pick_col(df, ["current_ratio", "Current Ratio"]),
        "altman": pick_col(df, ["altman_z", "Altman Z", "Altman Z'", "altman_z_score"]),
    }

    report_paths = []
    report_urls = []

    for _, row in df.iterrows():
        company = row.get(cols["company"], "company") if cols["company"] else "company"
        ticker = row.get(cols["ticker"], company) if cols["ticker"] else company
        year = row.get(cols["year"], "year") if cols["year"] else "year"

        filename = f"{safe_filename(ticker)}_{safe_filename(year)}_credit_review.md"
        report_path = output_dir / filename
        report_path.write_text(generate_report(row, cols), encoding="utf-8")

        # Store relative path for GitHub and local reference
        relative_path = report_path.relative_to(PROJECT_ROOT).as_posix()
        report_paths.append(relative_path)

        if args.github_base_url:
            report_urls.append(args.github_base_url.rstrip("/") + "/" + filename)
        else:
            report_urls.append("")

    df["report_path"] = report_paths
    df["report_url"] = report_urls

    df.to_csv(input_path, index=False, encoding="utf-8-sig")

    print(f"Generated {len(report_paths)} reports in: {output_dir}")
    print(f"Updated CSV with report_path/report_url: {input_path}")


if __name__ == "__main__":
    main()
