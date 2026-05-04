# Day 1 — 環境就緒 + 跑完 Pipeline + Tableau 第一張圖
**目標**：今天結束時，你應該有：(a) 程式跑得起來，(b) Tableau Public 連上資料，(c) 一張可截圖的「風險分數 by 公司」橫條圖。

> 設計原則：今天**不**追求好看，追求「看到資料、知道下一步」。

| 區塊 | 時間 | 產出 |
|---|---|---|
| Block 1 | 45 min | Python 環境裝好 |
| Block 2 | 30 min | Pipeline 跑出 5 個 CSV |
| Block 3 | 60 min | 看懂自己的 code，寫 3 個問題 |
| Block 4 | 30 min | Tableau Public 安裝完成 |
| Block 5 | 60 min | 第一張圖：風險分數橫條圖 |
| Block 6 | 30 min | Day-1 journal 寫完 |
| **總計** | **~4.5 小時** | （留 buffer 給卡關）|

---

## Block 1 — 環境（45 min）

### 1.1 確認 Python 版本（≥ 3.10）
```bash
python --version
# 如果顯示 3.10+ 就 OK；如果是 3.8 或更舊，先去 python.org 裝最新版
```

### 1.2 建虛擬環境（重要：不要污染全域 pip）
```bash
cd credit_review_tool
python -m venv .venv

# Mac / Linux：
source .venv/bin/activate
# Windows PowerShell：
.venv\Scripts\Activate.ps1
```
看到 prompt 開頭多了 `(.venv)` 才算成功。

### 1.3 安裝依賴
```bash
pip install -r requirements.txt
```

### 1.4 驗證
```bash
python -c "import pandas, numpy, sklearn; print('OK')"
```
看到 `OK` 就過關。

**卡關處方**：
- `pip install` 卡住 → 試 `pip install -r requirements.txt -i https://pypi.org/simple`
- macOS Apple Silicon scipy/sklearn 編譯失敗 → 升級 pip：`pip install --upgrade pip`

---

## Block 2 — 跑 Pipeline（30 min）

### 2.1 產生模擬資料
```bash
python scripts/generate_sample_data.py
```
預期看到：
```
✓ Generated 35 firm-year rows across 7 companies
```

### 2.2 跑完整 pipeline
```bash
python scripts/run_full_pipeline.py
```
預期看到：
```
[1/5] Loading financials …
[2/5] Computing ratios …
[3/5] Detecting anomalies …
[4/5] Building LLM input for focal company (2317 鴻海) …
[5/5] Generating stub LLM output …
✓ Pipeline complete.
```

### 2.3 確認 5 個輸出檔都生出來
```bash
ls outputs/
```
應該看到：`ratios_wide.csv  ratios_long.csv  anomalies.csv  sample_llm_input.json  sample_llm_output.md`

> ⚠️ 如果有檔案缺，**現在停下來除錯**。讓 Day 1 這裡乾淨，後面才不會疊 bug。

---

## Block 3 — 讀懂你自己的 code（60 min）

這 1 小時的目標：能用 1 分鐘解釋 pipeline 從原始資料到風險分數的流程。

### 3.1 用一家公司 (鴻海 2317) 走一遍
打開這幾個檔案，**對照看**鴻海 2024 年的數字：

| 檔案 | 看什麼 | 鴻海 2024 應該長這樣 |
|---|---|---|
| `data/sample_financials_long.csv` | 原始營收、總負債、淨利 | revenue ≈ 5xxx (B TWD) |
| `outputs/ratios_wide.csv` | debt_ratio, roe, altman_z_prime | debt_ratio ≈ 0.61 |
| `outputs/anomalies.csv` | 是否有 is_anomaly = True | 2023 年營收年增率 z=-7.3 |
| `outputs/sample_llm_input.json` | 給 LLM 的結構化包 | 整包 JSON |
| `outputs/sample_llm_output.md` | 中文初稿 | 200-300 字覆審意見 |

### 3.2 讀懂這 3 段關鍵 code
打開檔案，找到並用自己的話寫一行解釋：

1. `src/financial_ratios.py` 的 `compute_risk_score` — 為什麼用 35% / 25% / 20% / 20% 加權？
2. `src/anomaly_detection.py` 的 `_loo_z` — 為什麼要 leave-one-out？（提示：n=4 樣本）
3. `src/llm_summary.py` 的 `validate_output` — 這在防什麼？

### 3.3 寫下 3 個問題
任何「為什麼這樣寫」「能不能改用 X」「我看不懂這段」都列出來。寫在 `docs/my_questions.md`。**這份清單就是你 Day 2-3 的學習清單**。

> 顧問業 partner 問「你 defend 這行 code」時，你要當場答得出來。今天不答出來沒關係，但**要知道自己不懂**。

---

## Block 4 — Tableau Public 安裝（30 min）

### 4.1 下載
1. 到 https://public.tableau.com/
2. 點右上「Sign Up」建免費帳號（用你的個人 email，不要用實習公司的）
3. 下載 Tableau Public Desktop（Mac / Windows）
4. 安裝完成後打開

### 4.2 介面 5 分鐘導覽
打開 Tableau Public，記住這 4 個區塊位置（之後 80% 時間都在這邊）：
- 左側 **Data pane** — 顯示資料的欄位，分 Dimensions（藍色）和 Measures（綠色）
- 中間 **Worksheet** — 拖欄位來這裡建圖
- 上方 **Rows / Columns shelves** — 決定圖的 X / Y 軸
- 右側 **Marks card** — 控制顏色、大小、標籤、形狀

> Dimensions = 類別欄位（公司、年份、產業）→ 切片用
> Measures = 數值欄位（負債比率、ROE、風險分數）→ 計算用
> Tableau 會自己猜，**80% 的時候會猜錯**。年份特別容易被當成 Measure 加總，要手動改。

---

## Block 5 — 第一張圖：風險分數橫條圖（60 min）

**為什麼從這張圖開始**：它只用 2 個欄位，5 分鐘畫得出來，但展示了「公司排序 + 顏色分群 + 標籤」三個基本功。

### 5.1 連資料
1. 開啟 Tableau Public
2. 左下「Connect」→「To a File」→「Text file」
3. 選 `outputs/ratios_wide.csv`
4. Tableau 會自動載入，看到資料 preview 後點左下「Sheet 1」進工作表

### 5.2 修欄位型態（很重要，不修後面會踩雷）
看左側 Data pane：
- `Year` 應該是 Dimension（藍色 #）。如果它在 Measures 區（綠色 Σ），右鍵 → Convert to Dimension。
- `Ticker` 也是 Dimension。如果是 Measure，同樣轉換。
- `Risk Score` 應該是 Measure（綠色）。

### 5.3 建圖
1. 左側 Filters 區拖入 `Year`，選 2024（只看最新年）
2. 把 `Company Name` 拖到 **Rows**
3. 把 `Risk Score` 拖到 **Columns**
4. 應該看到一個橫條圖了
5. 把 `Risk Band` 拖到 Marks card 的 **Color**
6. 把 `Risk Score` 再拖一次到 Marks card 的 **Label**（會顯示數字）
7. 點工具列「Sort Descending」按鈕（A-Z 旁邊有箭頭那個）

### 5.4 整理一下
- 標題：上方雙擊「Sheet 1」→ 改成「2024 投資組合風險評分」
- 顏色：點 Marks → Color → Edit Colors，把：
  - 低風險 → 灰色 / 淡藍
  - 關注 → 黃
  - 警示 → 橘
  - 高風險 → 紅
  - 金融業(另採模型) → 淡灰
- 把 X 軸標題改成「風險分數（0=低，100=高）」

### 5.5 截圖存證
File → Export → Image，存到 `docs/day_1_screenshot.png`。

> 這張圖**就是**未來 Page 1 dashboard 的左上角元件。今天有這個就夠了。

---

## Block 6 — Day 1 收尾（30 min）

### 6.1 寫 journal（5 分鐘，不要超過）
建一個 `docs/journal.md`，今天寫 5 句話：
1. 我今天做了什麼（一句）
2. 哪一步最卡（一句）
3. 我學到一個新的 Tableau 概念是 ___（一句）
4. 我對 ___ 還不確定（一句）
5. 明天第一件事是 ___（一句）

> Partner review 前你會回頭看這份 journal，比你想像的有用。

### 6.2 整理當天 commit（如果用 Git）
```bash
git add .
git commit -m "Day 1: pipeline working, first Tableau chart"
```

### 6.3 預告 Day 2
明天目標：**完成 Page 1（投資組合總覽）**
- 把今天的橫條圖放上 dashboard
- 加上：產業分布圓餅圖（小心不要做成花俏的 donut）、近 5 年總曝險趨勢線
- 學一個新東西：Dashboard 的 Filter Action（點公司 → 跳到 Page 2）

---

## 自我檢核（睡前 30 秒）

- [ ] `python scripts/run_full_pipeline.py` 跑得通，沒有紅字
- [ ] `outputs/` 下有 5 個檔案
- [ ] 我能說出 leave-one-out Z-score 為什麼要 leave-one-out
- [ ] Tableau Public 開得起來，能連上 ratios_wide.csv
- [ ] 我有一張橫條圖，年份固定 2024，公司排序，按風險分群上色
- [ ] `docs/my_questions.md` 寫了至少 3 個問題
- [ ] `docs/journal.md` 寫完今天 5 句話

打勾數 ≥ 6 → Day 1 過關。打勾數 ≤ 4 → 補完再睡，不要拖到明天。

---

## 給未來的你

第一天通常會發現：
- 你以為簡單的事（環境、Tableau 欄位型態）會卡 30 分鐘
- 你以為難的事（讀別人 code）其實還好
- 你會想一次做完整個 dashboard ← **抗拒這個衝動**。今天就到這裡，明天大腦比較清楚。

如果你提早做完，請**不要**開始 Day 2。把多的時間拿去：
- 把 ratios_wide.csv 在 Excel 打開，肉眼看一遍 35 列數字
- 想：「如果我是核貸專員，看到這 35 列，我會先問什麼？」
- 把答案寫在 `docs/my_questions.md`
