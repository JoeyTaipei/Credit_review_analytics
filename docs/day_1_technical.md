# Day 1 — Technical Documentation
## Pipeline 建立 + 財務比率 + 異常偵測

---

## 1. 資料生成 (`generate_sample_data.py`)

```python
RNG = np.random.default_rng(seed=20260504)

def _noise(scale: float = 0.05) -> float:
    return float(np.clip(RNG.normal(1.0, scale), 1 - 3 * scale, 1 + 3 * scale))
```

**Technical Breakdown**
- `np.random.default_rng(seed)` — NumPy 新式隨機生成器，比 `np.random.seed()` 更安全，同一 seed 產生完全相同序列（reproducibility）
- `RNG.normal(1.0, scale)` — 以 1.0 為中心的正態分布，產生乘法噪聲（1 ± 5%）
- `np.clip(...)` — 防止極端值：超過 3σ 的噪聲截斷，確保數字不會變負數或爆炸
- 時間複雜度：O(1) per call，整體資料生成 O(n × m)，n = 公司數，m = 年份數

---

```python
COMPANIES = {
    "2330": {
        "revenue_cagr": 0.20,
        "gross_margin_mean": 0.52,
        "debt_ratio_mean": 0.30,
        "credit_exposure_mean": 85,
        "internal_rating_mean": 1.5,
    },
    ...
}
```

**Technical Breakdown**
- 用 `dict of dicts` 作為公司 profile 儲存，key = 股票代號（字串）
- `credit_exposure_mean`（億元）、`internal_rating_mean`（1-10）是本次新增的 credit fields
- Profile 是靜態錨點（anchors），實際年度數值由 `_noise()` 在 `_build_non_financial()` 裡產生
- 設計原則：profile = 業務邏輯（製造業高槓桿正常）；noise = 統計現實（每年有波動）

---

```python
def build_dataset() -> pd.DataFrame:
    all_rows = []
    for ticker, profile in COMPANIES.items():
        fn = _build_financial if profile["is_financial"] else _build_non_financial
        all_rows.extend(fn(ticker, profile))
    return pd.DataFrame(all_rows).sort_values(["ticker", "year"]).reset_index(drop=True)
```

**Technical Breakdown**
- `fn = _build_financial if ... else _build_non_financial` — 函式物件作為變數（first-class function），根據 `is_financial` 動態選擇建構函式
- `all_rows.extend(...)` — 比 `append(list)` 快，直接把 list 攤開加進去，避免巢狀 list
- `sort_values(["ticker", "year"])` — 確保輸出排序穩定，後續 `groupby().diff()` 計算 YoY 需要時間序順序
- `reset_index(drop=True)` — 避免舊 index 遺留影響後續 merge

---

## 2. 資料 Pipeline (`data_pipeline.py`)

```python
CANONICAL_COLUMNS = [
    "ticker", "company_name", "industry", "industry_zh",
    "broad_industry", "broad_industry_zh", "year",
    "is_financial_sector",
    "revenue", "cogs", "gross_profit", "operating_income", "net_income",
    "interest_expense",
    "total_assets", "total_liabilities", "total_equity",
    "current_assets", "current_liabilities",
    "cash_and_equivalents", "accounts_receivable", "inventory",
    "retained_earnings", "market_value_equity",
    "operating_cash_flow",
    "credit_exposure", "credit_limit", "internal_rating", "utilisation_rate",
]
```

**Technical Breakdown**
- Canonical column list = **schema contract**：下游所有模組只依賴這個 list，不硬寫欄位名稱
- 順序重要：識別欄位 → 財務報表欄位 → 授信欄位，方便 code review 和 debug
- `broad_industry` / `broad_industry_zh` 同時保留英文和中文，英文給 Python 做 groupby key，中文給 Tableau 顯示

---

```python
def _validate_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    eq_check = df["total_assets"] - (df["total_liabilities"] + df["total_equity"])
    bad = eq_check.abs() > df["total_assets"] * 0.01
    if bad.any():
        logger.warning("Balance sheet identity violated for %d rows", int(bad.sum()))

    dups = df.duplicated(subset=["ticker", "year"])
    if dups.any():
        raise ValueError(f"Duplicate (ticker, year) rows detected")

    return df[CANONICAL_COLUMNS]
```

**Technical Breakdown**
- **List comprehension** `[c for c in ... if c not in df.columns]` — O(n) 欄位缺失檢查
- **Balance sheet identity check**：資產 = 負債 + 股東權益，容許 1% 浮點數誤差（模擬資料噪聲造成）
- **Duplicate check** `df.duplicated(subset=["ticker", "year"])` — 防止同一公司同一年被重複插入，保護下游 groupby 的正確性
- `return df[CANONICAL_COLUMNS]` — 明確限制欄位順序輸出，確保任何 source 進來都有相同 schema

---

## 3. 財務比率 (`financial_ratios.py`)

```python
def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    den = den.replace(0, np.nan)
    return num / den
```

**Technical Breakdown**
- `replace(0, np.nan)` — 把分母的 0 換成 NaN，Series 除以 NaN = NaN，避免 ZeroDivisionError 或 inf
- 不用 `try/except`，因為 pandas 向量化運算不會拋 Python exception，必須用數值層處理
- 回傳 NaN 而非 0 或 error：下游 Tableau 顯示 NaN = 空白，比顯示 0 更誠實

---

```python
def _compute_for_ticker(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("year").copy()

    prev_assets = g["total_assets"].shift(1)
    avg_assets  = (g["total_assets"] + prev_assets) / 2
    avg_assets  = avg_assets.fillna(g["total_assets"])

    g["roa"] = _safe_div(g["net_income"], avg_assets)
    g["roe"] = _safe_div(g["net_income"], avg_equity)
```

**Technical Breakdown**
- `shift(1)` — 取上一年的值（lag），用於計算平均期初期末餘額（CFA / IFRS 標準做法）
- `fillna(g["total_assets"])` — 第一年沒有 lag，用期末值代替期初 + 期末平均
- 平均餘額的重要性：ROE 用「全年平均股東權益」而非年末值，防止年末資本操作造成失真
- `g.sort_values("year").copy()` — copy() 防止 pandas SettingWithCopyWarning，對 slice 操作安全

---

```python
# Altman Z' (Private firm version, 1983)
x1 = _safe_div(working_capital, g["total_assets"])
x2 = _safe_div(g["retained_earnings"], g["total_assets"])
x3 = _safe_div(g["operating_income"], g["total_assets"])
x4 = _safe_div(g["total_equity"], g["total_liabilities"])
x5 = _safe_div(g["revenue"], g["total_assets"])

g["altman_z_prime"] = 0.717*x1 + 0.847*x2 + 3.107*x3 + 0.420*x4 + 0.998*x5
```

**Technical Breakdown**
- **Z' vs Z**：原版 Z（1968）X4 用市值，只適用上市公司。Z'（1983）用帳面股東權益，適用私人公司 / SME（銀行 90% 客戶是 SME）
- **5 個 X 的意義**：
  - X1（流動性）、X2（累積獲利）、X3（資產報酬）、X4（財務槓桿）、X5（資產運用效率）
- **係數來源**：Altman 用 1968 年 33 家破產 + 33 家正常公司做 Linear Discriminant Analysis（LDA）估計
- **為什麼不自己 refit**：沒有台灣違約歷史資料；用學界公認 baseline 比 refit 一個不能 defend 的模型更專業

---

```python
def compute_risk_score(ratios_wide: pd.DataFrame) -> pd.DataFrame:
    z     = out["altman_z_prime"]
    dr    = out["debt_ratio"]
    ic    = out["interest_coverage"]

    altman_score = np.clip((2.9 - z) / (2.9 - 0.5) * 100, 0, 100)
    debt_score   = np.clip((dr - 0.3) / (0.8 - 0.3) * 100, 0, 100)
    ic_score     = np.clip((10 - ic) / (10 - 1) * 100, 0, 100)

    weights = pd.Series({"altman": 0.35, "debt": 0.25, "ic": 0.20, "trend": 0.20})
```

**Technical Breakdown**
- `np.clip(value, 0, 100)` — 把任何比率線性映射到 0-100，超界截斷
- **領域錨點（domain anchors）**：
  - Altman: Z'=2.9（安全）→ 0分，Z'=0.5（危機）→ 100分
  - Debt ratio: 30% → 0分，80% → 100分（台灣製造業常見上限）
  - IC: 10x → 0分，1x → 100分（< 1x 代表連利息都付不起）
- **加權 35/25/20/20 defense**：Altman 最高因為它已整合 5 個比率；負債比直接反映銀行最在意的槓桿；IC 是即時現金流壓力；ROE 趨勢是領先指標

---

## 4. 異常偵測 (`anomaly_detection.py`)

```python
def _loo_z(group: pd.Series) -> pd.Series:
    n = len(group)
    if n < 3:
        return pd.Series(np.nan, index=group.index)
    total_sum    = group.sum()
    total_sq_sum = (group ** 2).sum()
    loo_mean     = (total_sum - group) / (n - 1)
    loo_var      = ((total_sq_sum - group**2) / (n-1)) - loo_mean**2
    loo_var      = loo_var.clip(lower=1e-10)
    loo_std      = np.sqrt(loo_var)
    return (group - loo_mean) / loo_std
```

**Technical Breakdown**
- **Leave-one-out（LOO）原理**：計算第 i 年的 z-score 時，從 mean/std 計算中排除第 i 年本身
- **為什麼要 LOO**：正常 Z-score 在 n=4 下，離群值自己撐大 std，數學上 |z| ≤ √((n-1)/n) ≈ 0.87，永遠觸發不了 2σ 門檻
- **Welford 公式變體**：`total_sq_sum - group**2` 一次減掉該點的平方，避免兩次迴圈，O(n) 計算 n 個 LOO 變異數
- `clip(lower=1e-10)` — 防止數值精度問題讓 std 變負數後開根號 NaN
- `n < 3` guard — LOO 需要至少 3 個點才有意義（2 個點的 std 是 0）

---

```python
SIGNALS = {
    "revenue_yoy":    "營收年增率",
    "liabilities_yoy": "負債年增率",
    "ocf_change":     "營運現金流變動",
}
```

**Technical Breakdown**
- **為什麼選這 3 個信號**：這 3 個最常出現在信用事件的前兩年（學界 credit distress literature）
  - 營收年增率 → 需求 / 競爭力問題
  - 負債年增率 → 槓桿快速擴張
  - 現金流變動 → 流動性壓力
- **為什麼不用 levels（絕對值）而用 YoY 變化率**：不同公司 size 差異大，level 不能跨公司比；YoY 是相對變化，具可比性
- 3 個信號夠少，每個都能解釋；太多信號會稀釋注意力，核貸專員看不過來

---

---

# Day 1 面試 Q&A

---

## 🔧 Pipeline Engineering

**Q: 你的資料 pipeline 是怎麼設計的？**
> 「三層分離：(1) Source layer — `data_pipeline.py` 抽象化資料來源，sample / FinMind / TWSE 都實作同一個介面 (2) Transform layer — `financial_ratios.py` 和 `feature_engineering.py` 只做計算，不管資料從哪來 (3) Output layer — 固定輸出格式到 CSV / DB。這樣換資料來源不影響下游，換分析模型不影響 ingestion。」

**Q: 為什麼用 long format 輸出 `ratios_long.csv`？**
> 「Tableau 對 long format 最友好 — 每個比率是一列，用 `ratio_name` 做 filter，新增一個比率不需要改 schema，也不需要重建 dashboard 的 data connection。Wide format 對 pandas 計算友好，所以我兩個都輸出。」

**Q: `_validate_and_clean` 做了哪些 checks？為什麼？**
> 「三個：欄位完整性、balance sheet identity（資產 = 負債 + 權益，容許 1% 浮點誤差）、duplicate (ticker, year)。在 banking 場景下這些是基本 data quality gates — 任何一個失敗都代表上游資料有問題，與其讓錯誤數字進到比率計算，不如在 ingestion 就攔截。」

---

## 💰 Financial Logic

**Q: Altman Z' 和原版 Z 差在哪？你為什麼選 Z'？**
> 「原版 Z（1968）的 X4 是股票市值 / 總負債，只能用在上市公司。Z'（1983 修正版）把 X4 改成帳面股東權益 / 總負債，適用私人公司。銀行的企業授信客戶 90% 是 SME，不是上市公司。我選 Z' 讓這個工具對實際客戶群適用。」

**Q: 風險分數的 35/25/20/20 權重怎麼決定的？**
> 「這是 expert-driven 的初始設定，不是統計估計的。Altman 35% — 它本身整合了 5 個比率，給最高權重；負債比 25% — 台灣銀行最在意的單一指標，過去幾次本土金融危機都跟槓桿有關；IC 20% — 即時現金流壓力；ROE 趨勢 20% — 領先指標。**正確 framing 是『這是 calibration 起點，正式上線應由 credit officer 共同調整』，不是『這是最優解』。**」

**Q: 為什麼 ROE 和 ROA 要用平均餘額而非期末值？**
> 「CFA / IFRS 標準做法。期末值問題是：如果公司 12 月增資，分母突然變大，ROE 被人為壓低。平均（期初 + 期末）/ 2 反映全年真實資金成本。第一年沒有期初就用期末，這也是 TEJ 的處理方式。」

**Q: 金融業為什麼不算 Altman Z'？**
> 「Z' 的分子分母都假設公司有實體業務的資產負債結構 — 有存貨、有應收帳款、有生產性固定資產。金融業的『資產』是放款和金融資產，『負債』是存款。X1（營運資金）、X5（銷售/資產）對金融業完全不適用，強行計算會得出無意義的數字。標 N/A 是正確的工程判斷。」

---

## 📊 Dashboard / Narrative

**Q: Tableau Page 1 設計邏輯是什麼？**
> 「三圖回答三個問題：(1) 橫條圖 — 哪家公司現在風險最高？(2) 泡泡圖 — 曝險集中在哪個產業？(3) 趨勢線 — 風險在惡化還是改善？這三個是核貸專員覆審時一定要看的問題。顏色統一用 risk band 的 4 色系貫穿三張圖，讓人一眼對應。」

**Q: 為什麼泡泡圖用 credit_exposure 而不是 total_assets？**
> 「Total assets 是公司自己的數字，銀行看不到曝險。Credit exposure 是銀行借出去多少錢 — 台積電 total assets 幾兆，但銀行只借了 85 億；鴻海 total assets 可能也很大，但銀行借了 120 億。泡泡大小 = 我的曝險，這才是 portfolio risk concentration 的正確 framing。」

**Q: Dashboard 為什麼不做雷達圖？**
> 「Tableau 做雷達圖需要轉極座標、normalize 不同量綱的比率（current_ratio 是 1.x，IC 可以是 100x），工程成本高投報率低。更重要的是雷達圖難以精確讀數，顧問業偏好讓人能讀出具體數字的圖。核貸專員需要的不是『形狀好不好看』而是『這個數字超過警戒線了嗎』。」
