# =============================================================================
# scripts/generate_case_study.py  (REFINED)
# Deloitte-Style One-Page Credit Review Case Study Generator
# =============================================================================
# 【主要修正】
# - credit_actions import 失敗時不 crash,使用內建 fallback
# - 把 PROJECT_ROOT 加到 sys.path 確保 src/ 能被找到(Cursor / PowerShell 友善)
# - 全部欄位用 row.get() 安全存取
# - Markdown 輸出用 lf 換行,Windows / Mac 都正常
# =============================================================================

import pandas as pd
import numpy as np
import logging
import argparse
from pathlib import Path
from datetime import datetime
import sys

# ── 路徑設定(關鍵:讓 src/ 能被找到) ─────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. 安全 import credit_actions(失敗也能跑)
# ─────────────────────────────────────────────
def safe_assign_credit_actions(df):
    """嘗試 import,失敗則回傳原 df 並補 placeholder 欄位"""
    try:
        from src.credit_actions import assign_credit_actions
        return assign_credit_actions(df)
    except Exception as e:
        logger.warning(f"無法載入 credit_actions ({e}),使用 placeholder")
        df = df.copy()
        for col, default in [
            ("suggested_action", "Pending Review"),
            ("action_reason", "請參考風險驅動因子。"),
            ("review_priority", "待確認"),
        ]:
            if col not in df.columns:
                df[col] = default
        return df


# ─────────────────────────────────────────────
# 2. 載入 + 標的選擇
# ─────────────────────────────────────────────
def load_data(outputs_dir: Path) -> pd.DataFrame:
    candidates = [
        outputs_dir / "dashboard_credit_review.csv",
        outputs_dir / "risk_flags.csv",
    ]
    for p in candidates:
        if p.exists():
            logger.info(f"載入 {p.name}")
            df = pd.read_csv(p)
            if "ticker" in df.columns:
                df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
            if "year" in df.columns:
                df["year"] = pd.to_numeric(df["year"], errors="coerce")
                df = df.dropna(subset=["year"])
                df["year"] = df["year"].astype(int)
            return df
    raise FileNotFoundError("找不到輸入資料,請先執行 run_full_pipeline.py")


def pick_target(df: pd.DataFrame, ticker: str = None, year: int = None):
    """選定分析公司:指定 ticker 優先,否則挑最新年度的最高風險"""
    if year is None:
        year = int(df["year"].max())

    yr_df = df[df["year"] == year]
    if len(yr_df) == 0:
        raise ValueError(f"年度 {year} 沒有資料")

    if ticker:
        ticker = ticker.upper().strip()
        match = yr_df[yr_df["ticker"] == ticker]
        if len(match) == 0:
            raise ValueError(f"找不到 {ticker}({year})")
        row = match.iloc[0]
    else:
        score_col = next(
            (c for c in ["combined_score", "risk_score", "anomaly_score"]
             if c in yr_df.columns and not yr_df[c].isna().all()),
            None
        )
        if score_col:
            scores = pd.to_numeric(yr_df[score_col], errors="coerce")
            row = yr_df.loc[scores.idxmax()]
        else:
            row = yr_df.iloc[0]
        ticker = str(row["ticker"])

    logger.info(f"分析目標:{ticker}({year} 年)")
    return ticker, year, row


# ─────────────────────────────────────────────
# 3. 風險驅動因子識別
# ─────────────────────────────────────────────
def identify_drivers(row: pd.Series) -> list:
    """從財務數據自動識別 Key Risk Drivers,回傳 [(name, value, severity, desc)]"""
    drivers = []

    z = row.get("altman_z_prime")
    if pd.notna(z):
        if z < 1.23:
            drivers.append(("Altman Z' Score", f"{z:.2f}", "🔴",
                            "低於危險門檻 1.23,財務危機信號強烈"))
        elif z < 2.90:
            drivers.append(("Altman Z' Score", f"{z:.2f}", "🟡",
                            "處於灰色地帶(1.23–2.90),需密切觀察"))
        else:
            drivers.append(("Altman Z' Score", f"{z:.2f}", "🟢",
                            "高於安全門檻 2.90"))

    dr = row.get("debt_ratio")
    if pd.notna(dr):
        if dr > 0.80:
            drivers.append(("Debt Ratio(負債比率)", f"{dr:.1%}", "🔴",
                            "超高槓桿,償債壓力極大"))
        elif dr > 0.65:
            drivers.append(("Debt Ratio(負債比率)", f"{dr:.1%}", "🟡",
                            "槓桿偏高,需留意再融資風險"))

    ic = row.get("interest_coverage")
    if pd.notna(ic):
        if ic < 1.0:
            drivers.append(("Interest Coverage(利息保障倍數)", f"{ic:.2f}x", "🔴",
                            "利息保障不足 1 倍,存在違約風險"))
        elif ic < 2.0:
            drivers.append(("Interest Coverage(利息保障倍數)", f"{ic:.2f}x", "🟡",
                            "利息保障偏低,盈利緩衝不足"))

    cr = row.get("current_ratio")
    if pd.notna(cr):
        if cr < 1.0:
            drivers.append(("Current Ratio(流動比率)", f"{cr:.2f}", "🔴",
                            "流動性不足,短期償債能力堪憂"))
        elif cr < 1.5:
            drivers.append(("Current Ratio(流動比率)", f"{cr:.2f}", "🟡",
                            "流動性稍緊,需監控短期現金流"))

    ry = row.get("revenue_yoy")
    if pd.notna(ry):
        if ry < -0.10:
            drivers.append(("Revenue Growth(營收成長率)", f"{ry:.1%}", "🔴",
                            "營收年減超過 10%,業務明顯萎縮"))
        elif ry < -0.03:
            drivers.append(("Revenue Growth(營收成長率)", f"{ry:.1%}", "🟡",
                            "營收微幅下滑,需追蹤業務趨勢"))

    py_ = row.get("profit_yoy")
    if pd.notna(py_) and py_ < -0.15:
        drivers.append(("Profit Growth(淨利成長率)", f"{py_:.1%}", "🔴",
                        "獲利大幅衰退,盈利品質惡化"))

    fc = row.get("flag_count")
    if pd.notna(fc):
        if fc >= 4:
            drivers.append(("Risk Flags(風險旗標數)", f"{int(fc)} 項", "🔴",
                            "多項規則旗標同時觸發"))
        elif fc >= 2:
            drivers.append(("Risk Flags(風險旗標數)", f"{int(fc)} 項", "🟡",
                            "部分規則旗標觸發"))

    roa = row.get("roa")
    if pd.notna(roa) and roa < 0:
        drivers.append(("ROA(資產報酬率)", f"{roa:.2%}", "🔴",
                        "資產報酬率為負"))

    if not drivers:
        cs = row.get("combined_score", "N/A")
        drivers.append(("綜合風險評分", str(cs), "🟡",
                        "未現單一極度危險指標,但綜合評分偏高"))

    return drivers


# ─────────────────────────────────────────────
# 4. 5 年趨勢表
# ─────────────────────────────────────────────
def build_trend_table(df: pd.DataFrame, ticker: str) -> str:
    company_df = df[df["ticker"] == ticker].sort_values("year")
    if len(company_df) == 0:
        return "_(無趨勢資料)_"

    cols_map = {
        "year": "年度",
        "combined_score": "綜合風險分",
        "altman_z_prime": "Altman Z'",
        "debt_ratio": "負債比率",
        "interest_coverage": "利息保障倍數",
        "revenue_yoy": "營收 YoY",
        "final_risk_level": "風險等級",
    }
    available = {k: v for k, v in cols_map.items() if k in company_df.columns}
    if not available:
        return "_(資料欄位不足)_"

    disp = company_df[list(available.keys())].copy()
    disp = disp.rename(columns=available)

    # 格式化
    for col in disp.columns:
        if col in ["負債比率", "營收 YoY"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        elif col in ["綜合風險分", "Altman Z'"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "N/A")
        elif col == "利息保障倍數":
            disp[col] = disp[col].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")

    header = "| " + " | ".join(disp.columns) + " |"
    sep = "|" + "|".join(["---"] * len(disp.columns)) + "|"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in disp.values]
    return "\n".join([header, sep] + rows)


# ─────────────────────────────────────────────
# 5. Markdown 輸出
# ─────────────────────────────────────────────
def render_markdown(df: pd.DataFrame, ticker: str, year: int, row: pd.Series) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    company_name = str(row.get("company_name", ticker))
    industry = str(row.get("industry_zh") or row.get("broad_industry_zh") or row.get("industry") or "N/A")

    risk_level = str(row.get("final_risk_level", "N/A")).upper()
    risk_score = row.get("combined_score", row.get("risk_score"))
    exposure = row.get("credit_exposure")
    flag_count = row.get("flag_count")
    suggested_action = str(row.get("suggested_action", "待授信委員會決議"))
    action_reason = str(row.get("action_reason", ""))
    review_priority = str(row.get("review_priority", "N/A"))

    risk_emoji = {
        "CRITICAL": "🔴 **緊急(Critical)**",
        "HIGH": "🟠 **高風險(High)**",
        "MEDIUM": "🟡 **中風險(Medium)**",
        "LOW": "🟢 **低風險(Low)**",
    }.get(risk_level, f"⚪ {risk_level}")

    drivers = identify_drivers(row)
    trend_table = build_trend_table(df, ticker)

    # Markdown 模板
    md_parts = [
        "# 📋 授信覆審個案報告(Credit Review Case Study)",
        "",
        "---",
        "",
        "> **⚠️ Disclaimer**",
        "> 本報告由 AI-Assisted Credit Review Tool 自動生成,基於模擬財務資料。",
        "> 系統提供 **decision support**,**非自動核貸**(not automated loan approval)。",
        "> 最終授信決策仍須由核貸專員 / 授信委員會人工審核(Human-in-the-Loop)。",
        "",
        "---",
        "",
        "## 一、公司概況(Company Overview)",
        "",
        "| 欄位 | 內容 |",
        "|---|---|",
        f"| **公司代號(Ticker)** | `{ticker}` |",
        f"| **公司名稱** | {company_name} |",
        f"| **所屬產業** | {industry} |",
        f"| **覆審年度** | {year} 年 |",
        f"| **報告產生時間** | {now} |",
        f"| **工具版本** | Credit Review Tool v1.0 (Demo) |",
        "",
        "---",
        "",
        "## 二、當前風險等級(Current Risk Level)",
        "",
        risk_emoji,
        "",
        "| 指標 | 數值 |",
        "|---|---|",
        f"| 綜合風險評分(Combined Score)| {f'{risk_score:.4f}' if pd.notna(risk_score) else 'N/A'} |",
        f"| 授信曝險(Credit Exposure)| {f'NT$ {exposure:,.0f} 千元' if pd.notna(exposure) else 'N/A'} |",
        f"| 風險旗標數(Flag Count)| {f'{int(flag_count)} 項' if pd.notna(flag_count) else 'N/A'} |",
        "",
        "---",
        "",
        "## 三、主要風險驅動因子(Key Risk Drivers)",
        "",
        "以下指標由系統自動識別,依嚴重程度排序:",
        "",
        "| 財務指標 | 數值 | 嚴重度 | 說明 |",
        "|---|---|---|---|",
    ]
    for name, value, sev, desc in drivers:
        md_parts.append(f"| {name} | {value} | {sev} | {desc} |")

    md_parts += [
        "",
        "---",
        "",
        "## 四、五年風險趨勢(5-Year Risk Trend)",
        "",
        trend_table,
        "",
        "> 📈 趨勢說明:綜合風險分越高代表風險越大(0–1)。Altman Z' 越低代表財務危機可能性越高。",
        "",
        "---",
        "",
        "## 五、授信曝險分析(Credit Exposure Analysis)",
        "",
    ]

    # 曝險占比
    if "credit_exposure" in df.columns and pd.notna(exposure):
        yr_df = df[df["year"] == year]
        total_exp = float(pd.to_numeric(yr_df["credit_exposure"], errors="coerce").fillna(0).sum())
        company_exp = float(exposure)
        pct = company_exp / total_exp if total_exp > 0 else 0
        md_parts += [
            "| 項目 | 數值 |",
            "|---|---|",
            f"| 本公司授信曝險 | NT$ {company_exp:,.0f} 千元 |",
            f"| 全 Portfolio 總曝險 | NT$ {total_exp:,.0f} 千元 |",
            f"| 占 Portfolio 比重 | {pct:.1%} |",
            "",
        ]
    else:
        md_parts.append("_(曝險資料不足)_")
        md_parts.append("")

    md_parts += [
        "---",
        "",
        "## 六、建議授信行動(Suggested Credit Action)",
        "",
        "> 🤖 以下建議由 AI 自動生成,**僅供參考**,最終決策須由人工審核。",
        "",
        f"**建議行動:** {suggested_action}",
        "",
        f"**行動依據:** {action_reason if action_reason else '請參考第三節風險驅動因子。'}",
        "",
        f"**行動優先級:** {review_priority}",
        "",
        "### 建議後續步驟",
        "",
        "1. 要求該公司提交最新一季財務報表及銀行對帳單",
        "2. 評估擔保品現值是否足以覆蓋剩餘授信金額",
        "3. 安排授信專員進行現場訪查(Site Visit)",
        "4. 若評分下一年度仍未改善,提報授信委員會",
        "",
        "---",
        "",
        "## 七、分析師附記(Analyst Comment)",
        "",
        "> 💡 以下文字由 AI 自動生成,僅作為覆審起點,需由資深分析師確認。",
        "",
    ]

    # 自動分析師附記
    notes = []
    z = row.get("altman_z_prime")
    dr = row.get("debt_ratio")
    ic = row.get("interest_coverage")
    ry = row.get("revenue_yoy")

    if pd.notna(z) and z < 1.23:
        notes.append(f"Altman Z' = {z:.2f},進入財務危機危險區(< 1.23),建議列為優先覆審標的。")
    if pd.notna(dr) and dr > 0.75:
        notes.append(f"負債比率達 {dr:.1%},槓桿水準偏高,需評估再融資風險。")
    if pd.notna(ic) and ic < 1.5:
        notes.append(f"利息保障倍數僅 {ic:.2f}x,本業獲利勉強應付利息支出,財務彈性不足。")
    if pd.notna(ry) and ry < -0.08:
        notes.append(f"過去一年營收年減 {abs(ry):.1%},需確認是否為行業性衰退。")

    if not notes:
        notes.append("整體財務指標未現單一極度危險信號,但多項指標同步偏弱,建議加強追蹤並要求定期財報揭露。")

    for n in notes:
        md_parts.append(f"- {n}")

    md_parts += [
        "",
        "---",
        "",
        "## 附錄:方法論說明",
        "",
        "- **Altman Z' Score**:適用私人企業之修正版,危險區 < 1.23,灰色區 1.23–2.90",
        "- **綜合風險評分**:規則旗標分(60%)+ 異常偵測分(40%)加權",
        "- **風險等級**:low / medium / high / critical 四段",
        "- **本工具定位**:AI-Assisted Decision Support,非 Automated Loan Approval",
        "- **資料來源**:本 Demo 使用模擬財務資料(Synthetic Data)",
        "",
        "---",
        "",
        f"*報告產生時間:{now} | 工具版本:Credit Review Tool v1.0 (Demo)*",
        "",
    ]

    return "\n".join(md_parts)


# ─────────────────────────────────────────────
# 6. 入口
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default=None)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Case Study Generator")
    logger.info("=" * 50)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        df = load_data(OUTPUTS_DIR)

        # 補充 credit_actions 欄位(若缺)
        if "suggested_action" not in df.columns:
            df = safe_assign_credit_actions(df)

        ticker, year, row = pick_target(df, args.ticker, args.year)
        md = render_markdown(df, ticker, year, row)

        out_path = OUTPUTS_DIR / "company_case_study.md"
        out_path.write_text(md, encoding="utf-8", newline="\n")

        logger.info(f"✅ 已儲存:{out_path}")
        logger.info(f"   公司:{ticker} | 年度:{year}")
        logger.info(f"   風險等級:{row.get('final_risk_level', 'N/A')}")

    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 未預期錯誤:{e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
