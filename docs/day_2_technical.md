# Day 2 — Technical Documentation
## 7 層架構 + Feature Engineering + Risk Flags + Agent Trace

---

## 1. Feature Engineering (`feature_engineering.py`)

```python
def _yoy_features(df: pd.DataFrame) -> pd.DataFrame:
    grp = df.groupby("ticker")

    df["revenue_yoy"]  = grp["revenue"].pct_change()
    df["profit_yoy"]   = grp["net_income"].pct_change()
    df["debt_yoy"]     = grp["total_liabilities"].pct_change()
    df["cash_yoy"]     = grp["cash_and_equivalents"].pct_change()

    df["profit_margin"] = (df["net_income"] / df["revenue"]).replace([np.inf, -np.inf], np.nan)
    return df
```

**Technical Breakdown**
- `groupby("ticker").pct_change()` — pandas 自動按 ticker 分組，計算 (t - t-1) / t-1，第一年輸出 NaN（正確，無前年可比）
- `.replace([np.inf, -np.inf], np.nan)` — 當 revenue = 0，profit_margin 會出現 inf，替換成 NaN 避免下游計算爆炸
- YoY 選這 4 個信號的原因：revenue（需求）、profit（獲利能力）、debt（槓桿）、cash（流動性）— 覆蓋信用風險的 4 個面向
- 用 **rates（變動率）而非 levels（絕對值）**：9 家公司規模差距 100 倍以上，只有比率才能跨公司比較

---

```python
def _rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    def _cagr_3y(series: pd.Series) -> pd.Series:
        lag2 = series.shift(2)
        cagr = (series / lag2) ** 0.5 - 1
        cagr[series.rolling(3).count() < 3] = np.nan
        return cagr

    rolling_cagr = (
        df.groupby("ticker")["revenue"]
        .apply(_cagr_3y)
        .reset_index(level=0, drop=True)
    )
    df["rolling_3y_revenue_growth"] = rolling_cagr

    df["rolling_std_profit"] = (
        df.groupby("ticker")["net_income"]
        .transform(lambda s: s.rolling(3, min_periods=3).std())
    )
    return df
```

**Technical Breakdown**
- **CAGR 公式**：`(end / start)^(1/n) - 1`，n=2 因為是 3 年期（t 到 t-2 是 2 個間隔）
- **為什麼 CAGR 不用 mean(YoY)**：`mean(YoY)` 是算術平均，CAGR 是幾何平均，後者正確反映複利效果
- `series.rolling(3).count() < 3` — 確保只有足夠 3 個數據點才計算，前兩年輸出 NaN（no look-ahead bias）
- `rolling(3, min_periods=3).std()` — `rolling_std_profit` 衡量獲利波動性，高 std = 盈餘品質差 = 難以預測還款能力
- `transform` vs `apply`：`transform` 保留原 index，`apply` 可能改變 index 結構 — groupby 後保留 index 用 `transform`

---

```python
def _zscore_features(df: pd.DataFrame) -> pd.DataFrame:
    def _cs_zscore(col: str) -> pd.Series:
        grp = df.groupby(["broad_industry_zh", "year"])[col]
        return (df[col] - grp.transform("mean")) / grp.transform("std")

    mask_fin = df["is_financial_sector"]
    df["zscore_revenue"] = np.where(mask_fin, np.nan, _cs_zscore("revenue"))
    df["zscore_profit"]  = np.where(mask_fin, np.nan, _cs_zscore("net_income"))
    return df
```

**Technical Breakdown**
- **Cross-sectional Z-score**（橫截面）vs `anomaly_detection.py` 的 Time-series Z-score（時間序列）：
  - 時間序列：「這家公司今年 vs 它自己過去」
  - 橫截面：「這家公司今年 vs 同產業同年的同儕」
  - 兩者都要：一家公司可能時間序列正常但橫截面是離群值，反之亦然
- `grp.transform("mean")` — 廣播（broadcast）產業-年份均值回原 DataFrame shape，對齊做減法
- `np.where(mask_fin, np.nan, ...)` — 金融業排除出橫截面比較（結構不同，不能 peer compare）

---

## 2. Rule-based Flags (`risk_flags.py`)

```python
THRESHOLDS = {
    "revenue_drop_pct":   -0.10,
    "debt_spike_pct":      0.30,
    "cash_low_pct":        0.05,
    "current_ratio_min":   1.00,
}
```

**Technical Breakdown**
- **集中化閾值管理（Centralized threshold registry）**：閾值全部放在一個 dict，調整時只改一個地方
- 為什麼是這些數字：
  - `-10%` revenue drop：一次性下滑 10% 在製造業屬異常（景氣波動通常 < 5%）
  - `+30%` debt spike：一年內負債增加 30% 代表重大融資事件（併購、擴廠）或財務惡化
  - `5%` cash：低於 5% 現金佔資產，short-term liquidity stress
  - CR < 1：流動負債 > 流動資產，理論上短期無法全數償還

---

```python
def _boolean_flags(df: pd.DataFrame) -> pd.DataFrame:
    df["is_revenue_drop"] = (
        df["revenue_yoy"].notna() &
        (df["revenue_yoy"] < THRESHOLDS["revenue_drop_pct"])
    )

    is_retail = df["industry"].isin(RETAIL_INDUSTRIES)
    df["is_ratio_abnormal"] = (
        df["current_ratio"].notna() &
        (df["current_ratio"] < THRESHOLDS["current_ratio_min"]) &
        ~is_retail
    )

    flag_cols = ["is_revenue_drop", "is_profit_negative",
                 "is_debt_spike", "is_cash_low", "is_ratio_abnormal"]
    df["flag_count"] = df[flag_cols].sum(axis=1).astype(int)
    return df
```

**Technical Breakdown**
- **Null-safe 條件**：`df["revenue_yoy"].notna() & (condition)` — 先確認不是 NaN 再做比較，否則 NaN < -0.10 結果是 False 而非 NaN，造成誤判
- **零售業豁免**（`~is_retail`）：統一超的 current_ratio 約 0.9，是業態特性（現金收款、快速庫存周轉），不是財務危機
- `df[flag_cols].sum(axis=1)` — 橫向加總 boolean columns（True=1），得到每列觸發的 flag 數量
- 5 個獨立 flags 的設計：互相獨立、可組合 — 同時觸發 3 個 flags 比觸發 1 個嚴重，`flag_count` 量化程度

---

```python
def _anomaly_score(df: pd.DataFrame) -> pd.DataFrame:
    rev_component = _clip01(
        (THRESHOLDS["revenue_drop_pct"] - df["revenue_yoy"].fillna(0))
        / abs(THRESHOLDS["revenue_drop_pct"])
    )

    profit_max_loss = 0.10
    profit_component = _clip01(
        np.where(
            df["net_income"] < 0,
            0.5 + (-df["net_income"] / df["revenue"]) / profit_max_loss * 0.5,
            0.0
        )
    )

    score = (
        ANOMALY_WEIGHTS["revenue_component"] * rev_component +
        ANOMALY_WEIGHTS["profit_component"]  * profit_component + ...
    )
    df["anomaly_score"] = np.where(df["is_financial_sector"], np.nan, score.round(3))
    return df
```

**Technical Breakdown**
- **Domain-anchored scaling 而非 min-max**：min-max 讓最差公司永遠是 1.0，掩蓋絕對嚴重程度。Domain anchors（threshold 是 0，某個極端值是 1.0）讓 score 有絕對意義
- `profit_component`：虧損給 0.5 base，虧得越深越接近 1.0（用 10% 虧損率作為滿分錨點）
- `np.where(fin, nan, score)` — 金融業 anomaly_score 設 NaN：他們的 rule-based flags 根本不適用（銀行的 debt_yoy 高是正常業務增長）
- **加權而非最大值**：取最大值會讓單一嚴重 flag 掩蓋其他信號；加權讓多個中等 flags 也能累積出高分

---

```python
def _decision_layer(df: pd.DataFrame) -> pd.DataFrame:
    combined_non_fin = (
        0.6 * df["risk_score"].fillna(50) +
        0.4 * df["anomaly_score"].fillna(0) * 100
    )
    combined_fin = (df["internal_rating"] - 1) / 9 * 100

    df["combined_score"] = np.where(
        df["is_financial_sector"], combined_fin.round(1), combined_non_fin.round(1)
    )

    conditions = [
        df["combined_score"] >= 70,
        df["combined_score"] >= 45,
        df["combined_score"] >= 20,
    ]
    choices = ["critical", "high", "medium"]
    df["final_risk_level"] = np.select(conditions, choices, default="low")
```

**Technical Breakdown**
- **60/40 blending**：risk_score（Altman-based，結構性）vs anomaly_score（behaviour-based，當期）
  - 結構性給 60%：長期財務體質更重要，short-term fluctuation 容易被操縱
  - 行為性給 40%：捕捉財報剛出現的壓力訊號
- `fillna(50)` for risk_score：NaN 時給中性值 50，不讓金融業因 NaN 被 filter 掉
- `np.select(conditions, choices, default="low")` — 比 `pd.cut` 更彈性，條件可以是任意 boolean expression
- **4 個行動建議**（approve / monitor / reduce_exposure / escalate）對應銀行實際操作選項，不是分析師自己發明的

---

## 3. Agent Trace (`agent_trace.py`)

```python
@contextmanager
def step(self, step_name, tool, input_ref, output_ref="pending",
         company_id=None, confidence=None):
    start = time.perf_counter()
    ctx = _StepContext(output_ref, confidence)
    try:
        yield ctx
        status = "success"
        error  = None
    except Exception as exc:
        status = "fail"
        error  = str(exc)
        raise
    finally:
        latency = (time.perf_counter() - start) * 1000
        self._steps.append(TraceStep(
            run_id=self.run_id, step_name=step_name,
            status=status, latency_ms=round(latency, 1), ...
        ))
```

**Technical Breakdown**
- **`@contextmanager` decorator** — 把 generator 函式轉換成 context manager，支援 `with tracer.step(...) as ctx:` 語法
- `time.perf_counter()` — 比 `time.time()` 精確，使用 CPU 計時器，不受系統時鐘調整影響，適合 latency profiling
- `try/yield/except/finally` 模式：
  - `try/yield`：執行 with block 內的 user code
  - `except`：捕捉 exception，記錄 status="fail"，然後 `raise` 重新拋出（不吞掉 error）
  - `finally`：無論成功失敗都記錄 TraceStep
- `_StepContext` 的 `set_output()` 和 `set_confidence()` — 讓 with block 內部可以回填輸出描述和信心分數

---

```python
@dataclass
class TraceStep:
    run_id:           str
    company_id:       Optional[str]
    step_name:        str
    tool_used:        str
    input_data_ref:   str
    output_data_ref:  str
    status:           str
    latency_ms:       float
    confidence_score: Optional[float] = None
    error_message:    Optional[str]   = None
    timestamp:        str = field(default_factory=lambda: datetime.utcnow().isoformat())
```

**Technical Breakdown**
- `@dataclass` — Python 3.7+ 的 decorator，自動生成 `__init__`、`__repr__`、`__eq__`，比手寫 class 省 20 行
- `Optional[str]` — 允許 None（`from typing import Optional`），比 `str | None` 的 Python 3.10 語法更向下相容
- `field(default_factory=lambda: ...)` — `default_factory` 每次實例化都執行一次，確保 timestamp 是創建時間而非 class 定義時間
- `asdict(step)` — dataclass 內建轉 dict 方法，讓 `pd.DataFrame([asdict(s) for s in steps])` 無縫轉換

---

```python
def generate_sample_hitl(decisions_df, run_id):
    for _, row in decisions_df.iterrows():
        level = row.get("final_risk_level", "low")
        review_prob = {"critical": 1.0, "high": 0.8,
                       "medium": 0.3, "low": 0.05}.get(level, 0.05)

        if random.random() > review_prob:
            continue

        if level in ("critical", "high") and random.random() < 0.3:
            human_flag = 1
            correction = "downgrade"
            final = "monitor"
```

**Technical Breakdown**
- **Risk-stratified review probability**：critical 100%、high 80%、medium 30%、low 5% — 模擬真實銀行的 risk-based sampling 稽核流程
- `random.random() > review_prob` — 隨機決定這筆是否被人工審查，`random.seed(42)` 確保 reproducible
- **30% override rate for high/critical** — 真實場景：AI 高估風險時人工會 downgrade，模擬 AI 的 false positive 率
- `HumanReview` dataclass 的 `correction_type` 欄位：upgrade / downgrade / confirmed / pending — 這個分類可以用來分析 AI 系統的 calibration 品質（AI 一直被 downgrade = 模型偏向保守）

---

---

# Day 2 面試 Q&A

---

## 🔧 Pipeline Engineering

**Q: 什麼是 Feature Engineering layer？為什麼要單獨抽出來？**
> 「Feature Engineering 是把 raw data 轉換成 ML-ready features 的層。我把它抽出成獨立模組（`feature_engineering.py`）有 3 個原因：(1) Model-agnostic — 同一套 features 可以同時餵給規則引擎、anomaly detection 和未來的 ML 模型 (2) Testable — 可以單獨 unit test feature 計算邏輯 (3) Auditable — 面試官或監理機關問『你的 input features 是怎麼算的』，有一個地方可以指。」

**Q: Cross-sectional Z-score 和 time-series Z-score 差在哪？你為什麼兩個都要？**
> 「Time-series Z-score 問的是『這家公司今年 vs 它自己過去』；cross-sectional Z-score 問的是『這家公司今年 vs 同產業同年同儕』。一家公司可能歷史表現穩定（TS z-score 低）但跟同業比明顯落後（CS z-score 高），或反過來。兩個信號正交，放一起讓 downstream 模型有更完整的圖像。」

**Q: Agent Trace 層做什麼？跟 logging 有什麼不同？**
> 「Logging 是 text，你要 parse 才能分析。Agent Trace 是結構化的 CSV，每個 step 一列，包含 latency_ms、confidence_score、input/output 的 data reference、status。差別是可以用 SQL 或 pandas 直接 query：『哪個 step 的失敗率最高？』『哪家公司的分析最慢？』這是 Production observability 的基礎。LangSmith 做的也是同樣的事，我這是輕量版。」

**Q: Human-in-the-loop 表記錄什麼？商業價值是什麼？**
> 「記錄 AI 建議 vs 人的最終決定，加上修正類型（upgrade / downgrade / confirmed）和時間。商業價值兩個：(1) Governance — 監理機關可以審計『AI 建議什麼、人最後怎麼決定』，銀行的責任在人不在 AI (2) Feedback loop — 累積一段時間後，AI 一直被 downgrade 的模式代表模型偏向 false positive，可以用這個 data 做 calibration。」

---

## 💰 Financial Logic

**Q: Rule-based flags 為什麼要做 boolean，不直接用 anomaly_score 就好？**
> 「Boolean flags 和 anomaly_score 各解決不同問題。Flags 是 hard rules：電流不足就跳電路保護，不管電流低多少。Anomaly_score 是 soft gradient：電流越低分數越高。Flag 的好處是 explainability —— 核貸主管問為什麼觸發警示，我可以說『is_debt_spike = True，負債年增率 45% 超過 30% 閾值』。這比說『anomaly_score 0.7』清楚 100 倍。」

**Q: Combined score 的 60/40 是怎麼決定的？**
> 「60% 結構性（Altman-based risk_score）、40% 行為性（anomaly_score）。原則是：結構性是慢變數（公司體質不會一年內劇變），行為性是快變數（今年的異常可能是一次性）。給結構性更高權重是保守做法，防止一個壞季度就讓好公司被降評。這個比例是 starting point，正式上線需要在歷史違約資料上做 calibration。」

**Q: 為什麼 `_decision_layer` 要用 `np.select` 不用 `pd.cut`？**
> 「`pd.cut` 只能做等距區間切分，條件必須是數值範圍。`np.select` 可以是任意 boolean expression — 未來如果要加『高風險 OR 3 個以上 flags 的強制 escalate』這種複合條件，pd.cut 做不到，np.select 改一行就解決。預留擴展彈性。」

---

## 📊 Dashboard / Narrative

**Q: Dashboard 的 Filter Action 設計邏輯是什麼？**
> 「只設一個 Action：點橫條圖的公司 → 趨勢線 drill-down。泡泡圖不發出 Action，因為點產業泡泡會把整個 portfolio 過濾到只剩一個產業，核貸專員反而看不到對比。設計原則是：互動路徑要跟用戶的分析流程一致 — 先看整體排序，點感興趣的公司，看它的歷史軌跡，這是覆審時的自然流程。」

**Q: 你 dashboard 的商業故事是什麼？60 秒講給我聽。**
> 「這是 2024 年企業授信投資組合總覽。左邊橫條圖：9 家授信戶，展騰餐飲 76.7 分、合纖工業 55 分觸發警示，台積電 4.2 分是最健康的。右上泡泡圖：曝險最大的是金融業和製造業。右下趨勢：展騰餐飲的風險分數過去 5 年持續上升，2022 年之後加速，跟它的連續虧損和 Altman Z' < 1.0 對應。點展騰餐飲，趨勢圖 drill-down 到它一條線，可以看到惡化的時間點。下一步：按 Page 3 看異常警示的細節。」
