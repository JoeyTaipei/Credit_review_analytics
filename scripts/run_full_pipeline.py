# =============================================================================
# scripts/run_full_pipeline.py  (REFINED v2)
# Master Pipeline Orchestrator – Windows + PowerShell + Cursor friendly
# =============================================================================
# 【核心改變】
# 不再用 from xxx import main(假設不到的函數名稱),改用兩種策略:
#
# 1. 使用者既有的 scripts → 用 subprocess 呼叫(只要該檔有 if __name__ == "__main__")
# 2. 中間整合步驟(dashboard CSV)→ inline 寫在這個檔,減少依賴
# 3. 新的 generators(executive_summary / case_study)→ 也用 subprocess
#
# 【優點】
# - 不需要知道使用者 module 的內部函數名稱
# - 任何一步失敗只印 warning,不會讓整個 pipeline crash
# - PostgreSQL 失敗不影響 CSV 輸出
# - 在 Windows + PowerShell 上用 sys.executable 確保 Python 路徑正確
#
# 【執行方式】
#   python scripts/run_full_pipeline.py
#   python scripts/run_full_pipeline.py --skip-db
#   python scripts/run_full_pipeline.py --skip-existing  # 略過 user 既有 scripts
# =============================================================================

import sys
import time
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

# ── 路徑設定 ─────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SRC_DIR = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))

# ── 日誌 ─────────────────────────────────────
log_file = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("pipeline")


# ─────────────────────────────────────────────
# 1. 步驟結果記錄
# ─────────────────────────────────────────────
class StepResult:
    def __init__(self, name, success, duration, note=""):
        self.name = name
        self.success = success
        self.duration = duration
        self.note = note

    def __str__(self):
        icon = "✅" if self.success else "⚠️"
        extra = f" — {self.note}" if self.note else ""
        return f"{icon} {self.name} ({self.duration:.1f}s){extra}"


# ─────────────────────────────────────────────
# 2. Subprocess 執行器(關鍵:跨平台 Python 路徑)
# ─────────────────────────────────────────────
def run_script_subprocess(script_path: Path, step_name: str, optional: bool = False) -> StepResult:
    """
    用 subprocess 執行一個 Python script。
    - sys.executable 確保用同一個 Python(Windows 上避免 'python' vs 'py' 問題)
    - cwd 設為 PROJECT_ROOT,確保相對路徑正確
    - capture_output=False,讓使用者即時看到子進程輸出
    """
    start = time.time()

    if not script_path.exists():
        if optional:
            logger.warning(f"⏭️  略過 {step_name}:找不到 {script_path.name}(可選)")
            return StepResult(step_name, True, 0, "skipped (not found)")
        else:
            logger.error(f"❌ {step_name}:找不到 {script_path}")
            return StepResult(step_name, False, 0, "file not found")

    logger.info(f"▶️  執行 {step_name}:{script_path.relative_to(PROJECT_ROOT)}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            check=False,  # 不要 raise,我們自己處理
            text=True,
        )
        duration = time.time() - start

        if result.returncode == 0:
            logger.info(f"✅ {step_name} 完成({duration:.1f}s)")
            return StepResult(step_name, True, duration)
        else:
            logger.warning(f"⚠️  {step_name} 退出碼 {result.returncode}({duration:.1f}s)")
            return StepResult(step_name, False, duration, f"exit code {result.returncode}")

    except Exception as e:
        duration = time.time() - start
        logger.error(f"❌ {step_name} 例外:{e}")
        return StepResult(step_name, False, duration, str(e))


# ─────────────────────────────────────────────
# 3. Inline:Build dashboard_credit_review.csv
#    (合併 risk_flags + ratios_wide + anomalies + credit_actions)
# ─────────────────────────────────────────────
def build_dashboard_csv() -> StepResult:
    """直接讀現有 CSV 合併,不依賴外部 module"""
    step_name = "Build dashboard_credit_review.csv"
    start = time.time()
    logger.info(f"▶️  {step_name}")

    risk_flags_path = OUTPUTS_DIR / "risk_flags.csv"
    if not risk_flags_path.exists():
        logger.warning(f"⚠️  找不到 risk_flags.csv,跳過 dashboard 合併")
        return StepResult(step_name, False, time.time() - start, "no risk_flags.csv")

    try:
        # ── 讀主表 ──
        df = pd.read_csv(risk_flags_path)
        df = _normalize_keys(df)
        logger.info(f"   主表 risk_flags:{len(df)} 筆")

        # ── 合併 ratios_wide ──
        ratios_path = OUTPUTS_DIR / "ratios_wide.csv"
        if ratios_path.exists():
            ratios = _normalize_keys(pd.read_csv(ratios_path))
            new_cols = [c for c in ratios.columns if c not in df.columns or c in ["ticker", "year"]]
            df = df.merge(ratios[new_cols], on=["ticker", "year"], how="left")
            logger.info(f"   合併 ratios_wide ✓")

        # ── 合併 anomalies ──
        anom_path = OUTPUTS_DIR / "anomalies.csv"
        if anom_path.exists():
            anom = _normalize_keys(pd.read_csv(anom_path))
            new_cols = [c for c in anom.columns if c not in df.columns or c in ["ticker", "year"]]
            df = df.merge(anom[new_cols], on=["ticker", "year"], how="left")
            logger.info(f"   合併 anomalies ✓")

        # ── 加入 credit_actions ──
        try:
            from src.credit_actions import assign_credit_actions
            df = assign_credit_actions(df)
            logger.info(f"   附加 credit_actions ✓")
        except Exception as e:
            logger.warning(f"   credit_actions 失敗:{e},以 placeholder 替代")
            for c, v in [("suggested_action", "Pending"),
                         ("action_reason", "N/A"),
                         ("review_priority", "N/A")]:
                if c not in df.columns:
                    df[c] = v

        # ── 補齊關鍵欄位 ──
        df = _ensure_essential_columns(df)

        # ── 寫出 ──
        out_path = OUTPUTS_DIR / "dashboard_credit_review.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        duration = time.time() - start
        logger.info(f"✅ {step_name} 完成 → {out_path.name}({len(df)} 筆,{duration:.1f}s)")
        return StepResult(step_name, True, duration)

    except Exception as e:
        duration = time.time() - start
        logger.error(f"❌ {step_name} 失敗:{e}", exc_info=True)
        return StepResult(step_name, False, duration, str(e))


def _normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    """統一 ticker / year 型別"""
    df = df.copy()
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df.dropna(subset=["year"])
        df["year"] = df["year"].astype(int)
    return df


def _ensure_essential_columns(df: pd.DataFrame) -> pd.DataFrame:
    """補齊 dashboard 必要欄位"""
    df = df.copy()

    # credit_exposure
    if "credit_exposure" not in df.columns or df["credit_exposure"].isna().all():
        if "total_assets" in df.columns:
            df["credit_exposure"] = pd.to_numeric(df["total_assets"], errors="coerce") * 0.3
            logger.info("   credit_exposure ← total_assets × 0.3")
        else:
            np.random.seed(42)
            df["credit_exposure"] = np.random.uniform(3000, 20000, len(df)).round(0)
            logger.warning("   credit_exposure 為模擬值(隨機)")

    # company_name
    if "company_name" not in df.columns:
        df["company_name"] = df.get("ticker", "Unknown")

    # industry_zh
    if "industry_zh" not in df.columns:
        df["industry_zh"] = df.get("industry", "未知產業")

    return df


# ─────────────────────────────────────────────
# 4. PostgreSQL(可選 / 失敗不 crash)
# ─────────────────────────────────────────────
def write_to_postgres_safe(skip_db: bool) -> StepResult:
    step_name = "PostgreSQL Write"
    start = time.time()

    if skip_db:
        logger.info(f"⏭️  {step_name}:--skip-db 模式")
        return StepResult(step_name, True, 0, "skipped by user")

    # 嘗試找你既有的 DB 寫入腳本
    candidates = [
        SCRIPTS_DIR / "write_to_db.py",
        SCRIPTS_DIR / "load_to_postgres.py",
        SCRIPTS_DIR / "data_pipeline.py",  # 若 DB 寫入在這個檔內
    ]
    for path in candidates:
        if path.exists():
            try:
                logger.info(f"▶️  {step_name}:{path.name}")
                result = subprocess.run(
                    [sys.executable, str(path)],
                    cwd=str(PROJECT_ROOT),
                    timeout=60,
                    text=True,
                    check=False,
                )
                duration = time.time() - start
                if result.returncode == 0:
                    return StepResult(step_name, True, duration)
                else:
                    logger.warning(
                        f"⚠️  PostgreSQL 失敗(不影響 CSV 輸出),"
                        f"退出碼 {result.returncode}。"
                        f"請確認 docker-compose up -d 已啟動。"
                    )
                    return StepResult(step_name, False, duration, "DB unreachable")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️  PostgreSQL 連線超時,跳過")
                return StepResult(step_name, False, time.time() - start, "timeout")
            except Exception as e:
                logger.warning(f"⚠️  PostgreSQL 失敗:{e}")
                return StepResult(step_name, False, time.time() - start, str(e))

    logger.info(f"⏭️  {step_name}:找不到 DB 寫入腳本,跳過")
    return StepResult(step_name, True, 0, "no script found")


# ─────────────────────────────────────────────
# 5. 主 Pipeline
# ─────────────────────────────────────────────
def run_pipeline(skip_db: bool = False, skip_existing: bool = False):
    pipeline_start = time.time()
    results = []

    logger.info("=" * 60)
    logger.info("🏦 Credit Review Full Pipeline")
    logger.info(f"   時間:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   輸出目錄:{OUTPUTS_DIR}")
    logger.info("=" * 60)

    # ─── Stage A:既有 scripts(產生 raw / ratios / risk_flags / anomalies)───
    # 這些檔案如果已經存在於 outputs/ 且 --skip-existing 模式,就跳過
    existing_scripts = [
        ("Generate Sample Data", SCRIPTS_DIR / "generate_sample_data.py", "financials_raw.csv"),
        ("Data Pipeline / Schema Validation", SCRIPTS_DIR / "data_pipeline.py", None),
        ("Financial Ratios", SRC_DIR / "financial_ratios.py", "ratios_wide.csv"),
        ("Feature Engineering", SRC_DIR / "feature_engineering.py", None),
        ("Anomaly Detection", SRC_DIR / "anomaly_detection.py", "anomalies.csv"),
        ("Risk Flags & Scoring", SRC_DIR / "risk_flags.py", "risk_flags.csv"),
    ]

    if skip_existing:
        logger.info("⏭️  --skip-existing 模式:跳過既有 scripts,直接整合現有 CSV")
    else:
        for name, path, expected_csv in existing_scripts:
            # 若 expected CSV 已存在,可選擇跳過(加速重複執行)
            if expected_csv and (OUTPUTS_DIR / expected_csv).exists():
                logger.info(f"📦 {expected_csv} 已存在,但仍重新執行 {name}(確保資料一致)")
            results.append(run_script_subprocess(path, name, optional=True))

    # ─── Stage B:整合 dashboard CSV ───
    results.append(build_dashboard_csv())

    # ─── Stage C:Executive Summary ───
    results.append(run_script_subprocess(
        SCRIPTS_DIR / "generate_executive_summary.py",
        "Executive Summary",
    ))

    # ─── Stage D:Case Study ───
    results.append(run_script_subprocess(
        SCRIPTS_DIR / "generate_case_study.py",
        "Case Study",
    ))

    # ─── Stage E:PostgreSQL(可選)───
    results.append(write_to_postgres_safe(skip_db))

    # ─── 摘要 ───
    print_summary(results, time.time() - pipeline_start)


# ─────────────────────────────────────────────
# 6. 摘要報告
# ─────────────────────────────────────────────
def print_summary(results: list, total_duration: float):
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    print("\n" + "=" * 60)
    print("📋 PIPELINE EXECUTION SUMMARY")
    print("=" * 60)
    for r in results:
        print(f"  {r}")
    print(f"\n  總步驟:{len(results)} | ✅ 成功 {success} | ⚠️ 失敗 {failed}")
    print(f"  總耗時:{total_duration:.1f} 秒")
    print("=" * 60)

    # 列出輸出檔
    print("\n📂 輸出檔案清單:")
    expected_files = [
        "financials_raw.csv",
        "ratios_wide.csv",
        "ratios_long.csv",
        "risk_flags.csv",
        "anomalies.csv",
        "dashboard_credit_review.csv",
        "executive_summary.csv",
        "company_case_study.md",
    ]
    for fname in expected_files:
        fpath = OUTPUTS_DIR / fname
        if fpath.exists():
            size_kb = fpath.stat().st_size / 1024
            print(f"  ✅ {fname:40s} ({size_kb:7.1f} KB)")
        else:
            print(f"  ❌ {fname:40s} (未產生)")

    print(f"\n📝 執行日誌:{log_file}")

    if failed > 0:
        print(f"\n⚠️  有 {failed} 個步驟失敗,但成功的 CSV 仍然可用。")
        print("    可單獨重跑:python scripts/<該步驟>.py")


# ─────────────────────────────────────────────
# 7. CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Credit Review Full Pipeline (Windows / PowerShell friendly)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  python scripts/run_full_pipeline.py
  python scripts/run_full_pipeline.py --skip-db
  python scripts/run_full_pipeline.py --skip-existing  # 只重跑新的 generator
""",
    )
    parser.add_argument("--skip-db", action="store_true", help="跳過 PostgreSQL 步驟")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳過既有 scripts(假設 raw / ratios / risk_flags 已產生)")
    args = parser.parse_args()

    run_pipeline(skip_db=args.skip_db, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
