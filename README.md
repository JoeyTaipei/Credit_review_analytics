# 年度授信覆審智能分析工具  
### AI 輔助授信風險分析 Dashboard｜Credit Review Analytics Portfolio Project

本專案是一個端到端的資料分析作品集，模擬金融機構在年度授信覆審流程中，如何使用 **Python 資料流程、財務風險指標、Tableau 互動式儀表板，以及自動產生授信覆審報告**，協助授信分析師更快辨識高風險公司、產業集中風險與潛在財務惡化訊號。

> **重要聲明**  
> 本專案使用 100% 模擬資料，僅作為作品集展示用途。  
> 這不是自動核貸系統，也不會取代人工授信判斷。  
> 本工具定位為 **AI-assisted decision support tool**：AI 協助分析師整理資料、提示風險與產生報告初稿，最終授信決策仍需由人工覆核。

---

## Dashboard Preview


![Dashboard Preview](docs/Dashboard_preview.png)

---

## 專案摘要

年度授信覆審通常需要分析師人工整理多家公司財務資料、計算財務比率、比較不同產業風險，並準備內部覆審文件。這個流程耗時、重複性高，也容易因不同分析師的判斷標準不同而造成風險評估不一致。

本專案建立一個實務導向的分析流程，將原始財務資料轉換成可視覺化、可追蹤、可產生報告的授信風險分析工具。

```text
模擬財務資料
        ↓
Python 資料處理流程
        ↓
財務比率計算
        ↓
風險旗標 + 異常偵測
        ↓
綜合風險分數
        ↓
建議授信行動
        ↓
Tableau Dashboard
        ↓
自動產生授信覆審報告
```

本專案重點不是建立一個完美的信用風險模型，而是展示如何將 **business problem → data pipeline → risk logic → dashboard → report generation** 串成完整的資料分析作品。

---

## 商業問題

金融機構在年度授信覆審時，常見痛點包括：

- 授信分析師需要花大量時間整理與檢查財務資料
- 不同公司與不同產業的風險不易快速比較
- 財務惡化可能是逐年發生，不容易即時被發現
- 主管需要快速掌握 portfolio 層級的風險分布
- 覆審報告需要標準化，方便內部溝通與審核
- 高風險公司需要被優先辨識並安排人工覆審

本專案模擬如何用資料分析方式，協助分析師更快完成授信覆審前期的資料整理、風險辨識與報告準備。

---

## 解決方案

系統會處理多年度公司財務資料，計算風險指標，產生風險分數與建議行動，最後輸出 Tableau dashboard 與 Markdown 授信覆審報告。

| 模組 | 說明 |
|---|---|
| 資料產生 | 建立 9 家公司 × 5 年的模擬財務資料 |
| 資料處理 | 清理資料、合併欄位、建立 Tableau-ready CSV |
| 財務比率 | 計算負債比、流動比、利息保障倍數、ROA、ROE、Altman Z' Score |
| 風險旗標 | 標記高負債、低流動性、低利息保障、營收衰退等風險 |
| 異常偵測 | 找出公司歷年財務表現中的異常變化 |
| 風險評分 | 結合 rule-based risk flags 與 anomaly score |
| 建議行動 | 依照風險等級產生授信覆審建議 |
| Tableau Dashboard | 呈現公司風險排名、產業風險分布與 5 年風險趨勢 |
| 自動報告 | 產生公司層級 Markdown 授信覆審報告 |

---

## 核心功能

- Python 端到端資料處理流程
- 財務比率自動計算
- Rule-based risk flag detection
- Time-series anomaly detection
- Composite risk score generation
- Suggested credit action logic
- Tableau-ready dashboard CSV output
- 互動式 Tableau dashboard
- 自動產生公司層級 Markdown 授信覆審報告
- 支援 PostgreSQL / Docker 作為延伸架構
- Human-in-the-loop 設計，避免將 AI 包裝成自動決策系統

---

## Tableau Dashboard 設計

Dashboard 以三個授信覆審問題為核心設計。

### 1. 企業風險分數排名

協助分析師快速辨識需要優先覆審的公司。

可回答問題：

- 哪些公司風險分數最高？
- 哪些公司屬於 High / Critical risk？
- 哪些公司應該進入人工覆審或進一步檢查？

### 2. 產業授信風險分布

協助主管觀察風險是否集中在特定產業。

可回答問題：

- 哪些產業的平均風險較高？
- 高風險公司是否集中在少數產業？
- Portfolio 是否存在產業集中風險？

### 3. 企業 5 年風險趨勢

追蹤公司風險是否逐年惡化或改善。

可回答問題：

- 哪些公司風險分數持續上升？
- 哪些公司在 2024 年突然惡化？
- 哪些公司雖然目前風險不高，但趨勢正在轉差？

---

## Tableau 互動功能

| 互動功能 | 目的 |
|---|---|
| Year Filter | 切換不同覆審年度 |
| Risk Band Filter | 聚焦 High / Critical risk 公司 |
| Industry Filter | 查看特定產業風險 |
| Dashboard Filter Action | 點擊產業泡泡後，自動更新公司排名與趨勢圖 |
| Tooltip Details | 顯示 suggested action、review reason 與 report path |
| URL Action | 點擊公司 bar，開啟 GitHub 上的授信覆審報告 |

### Report Link 設計

Tableau 不會在點擊 dashboard 時直接執行 Python。  
本專案採用較穩定的做法：先用 Python 產生報告，再讓 Tableau 開啟已產生的 GitHub report link。

```text
Python 產生 reports/*.md
        ↓
dashboard_credit_review.csv 儲存 report_url
        ↓
Tableau URL Action 開啟 report_url
```

---

## 自動產生授信覆審報告

使用以下指令可產生公司層級 Markdown 報告：

```bash
python scripts/generate_company_reports.py --github-base-url "https://github.com/JoeyTaipei/Credit_review_analytics/blob/main/reports"
```

此 script 會：

1. 讀取 `outputs/dashboard_credit_review.csv`
2. 產生 `reports/*.md`
3. 將 `report_path` 與 `report_url` 加回 `dashboard_credit_review.csv`
4. 讓 Tableau 可以透過 URL Action 開啟公司層級報告

每份報告包含：

- 公司基本資訊
- 年度風險等級
- 核心財務指標
- 系統建議行動
- 覆審原因
- 分析師覆核重點
- Human-in-the-loop 聲明

---

## 風險評分邏輯

### Step 1：財務比率計算

| 指標 | 公式 | 解讀 |
|---|---|---|
| Debt Ratio | Total Liabilities / Total Assets | 衡量槓桿程度 |
| Current Ratio | Current Assets / Current Liabilities | 衡量短期流動性 |
| Interest Coverage | EBIT / Interest Expense | 衡量利息償付能力 |
| ROA | Net Income / Total Assets | 衡量資產獲利能力 |
| ROE | Net Income / Equity | 衡量股東權益報酬 |
| Altman Z' Score | 非上市企業財務壓力指標 | 分數越低代表財務壓力越高 |

### Step 2：Rule-Based Risk Flags

系統會標記以下風險訊號：

- 高負債比
- 低流動比率
- 低利息保障倍數
- 淨利為負
- 營收明顯衰退
- Altman Z' 顯示財務壓力

### Step 3：綜合風險分數

```text
Composite Risk Score = Rule-Based Risk Score × 60% + Anomaly Score × 40%
```

目前 60/40 權重為 demo 用 heuristic 設定。  
若進入 production，應使用歷史違約資料校準模型，例如 logistic regression、XGBoost，並使用 AUC、KS、Gini 等指標驗證模型區辨能力。

---

## Human-in-the-Loop 設計

本專案刻意設計為 **AI-assisted decision support**，而不是 **automated loan approval**。

AI 可以協助：

- 整理財務指標
- 找出潛在風險訊號
- 產生授信覆審建議
- 建立報告初稿
- 協助分析師節省資料整理時間

AI 不應該直接決定：

- 是否核准授信
- 是否拒絕續貸
- 是否調整授信額度
- 是否要求額外擔保品
- 是否將公司列入特殊監控名單

最終決策仍應由授信分析師、主管或授信委員會進行人工覆核。

---

## 技術棧

| 類別 | 工具 |
|---|---|
| 程式語言 | Python |
| 資料處理 | pandas, NumPy |
| 風險邏輯 | Rule-based scoring, anomaly detection |
| 視覺化 | Tableau |
| 報告輸出 | Markdown, CSV |
| 資料庫 | PostgreSQL, SQLAlchemy |
| 環境管理 | Docker |
| 版本控制 | Git, GitHub |

---

## 專案結構

```text
credit_review_tool/
├── scripts/
│   ├── generate_sample_data.py
│   ├── run_full_pipeline.py
│   ├── generate_executive_summary.py
│   ├── generate_case_study.py
│   └── generate_company_reports.py
│
├── src/
│   ├── financial_ratios.py
│   ├── feature_engineering.py
│   ├── anomaly_detection.py
│   ├── risk_flags.py
│   ├── credit_actions.py
│   └── agent_trace.py
│
├── outputs/
│   └── dashboard_credit_review.csv
│
├── reports/
│   └── *_credit_review.md
│
├── docs/
│   ├── Dashboard_preview.png
│   ├── interview_script_zh.md
│   └── 10_day_finish_plan_zh.md
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 如何執行

### 1. Clone repository

```bash
git clone https://github.com/JoeyTaipei/Credit_review_analytics.git
cd Credit_review_analytics
```

### 2. 安裝套件

```bash
pip install -r requirements.txt
```

### 3. 執行完整 pipeline，不使用資料庫

```bash
python scripts/run_full_pipeline.py --skip-db
```

### 4. 產生公司層級授信覆審報告

```bash
python scripts/generate_company_reports.py --github-base-url "https://github.com/JoeyTaipei/Credit_review_analytics/blob/main/reports"
```

### 5. 開啟 Tableau

使用以下 CSV 作為 Tableau 主要資料來源：

```text
outputs/dashboard_credit_review.csv
```

---

## 主要輸出

| 輸出檔案 | 說明 |
|---|---|
| `outputs/dashboard_credit_review.csv` | Tableau 主要資料來源 |
| `reports/*.md` | 自動產生的公司層級授信覆審報告 |
| `outputs/executive_summary.csv` | Portfolio 層級摘要 |
| `outputs/ratios_wide.csv` | 財務比率寬表 |
| `outputs/anomalies.csv` | 異常偵測結果 |
| `outputs/risk_flags.csv` | 風險旗標結果 |

---

## 專案限制

| 限制 | 影響 | 未來改進 |
|---|---|---|
| 使用模擬資料 | 無法驗證真實違約預測能力 | 接入公開財報或授權資料 |
| 沒有 default labels | 無法訓練 supervised default prediction model | 加入歷史違約標籤 |
| 權重為 heuristic | 風險分數尚未統計校準 | 使用 logistic regression 或 XGBoost 校準 |
| 未加入總體經濟變數 | 無法反映利率、GDP 或景氣循環 | 加入 macroeconomic indicators |
| 質化資料有限 | 尚未分析年報文字、新聞或授信 memo | 未來可加入 LLM / RAG |
| Demo 主要使用 CSV | 尚非 production data architecture | 可升級為 PostgreSQL 或 data warehouse |

---

## 未來優化方向

1. **接入真實或公開財務資料**  
   將 synthetic data 替換成公開財報或經授權的金融機構資料。

2. **模型校準與驗證**  
   使用歷史違約資料校準風險分數，並加入 AUC、KS、Gini 等模型驗證指標。

3. **加入總體經濟變數**  
   加入利率、GDP 成長率、產業景氣循環等變數。

4. **LLM 生成 Credit Memo**  
   使用 LLM 根據結構化財務資料產生更完整的授信 memo 初稿。

5. **RAG for Unstructured Documents**  
   當資料範圍擴充到年報、新聞、授信合約或內部 memo 時，再加入 RAG 讓分析師能查詢非結構化文件。

6. **MLOps 與監控**  
   加入資料漂移偵測、模型監控與定期重新校準流程。

---

## 面試說明重點

這個專案展示我能將商業問題轉換成資料分析解決方案：

```text
Business problem
        ↓
Python data pipeline
        ↓
Financial risk logic
        ↓
Tableau dashboard
        ↓
Auto-generated reports
        ↓
Human-reviewed decision support
```

此專案對應的能力包括：

- Python 資料處理能力
- 財務風險分析邏輯
- Tableau dashboard 設計
- 商業問題拆解
- 自動化報告生成
- Responsible AI / Human-in-the-loop 思維
- End-to-end project execution

---

## Author

Built by Joey as a portfolio project for data analyst and analytics consulting internship applications.
