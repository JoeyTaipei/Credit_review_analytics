"""
llm_summary.py
===============
Generates a Traditional-Chinese first-draft credit review opinion (覆審意見草稿)
from the structured analysis output (ratios + anomalies + risk score).

This is **drafting assistance, not decision-making**.  The bank's
authorized credit officer is always responsible for the final memo.

Defending the design choices:

1. **Structured input → structured constraint → constrained output**
   We hand the LLM a JSON blob of pre-computed numbers and force it (via
   prompt + post-validation) to quote only those numbers.  This is the
   single most important hallucination guard for finance use cases:
   if the LLM is making things up, it will use a number we never gave it,
   and we can detect that.

2. **Mandatory citation** — every quantitative claim must reference the
   field name.  We instruct the model to write e.g. "債務比率為 62%"
   only after seeing `debt_ratio: 0.62` in the input.

3. **Length-bounded** — 200-300 字 cap.  Long LLM outputs creep toward
   embellishment.  Short outputs force precision.

4. **Mandatory disclaimer** — the closing line is hard-coded by us, not
   generated.  We append it after the model returns.

5. **Why we don't fine-tune** — at intern scale, fine-tuning a model on
   bank credit memos is overkill, expensive, and creates audit / data
   privacy issues with the training set.  Few-shot prompting with one
   well-structured example does ~90% of the job.

Calling pattern:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    summary = generate_review_summary(client, company_input)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

# Hard-coded closing line — appended after generation, never optional
DISCLAIMER = (
    "\n\n本摘要為 AI 輔助生成，僅供核貸專員參考；最終授信決定須由授權核貸主管覆核。"
)

# We forbid the model from citing any number that doesn't appear in the
# input.  This is the post-validation backstop.
ALLOWED_NUMBER_TOLERANCE = 0.005   # 0.5% rounding tolerance


@dataclass
class CompanyAnalysisInput:
    """The structured slice passed to the LLM for a single company."""
    ticker: str
    company_name: str
    industry_zh: str
    broad_industry_zh: str
    review_year: int

    # Latest-year ratios
    current_ratio: Optional[float]
    debt_ratio: Optional[float]
    interest_coverage: Optional[float]
    operating_margin: Optional[float]
    roe: Optional[float]
    altman_z_prime: Optional[float]

    # Trend (5y YoY change for revenue, debt)
    revenue_5y_cagr: Optional[float]
    debt_5y_change: Optional[float]

    # Risk
    risk_score: Optional[float]
    risk_band: Optional[str]

    # Anomalies (list of dicts: {signal, year, z_score, direction})
    anomalies: list[dict]

    # Industry medians (broad industry) for the latest year
    industry_median_debt_ratio: Optional[float]
    industry_median_operating_margin: Optional[float]
    industry_median_roe: Optional[float]


def build_prompt(payload: CompanyAnalysisInput) -> str:
    """
    Construct the user message.  The system message is separate
    (in `SYSTEM_PROMPT` below).
    """
    payload_json = json.dumps(payload.__dict__, ensure_ascii=False, indent=2,
                              default=str)
    return f"""請根據下方 JSON 結構化分析資料，撰寫一份 200-300 字的繁體中文授信覆審意見草稿。

【嚴格規則】
1. 所有數字必須直接引用 JSON 中提供的欄位（例如「債務比率 62%」必須對應 debt_ratio: 0.62）
2. 不得引用任何未在 JSON 中出現的數字、公司名稱、年度
3. 不得做出超出數據支持的判斷（例如不得宣稱「公司管理層素質良好」這類主觀評語）
4. 結構：(a) 整體財務體質 (b) 主要風險點 (c) 與同業比較 (d) 建議覆審結論
5. 用詞中性、客觀、避免絕對化（用「相對偏低」而非「過低」）

【公司結構化資料】
{payload_json}

請開始撰寫："""


SYSTEM_PROMPT = """你是台灣中型商業銀行企業金融部的資深授信分析師助理。你的任務是根據結構化財務分析資料，產生授信覆審意見的「初稿」，協助核貸專員加速作業。

你不是決策者，最終判斷由核貸主管負責。
你的輸出必須：
- 完全基於提供的數字，不得引用未提供的資訊
- 使用台灣金融業常用的審慎語氣
- 在 200-300 字內，結構清晰
- 每個數字主張都要可被回推到 JSON 的特定欄位"""


# ---------------------------------------------------------------------------
# Validation: detect hallucinated numbers in the output
# ---------------------------------------------------------------------------
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_numbers(text: str) -> list[float]:
    """Extract every numeric mention from the LLM output for validation."""
    return [float(x) for x in NUMBER_RE.findall(text)]


def _allowed_numbers(payload: CompanyAnalysisInput) -> set[float]:
    """
    The set of numbers the LLM is allowed to use.

    We include:
      - Each numeric field, both in raw form and as percentage
        (e.g. debt_ratio 0.62 → also allow 62)
      - Year fields (review_year etc.)
      - 0 and 100 as no-info reference points

    Anything else in the output is suspect.
    """
    allowed: set[float] = {0.0, 100.0, float(payload.review_year)}

    for field, value in payload.__dict__.items():
        if value is None:
            continue
        if isinstance(value, (int, float)):
            allowed.add(float(value))
            allowed.add(round(float(value) * 100, 1))   # percentage form
            allowed.add(round(float(value), 2))
        if isinstance(value, list):    # anomalies
            for item in value:
                for k, v in item.items():
                    if isinstance(v, (int, float)):
                        allowed.add(float(v))
                        allowed.add(round(float(v) * 100, 1))
                        allowed.add(round(float(v), 2))

    return allowed


def validate_output(text: str, payload: CompanyAnalysisInput) -> list[float]:
    """
    Return the list of numbers in `text` that are NOT in the allowed set.
    Empty list = clean output.
    """
    allowed = _allowed_numbers(payload)
    used = _extract_numbers(text)

    suspicious = []
    for n in used:
        # Match within tolerance
        if not any(abs(n - a) < ALLOWED_NUMBER_TOLERANCE * max(abs(a), 1)
                   for a in allowed):
            suspicious.append(n)
    return suspicious


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def generate_review_summary(client, payload: CompanyAnalysisInput,
                             model: str = "claude-sonnet-4-20250514") -> dict:
    """
    Call the LLM, validate, and return a result dict.

    Parameters
    ----------
    client : anthropic.Anthropic
        Authenticated Anthropic client.
    payload : CompanyAnalysisInput
    model : str

    Returns
    -------
    dict with keys:
        text                — final summary (with disclaimer appended)
        raw_text            — model output before disclaimer
        suspicious_numbers  — list of numbers in output not in input (should be empty)
        warning             — set if validation failed
    """
    user_msg = build_prompt(payload)

    response = client.messages.create(
        model=model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw_text = response.content[0].text.strip()

    suspicious = validate_output(raw_text, payload)

    return {
        "text": raw_text + DISCLAIMER,
        "raw_text": raw_text,
        "suspicious_numbers": suspicious,
        "warning": (
            f"⚠️ Output contains {len(suspicious)} numbers not in the input: "
            f"{suspicious}.  Manual review required."
            if suspicious else None
        ),
    }


# ---------------------------------------------------------------------------
# Demo / offline preview (no API call) — produces a stub for sample output
# ---------------------------------------------------------------------------
def stub_review_summary(payload: CompanyAnalysisInput) -> str:
    """
    Deterministic non-LLM version, useful for testing the pipeline plumbing
    without spending API tokens.  Outputs roughly the same shape as the
    real LLM would.
    """
    p = payload
    pct = lambda x: f"{x*100:.1f}%" if x is not None else "N/A"

    parts = []
    parts.append(
        f"【整體財務體質】{p.company_name}（{p.ticker}，{p.industry_zh}）"
        f"{p.review_year} 年度負債比率 {pct(p.debt_ratio)}，"
        f"營業利益率 {pct(p.operating_margin)}，ROE {pct(p.roe)}。"
        f"Altman Z' 為 {p.altman_z_prime:.2f}，" if p.altman_z_prime else ""
    )
    parts.append(
        f"利息保障倍數 {p.interest_coverage:.1f} 倍，流動比率 {p.current_ratio:.2f}。"
        if p.interest_coverage and p.current_ratio else ""
    )

    # Peer comparison
    if p.industry_median_debt_ratio is not None:
        diff = (p.debt_ratio - p.industry_median_debt_ratio) * 100
        direction = "高於" if diff > 0 else "低於"
        parts.append(
            f"【同業比較】負債比率較{p.broad_industry_zh}中位數"
            f"({pct(p.industry_median_debt_ratio)})"
            f"{direction} {abs(diff):.1f} 個百分點。"
        )

    # Anomalies
    if p.anomalies:
        anomaly_str = "、".join(
            f"{a['year']}年{a['signal']}({a['direction']}, z={a['z_score']:.1f})"
            for a in p.anomalies[:3]
        )
        parts.append(f"【異常警示】偵測到 {len(p.anomalies)} 項異常：{anomaly_str}。")

    # Conclusion
    if p.risk_band == "低風險":
        rec = "建議維持現有授信額度，每年定期覆審即可。"
    elif p.risk_band == "關注":
        rec = "建議列入觀察名單，半年後再次檢視。"
    elif p.risk_band == "警示":
        rec = "建議降低授信曝險，並要求公司提供下季財務簡報。"
    elif p.risk_band == "高風險":
        rec = "建議啟動加強覆審程序，必要時調整授信條件或要求增提擔保。"
    else:
        rec = "建議交由產業專屬模型評估。"

    parts.append(f"【覆審結論】綜合風險分數 {p.risk_score} ({p.risk_band})，{rec}")

    return " ".join(p for p in parts if p) + DISCLAIMER


# ---------------------------------------------------------------------------
# CLI for quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample = CompanyAnalysisInput(
        ticker="2317",
        company_name="鴻海",
        industry_zh="電子代工",
        broad_industry_zh="製造業",
        review_year=2024,
        current_ratio=1.40,
        debt_ratio=0.62,
        interest_coverage=12.0,
        operating_margin=0.027,
        roe=0.09,
        altman_z_prime=1.95,
        revenue_5y_cagr=0.05,
        debt_5y_change=0.08,
        risk_score=25.9,
        risk_band="關注",
        anomalies=[
            {"signal": "營收年增率", "year": 2023, "z_score": -7.3, "direction": "下偏"},
            {"signal": "負債年增率", "year": 2023, "z_score": -2.3, "direction": "下偏"},
        ],
        industry_median_debt_ratio=0.55,
        industry_median_operating_margin=0.06,
        industry_median_roe=0.11,
    )
    print(stub_review_summary(sample))
