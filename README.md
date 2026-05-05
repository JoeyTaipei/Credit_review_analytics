# 🏦 年度授信覆審 AI 分析工具
### AI 輔助 Portfolio Risk Analysis｜Deloitte Data Analyst Intern Demo

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791)](https://www.postgresql.org/)
[![Tableau](https://img.shields.io/badge/Visualization-Tableau-E97627)](https://www.tableau.com/)
[![Status](https://img.shields.io/badge/Status-Demo%20Ready-green)]()

---

## 📌 專案簡介

本專案是一個 **AI 輔助的年度授信覆審分析工具**，模擬金融機構在企業授信覆審流程中，如何透過資料分析、風險評分與視覺化儀表板，協助授信人員更快識別高風險公司與產業集中風險。

系統會使用多年度企業財務資料，計算財務比率、偵測異常變化、建立風險分數，並輸出可供 Tableau 使用的 dashboard 資料與一頁式覆審摘要。

> **重要聲明：**  
> 本專案使用 100% 模擬資料，僅作為作品集展示用途。  
> 這不是自動核貸系統，也不會取代人工授信判斷。  
> AI 的角色是協助整理資料、提示風險與產生建議，最終決策仍需由授信人員或主管覆核。

---

## 🎯 商業問題

金融機構在年度授信覆審時，常面臨以下痛點：

- 企業財務資料量大，人工整理耗時
- 不同授信人員的風險判斷標準可能不一致
- 財務惡化或異常變化不容易即時被發現
- 產業集中風險難以用直覺方式呈現
- 主管需要快速掌握 portfolio 層級的風險概況

本專案的目標是建立一個 **data-driven credit review workflow**，協助分析師快速完成：

1. 財務資料整理  
2. 財務比率計算  
3. 風險旗標標記  
4. 異常偵測  
5. Tableau 視覺化  
6. 覆審建議與摘要輸出  

---

## 💡 解決方案

| 分析層級 | 功能 | 使用技術 |
|---|---|---|
| 資料產生 | 建立 9 家公司 × 5 年模擬財務資料 | Python / Pandas |
| 資料處理 | 清理資料、轉換格式、建立 Tableau 輸出 | Python / Pandas |
| 財務比率 | 負債比、流動比、利息保障倍數、ROA、ROE、Altman Z' | Python / NumPy |
| 風險旗標 | 高負債、低流動性、低利息保障、營收衰退等 | Python |
| 異常偵測 | 比較公司歷年財務變化，找出異常波動 | Python |
| 建議行動 | 根據風險等級產生授信覆審建議 | Python |
| 報告輸出 | 產出 executive summary 與 case study | CSV / Markdown |
| 視覺化 | 建立互動式風險儀表板 | Tableau |
| 資料庫 | 支援 PostgreSQL / Docker，但 demo 可使用 CSV | PostgreSQL / Docker |

---

## 🏗️ 專案架構

```text
credit_review_tool/
├── scripts/
│   ├── generate_sample_data.py          # 產生模擬財務資料
│   ├── run_full_pipeline.py             # 一鍵執行完整 pipeline
│   ├── generate_executive_summary.py    # 產出主管摘要
│   └── generate_case_study.py           # 產出一頁式個案報告
│
├── src/
│   ├── financial_ratios.py              # 財務比率計算
│   ├── feature_engineering.py           # 特徵工程
│   ├── anomaly_detection.py             # 異常偵測
│   ├── risk_flags.py                    # 風險旗標與風險分數
│   ├── credit_actions.py                # 授信建議行動
│   └── agent_trace.py                   # AI 建議與人工覆核紀錄
│
├── outputs/
│   ├── dashboard_credit_review.csv      # Tableau 主要資料來源
│   ├── executive_summary.csv            # Portfolio 摘要
│   ├── case_study.md                    # 高風險公司個案報告
│   └── other CSV outputs
│
├── docs/
│   ├── day_1_technical.md
│   ├── day_2_technical.md
│   ├── day_3_technical.md
│   └── sql_showcase.sql
│
├── docker-compose.yml                   # PostgreSQL 環境設定
├── requirements.txt
└── README.md
```

---

## 🔄 分析流程

```text
模擬財務資料
        ↓
資料清理與轉換
        ↓
財務比率計算
        ↓
風險旗標與異常偵測
        ↓
綜合風險分數
        ↓
建議授信行動
        ↓
CSV / PostgreSQL / Markdown 輸出
        ↓
Tableau 互動式儀表板
```

---

## 📊 Tableau Dashboard 設計

本專案使用 `outputs/dashboard_credit_review.csv` 作為 Tableau 主要資料來源。

目前 dashboard 設計重點：

### 1. 企業風險分數排名

用途：快速辨識 2024 年風險最高的公司。

可回答問題：

- 哪些公司需要優先覆審？
- 哪些公司風險分數最高？
- 哪些公司屬於 High / Critical risk？

---

### 2. 產業授信風險分布

用途：觀察風險是否集中在特定產業。

可回答問題：

- 哪些產業風險較高？
- 高風險公司是否集中在少數產業？
- Portfolio 是否有產業集中風險？

---

### 3. 企業 5 年風險趨勢

用途：追蹤公司風險是否持續惡化或改善。

可回答問題：

- 哪些公司風險逐年上升？
- 哪些公司在 2024 年突然惡化？
- 風險變化是否具有趨勢性？

---

## 🖱️ Tableau 互動功能建議

為了讓 dashboard 更像顧問交付成果，建議加入以下互動功能：

| 互動功能 | 做法 | 商業價值 |
|---|---|---|
| 年度篩選器 | 加入 `Year` filter | 讓使用者切換不同覆審年度 |
| 產業篩選器 | 加入 `Industry` filter | 快速查看特定產業風險 |
| 風險等級篩選器 | 加入 `Risk Band` / `Risk Level` filter | 聚焦 High / Critical 公司 |
| 點擊泡泡圖聯動 | Dashboard Action → Filter | 點選產業後，自動更新公司排名與趨勢圖 |
| Tooltip 說明 | 在 tooltip 加入 `suggested_action`、`review_reason` | 點到公司即可看到授信建議 |
| Highlight Action | 滑鼠移到公司名稱時 highlight 該公司趨勢 | 方便追蹤單一公司 |
| Parameter 控制指標 | 建立指標切換參數，例如 Risk Score / Debt Ratio / Altman Z' | 讓 dashboard 更有互動分析感 |

---

## 📐 風險評分邏輯

### Step 1：財務比率計算

| 指標 | 公式 | 解讀 |
|---|---|---|
| Debt Ratio | Total Liabilities / Total Assets | 衡量槓桿程度 |
| Interest Coverage | EBIT / Interest Expense | 衡量償債能力 |
| Current Ratio | Current Assets / Current Liabilities | 衡量短期流動性 |
| ROA | Net Income / Total Assets | 衡量資產獲利能力 |
| ROE | Net Income / Equity | 衡量股東權益報酬 |
| Altman Z' | 非上市企業破產風險指標 | 越低代表財務壓力越高 |

---

### Step 2：Rule-Based Risk Flags

系統會針對每家公司每一年建立風險旗標，例如：

- `flag_high_debt`：負債比過高
- `flag_low_coverage`：利息保障倍數過低
- `flag_low_liquidity`：流動比率過低
- `flag_negative_profit`：淨利為負
- `flag_revenue_decline`：營收明顯衰退
- `flag_altman_distress`：Altman Z' 低於安全門檻

---

### Step 3：綜合風險分數

```text
Combined Risk Score = Rule-Based Risk Score × 60% + Anomaly Score × 40%
```

目前 60/40 權重是 demo 用的 heuristic 設定。

在真實 production 專案中，權重應該使用歷史違約資料進行校準，例如 logistic regression、XGBoost 或其他 credit risk model。

---

## 🤖 Human-in-the-Loop 設計

本專案的核心原則是：

```text
AI 提供分析與建議，人類負責最終決策。
```

AI 可以協助：

- 快速整理財務指標
- 找出異常公司
- 產生風險摘要
- 提出授信覆審建議

但 AI 不應該直接決定：

- 是否核准授信
- 是否拒絕續貸
- 是否調整額度
- 是否要求擔保品

這樣的設計較符合金融業對模型治理、人工覆核與風險控管的要求。

---

## 📁 主要輸出檔案

| 檔案 | 用途 |
|---|---|
| `outputs/dashboard_credit_review.csv` | Tableau dashboard 主要資料來源 |
| `outputs/executive_summary.csv` | Portfolio 層級摘要 |
| `outputs/case_study.md` | 高風險公司一頁式個案報告 |
| `outputs/ratios_wide.csv` | 財務比率寬表 |
| `outputs/anomalies.csv` | 異常偵測結果 |
| `outputs/risk_flags.csv` | 風險旗標結果 |
| `logs/*.log` | Pipeline 執行紀錄 |

---

## ⚠️ 限制

| 限制 | 影響 | 未來改進方向 |
|---|---|---|
| 使用模擬資料 | 無法驗證真實違約預測能力 | 接入真實授信資料 |
| 沒有 default labels | 無法計算 AUC / KS / Gini | 使用歷史違約資料回測 |
| 權重為 heuristic | 不是正式模型校準結果 | 用 logistic regression 或 XGBoost 校準 |
| 未加入總體經濟變數 | 無法反映利率與景氣循環 | 加入 GDP、利率、產業景氣資料 |
| Tableau 主要使用 CSV | 即時資料更新能力有限 | 未來可接 PostgreSQL / data warehouse |
| 無 NLP 文件分析 | 未分析年報文字或新聞 | 未來可加入 LLM-based credit memo analysis |

---

## 🚀 未來優化方向

1. **接入真實資料來源**  
   將 synthetic data 改為真實授信資料或公開財報資料。

2. **模型校準與驗證**  
   使用歷史違約標籤校準風險分數，並加入 AUC、KS、Gini 等驗證指標。

3. **加入總體經濟變數**  
   例如利率、GDP 成長率、產業景氣指標。

4. **升級資料流程**  
   將 Python script 升級為 Airflow / dbt pipeline。

5. **強化 Tableau 互動功能**  
   加入 dashboard actions、filter、tooltip、parameter，讓使用者可以自行探索公司、產業與年度風險。

6. **加入 LLM 報告生成**  
   根據風險分數、異常原因與建議行動，自動產生授信覆審 memo 初稿。

---

## 🛠️ Setup & Quickstart

```bash
# 1. Clone repository
git clone https://github.com/JoeyTaipei/Credit_review_analytics.git
cd Credit_review_analytics

# 2. Install packages
pip install -r requirements.txt

# 3. Run full pipeline without database
python scripts/run_full_pipeline.py --skip-db

# 4. Optional: start PostgreSQL with Docker
docker-compose up -d

# 5. Optional: run full pipeline with database
python scripts/run_full_pipeline.py
```

---

## 🧪 Demo Workflow

建議面試展示順序：

```text
1. 開 GitHub README，說明商業問題與系統架構
2. 簡短展示 Python pipeline
3. 執行 python scripts/run_full_pipeline.py --skip-db
4. 打開 outputs/dashboard_credit_review.csv
5. 展示 Tableau dashboard
6. 說明 AI-assisted，不是 automated loan approval
7. 說明限制與 production improvement
```

---

## 👤 Author

Built by Joey as a portfolio project for data analyst / analytics consulting internship applications.

此專案用於展示：

- Python 資料處理能力
- 財務風險分析邏輯
- Tableau 視覺化能力
- End-to-end data pipeline thinking
- AI-assisted decision support 設計概念
- 技術結果轉換成商業語言的能力

---

## 📌 One-Sentence Summary

```text
This project demonstrates how Python, financial risk logic, and Tableau can be combined into an AI-assisted credit review workflow that helps analysts identify portfolio risk while keeping final decisions human-reviewed.
```
