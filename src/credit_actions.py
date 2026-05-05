# =============================================================================
# src/credit_actions.py  (REFINED)
# AI-Assisted Credit Review Tool – Credit Action Recommendation Engine
# =============================================================================
# 【定位】
# AI-assisted decision support, NOT automated loan approval.
# 系統提供建議,最終決策仍由核貸專員審核。
#
# 【主要修正】
# - 修掉 pd.cut fallback 的 length mismatch bug
# - 全部欄位用 df.get() 安全存取,避免 KeyError
# - 統一 final_risk_level 標準化邏輯
# - 加入空 DataFrame 防呆
# =============================================================================

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 1. Risk Level → Action Mapping
# ─────────────────────────────────────────────
ACTION_MAPPING = {
    "low": {
        "suggested_action": "Maintain Credit Line / Annual Review",
        "action_reason_base": "財務指標穩健,維持現行授信額度,按年度例行覆審。",
        "review_priority": "低 (Low)",
    },
    "medium": {
        "suggested_action": "Enhanced Monitoring / Request Updated Financials",
        "action_reason_base": "部分財務指標出現惡化跡象,建議加強追蹤並要求最新財報。",
        "review_priority": "中 (Medium)",
    },
    "high": {
        "suggested_action": "Reduce Exposure or Request Additional Collateral",
        "action_reason_base": "多項風險旗標觸發,財務狀況明顯惡化,建議縮減授信規模或要求追加擔保品。",
        "review_priority": "高 (High) — 優先處理",
    },
    "critical": {
        "suggested_action": "Escalate to Credit Committee — Immediate Action Required",
        "action_reason_base": "財務危機信號明顯,建議立即提報授信委員會並暫停新增授信。",
        "review_priority": "緊急 (Critical) — 立即處理",
    },
}

VALID_LEVELS = set(ACTION_MAPPING.keys())


# ─────────────────────────────────────────────
# 2. 工具函數:從 combined_score 推 final_risk_level
# ─────────────────────────────────────────────
def _score_to_level(score) -> str:
    """單一數值轉為 risk level,完全防 NaN"""
    if pd.isna(score):
        return "medium"
    if score < 0.25:
        return "low"
    elif score < 0.50:
        return "medium"
    elif score < 0.75:
        return "high"
    else:
        return "critical"


def _normalize_level(value) -> str:
    """標準化 risk level 字串,任何輸入都回傳合法值"""
    if pd.isna(value):
        return "medium"
    s = str(value).lower().strip()
    if s in VALID_LEVELS:
        return s
    # 中文相容
    zh_map = {"低": "low", "中": "medium", "高": "high",
              "高風險": "high", "警示": "critical", "緊急": "critical"}
    return zh_map.get(s, "medium")


# ─────────────────────────────────────────────
# 3. 動態 action_reason 生成器
# ─────────────────────────────────────────────
def _build_detailed_reason(row: pd.Series) -> str:
    """根據實際財務指標補充 action_reason 細節"""
    level = _normalize_level(row.get("final_risk_level"))
    base = ACTION_MAPPING[level]["action_reason_base"]
    reasons = []

    z = row.get("altman_z_prime")
    if pd.notna(z):
        if z < 1.23:
            reasons.append(f"Altman Z' = {z:.2f}(低於危險門檻 1.23)")
        elif z < 2.90:
            reasons.append(f"Altman Z' = {z:.2f}(灰色地帶)")

    dr = row.get("debt_ratio")
    if pd.notna(dr) and dr > 0.70:
        reasons.append(f"負債比率偏高 ({dr:.1%})")

    ic = row.get("interest_coverage")
    if pd.notna(ic) and ic < 1.5:
        reasons.append(f"利息保障倍數不足 ({ic:.2f}x)")

    ry = row.get("revenue_yoy")
    if pd.notna(ry) and ry < -0.05:
        reasons.append(f"營收年增率下滑 ({ry:.1%})")

    fc = row.get("flag_count")
    if pd.notna(fc) and fc >= 3:
        reasons.append(f"觸發 {int(fc)} 項風險旗標")

    if reasons:
        return base + " 主要驅動因子:" + "、".join(reasons) + "。"
    return base


# ─────────────────────────────────────────────
# 4. 主函數
# ─────────────────────────────────────────────
def assign_credit_actions(df: pd.DataFrame) -> pd.DataFrame:
    """
    輸入:含 final_risk_level 或 combined_score 的 DataFrame
    輸出:加入 suggested_action / action_reason / review_priority 三欄
    """
    if df is None or len(df) == 0:
        logger.warning("assign_credit_actions 收到空 DataFrame")
        return df

    df = df.copy()

    # 確保 final_risk_level 存在且合法
    if "final_risk_level" not in df.columns:
        if "combined_score" in df.columns:
            logger.info("由 combined_score 推算 final_risk_level")
            df["final_risk_level"] = df["combined_score"].apply(_score_to_level)
        else:
            logger.warning("缺 final_risk_level 與 combined_score,全部設為 medium")
            df["final_risk_level"] = "medium"
    else:
        df["final_risk_level"] = df["final_risk_level"].apply(_normalize_level)

    # 套 mapping
    df["suggested_action"] = df["final_risk_level"].map(
        {k: v["suggested_action"] for k, v in ACTION_MAPPING.items()}
    )
    df["review_priority"] = df["final_risk_level"].map(
        {k: v["review_priority"] for k, v in ACTION_MAPPING.items()}
    )
    df["action_reason"] = df.apply(_build_detailed_reason, axis=1)

    # 統計
    counts = df["final_risk_level"].value_counts().to_dict()
    logger.info(f"credit_actions 完成:{len(df)} 筆 | {counts}")

    return df


# ─────────────────────────────────────────────
# 5. 自我測試
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    test_df = pd.DataFrame({
        "ticker": ["AAA", "BBB", "CCC", "DDD"],
        "year": [2024] * 4,
        "final_risk_level": ["low", "medium", "high", "critical"],
        "combined_score": [0.1, 0.4, 0.7, 0.9],
        "altman_z_prime": [4.5, 2.1, 1.0, 0.5],
        "debt_ratio": [0.3, 0.55, 0.75, 0.88],
        "interest_coverage": [8.0, 3.0, 1.2, 0.4],
        "revenue_yoy": [0.05, -0.02, -0.12, -0.25],
        "flag_count": [0, 1, 3, 5],
    })

    result = assign_credit_actions(test_df)
    print("\n[測試 1] 正常輸入")
    print(result[["ticker", "final_risk_level", "review_priority"]].to_string(index=False))

    # 測試 2:缺 final_risk_level,只有 combined_score
    test2 = test_df.drop(columns=["final_risk_level"])
    result2 = assign_credit_actions(test2)
    print("\n[測試 2] 只有 combined_score")
    print(result2[["ticker", "final_risk_level"]].to_string(index=False))

    # 測試 3:都缺
    test3 = test_df.drop(columns=["final_risk_level", "combined_score"])
    result3 = assign_credit_actions(test3)
    print("\n[測試 3] 兩個欄位都缺")
    print(result3[["ticker", "final_risk_level"]].to_string(index=False))

    print("\n[測試 4] action_reason 範例")
    for _, r in result.iterrows():
        print(f"  {r['ticker']}: {r['action_reason']}")
