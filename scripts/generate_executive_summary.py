# =============================================================================
# scripts/generate_executive_summary.py  (REFINED)
# Portfolio-level Executive Summary Generator
# =============================================================================
# 【主要修正】
# - 全部欄位用 df.get() 安全存取
# - 一致的 high-risk 判斷邏輯(英中文 / score fallback 三層)
# - get_deteriorating_companies 處理單年資料不 crash
# - 找不到 risk_score 欄位時,給合理 fallback,不直接退出
# =============================================================================

import pandas as pd
import numpy as np
import logging
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. 載入主資料
# ─────────────────────────────────────────────
def load_input(outputs_dir: Path) -> pd.DataFrame:
    """優先讀 dashboard_credit_review.csv(欄位最完整)"""
    candidates = [
        outputs_dir / "dashboard_credit_review.csv",
        outputs_dir / "risk_flags.csv",
    ]
    for path in candidates:
        if path.exists():
            logger.info(f"載入 {path.name}")
            df = pd.read_csv(path)
            # 統一 key 型別
            if "ticker" in df.columns:
                df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
            if "year" in df.columns:
                df["year"] = pd.to_numeric(df["year"], errors="coerce")
                df = df.dropna(subset=["year"])
                df["year"] = df["year"].astype(int)
            return df
    raise FileNotFoundError(
        "找不到 dashboard_credit_review.csv 或 risk_flags.csv,"
        "請先執行 run_full_pipeline.py"
    )


# ─────────────────────────────────────────────
# 2. 風險判斷統一邏輯(三層 fallback)
# ─────────────────────────────────────────────
def get_high_risk_mask(df: pd.DataFrame) -> pd.Series:
    """
    high-risk 條件(只要符合任一即視為高風險):
    - final_risk_level in ['high', 'critical']
    - risk_band in ['高風險', '警示']
    - combined_score > 0.6 (備用)
    """
    mask = pd.Series(False, index=df.index)

    if "final_risk_level" in df.columns:
        levels = df["final_risk_level"].astype(str).str.lower().str.strip()
        mask = mask | levels.isin(["high", "critical"])

    if "risk_band" in df.columns:
        bands = df["risk_band"].astype(str)
        mask = mask | bands.isin(["高風險", "警示"])

    # 若兩欄都沒有訊號,fallback
    if not mask.any() and "combined_score" in df.columns:
        logger.warning("使用 combined_score > 0.6 作為高風險判斷(備用)")
        scores = pd.to_numeric(df["combined_score"], errors="coerce").fillna(0)
        mask = scores > 0.6

    return mask


def get_score_column(df: pd.DataFrame) -> str | None:
    """挑選風險評分欄位(優先序)"""
    for col in ["combined_score", "risk_score", "anomaly_score"]:
        if col in df.columns and not df[col].isna().all():
            return col
    return None


# ─────────────────────────────────────────────
# 3. 惡化公司偵測
# ─────────────────────────────────────────────
def get_deteriorating_tickers(df: pd.DataFrame, year_cutoff: int = None) -> set:
    """
    定義:風險分數連續 ≥ 2 年上升的公司
    - 至少需 3 個年度資料才算「連續兩年上升」
    - 只有 2 個年度時,放寬為「最後一年上升」
    """
    score_col = get_score_column(df)
    if score_col is None or "ticker" not in df.columns or "year" not in df.columns:
        return set()

    if year_cutoff is not None:
        df = df[df["year"] <= year_cutoff]

    deteriorating = set()
    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("year")
        scores = pd.to_numeric(g[score_col], errors="coerce").dropna().values

        if len(scores) >= 3:
            # 最後兩個 diff 都 > 0 = 連續兩年惡化
            diffs = np.diff(scores)
            if diffs[-1] > 0 and diffs[-2] > 0:
                deteriorating.add(ticker)
        elif len(scores) == 2:
            # 放寬:最後一年上升
            if scores[-1] > scores[0]:
                deteriorating.add(ticker)

    return deteriorating


# ─────────────────────────────────────────────
# 4. 確保關鍵欄位存在
# ─────────────────────────────────────────────
def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """補齊執行 summary 需要的欄位,避免 KeyError"""
    df = df.copy()

    # credit_exposure
    if "credit_exposure" not in df.columns:
        if "total_assets" in df.columns:
            logger.warning("以 total_assets × 0.3 估算 credit_exposure")
            df["credit_exposure"] = pd.to_numeric(
                df["total_assets"], errors="coerce"
            ).fillna(0) * 0.3
        else:
            logger.warning("無 credit_exposure 也無 total_assets,模擬為 1")
            df["credit_exposure"] = 1.0

    df["credit_exposure"] = pd.to_numeric(
        df["credit_exposure"], errors="coerce"
    ).fillna(0)

    # company_name
    if "company_name" not in df.columns:
        df["company_name"] = df.get("ticker", "Unknown")

    return df


def pick_industry_column(df: pd.DataFrame) -> str | None:
    for col in ["industry_zh", "broad_industry_zh", "industry"]:
        if col in df.columns:
            return col
    return None


# ─────────────────────────────────────────────
# 5. 主函數
# ─────────────────────────────────────────────
def generate_summary(outputs_dir: Path) -> pd.DataFrame:
    df = load_input(outputs_dir)
    df = ensure_required_columns(df)

    if "year" not in df.columns or "ticker" not in df.columns:
        raise ValueError("資料缺少必要欄位 ticker / year")

    score_col = get_score_column(df)
    industry_col = pick_industry_column(df)
    years = sorted(df["year"].unique())

    rows = []
    for year in years:
        yr = df[df["year"] == year]

        total_companies = yr["ticker"].nunique()
        total_exposure = float(yr["credit_exposure"].sum())

        # 高風險
        hr_mask = get_high_risk_mask(yr)
        hr_df = yr[hr_mask]
        hr_companies = hr_df["ticker"].nunique()
        hr_exposure = float(hr_df["credit_exposure"].sum())
        hr_pct = hr_exposure / total_exposure if total_exposure > 0 else 0.0

        # 惡化公司(用 ≤ 當年的歷史資料計算)
        deteriorating = get_deteriorating_tickers(df, year_cutoff=year)
        current_tickers = set(yr["ticker"].unique())
        deter_in_year = deteriorating & current_tickers

        # 最高風險公司
        if score_col and not yr[score_col].isna().all():
            scores = pd.to_numeric(yr[score_col], errors="coerce")
            top_idx = scores.idxmax()
            top_company = str(yr.loc[top_idx, "company_name"])
            top_score = round(float(scores.loc[top_idx]), 4)
        else:
            top_company = "N/A"
            top_score = None

        # 曝險最大產業
        if industry_col:
            ind = yr.groupby(industry_col)["credit_exposure"].sum().sort_values(ascending=False)
            largest_industry = str(ind.index[0]) if len(ind) > 0 else "N/A"
            largest_amount = float(ind.iloc[0]) if len(ind) > 0 else 0.0
        else:
            largest_industry = "N/A"
            largest_amount = 0.0

        rows.append({
            "review_year": int(year),
            "total_companies": int(total_companies),
            "total_credit_exposure": round(total_exposure, 2),
            "high_risk_companies": int(hr_companies),
            "high_risk_exposure": round(hr_exposure, 2),
            "high_risk_exposure_pct": round(hr_pct, 4),
            "deteriorating_companies": len(deter_in_year),
            "deteriorating_tickers": "; ".join(sorted(deter_in_year)) or "None",
            "top_risk_company": top_company,
            "top_risk_score": top_score,
            "largest_exposure_industry": largest_industry,
            "largest_exposure_amount": round(largest_amount, 2),
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# 6. 入口
# ─────────────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("Executive Summary Generator")
    logger.info("=" * 50)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        summary = generate_summary(OUTPUTS_DIR)
        out_path = OUTPUTS_DIR / "executive_summary.csv"
        summary.to_csv(out_path, index=False, encoding="utf-8-sig")

        logger.info(f"✅ 已儲存:{out_path}")
        logger.info(f"   涵蓋年度:{summary['review_year'].tolist()}")
        if len(summary) > 0:
            latest = summary.iloc[-1]
            logger.info(
                f"   最新年度({latest['review_year']}):"
                f"高風險 {latest['high_risk_companies']} 家 / 惡化 {latest['deteriorating_companies']} 家"
            )

        print("\n[Executive Summary 預覽]")
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 140)
        print(summary.to_string(index=False))

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 未預期錯誤:{e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
