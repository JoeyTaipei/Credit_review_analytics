# 企業授信覆審分析工具
**Corporate Credit Review Analytics Tool — Deloitte FSI Demo**

> Internal demo for partner review. Simplified version of the "Risk Intelligence Dashboard" service offering, built to support the credit review analyst workflow at a mid-size Taiwan commercial bank.

---

## 1. 專案目的 (Why this exists)

台灣中型商業銀行的核貸專員，每年要對既有企業授信戶做覆審。目前流程：
人工從年報、信用查詢、產業報告蒐集資料 → Excel 算財務比率 → 寫覆審意見 → 平均**4-6 小時/戶**，且不同分行品質差異大。

**這個工具的目標**：把「資料整理 + 比率計算 + 異常偵測 + 初稿撰寫」自動化，將前置分析縮短到 **30 分鐘以內**，讓核貸專員把時間花在「判斷」而非「整理」。

> 我們刻意**不**把它做成完整 production system —— 這是 demo，不是要取代核心系統。決策權永遠在持照核貸主管手上。

---

## 2. 資料夾結構

```
credit_review_tool/
├── README.md                          ← 你正在讀的這個
├── requirements.txt                   ← Python 依賴
├── src/                               ← 核心程式碼
│   ├── data_pipeline.py               ← 從 FinMind / TWSE OpenAPI 抓資料
│   ├── financial_ratios.py            ← 8+ 個財務比率 + Altman Z'
│   ├── anomaly_detection.py           ← Z-score 異常偵測
│   └── llm_summary.py                 ← LLM 覆審意見生成
├── scripts/
│   ├── generate_sample_data.py        ← 產生模擬資料（demo 用）
│   └── run_full_pipeline.py           ← 一鍵跑完整流程
├── data/
│   ├── sample_financials_long.csv     ← 模擬資料（long format）
│   └── sample_industry_medians.csv    ← 產業中位數對標
├── outputs/
│   ├── ratios_long.csv                ← 給 Tableau 的主表
│   ├── anomalies.csv                  ← 異常偵測結果
│   ├── sample_llm_input.json          ← LLM prompt 輸入範例
│   └── sample_llm_output.md           ← LLM 輸出範例
├── docs/
│   ├── executive_summary.md           ← 一頁式 SVP 摘要
│   ├── tableau_dashboard_spec.md      ← 三頁 dashboard 設計規格
│   ├── tableau_learning_roadmap.md    ← Tableau 學習計畫
│   ├── methodology_and_defense.md     ← 每個技術選擇的 defense
│   └── interview_qa.md                ← 預期 Q&A 演練
└── notebooks/
    └── exploratory_analysis.ipynb     ← 探索性分析（選做）
```

---

## 3. 快速開始 (Quick Start)

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 產生模擬資料（不需要 API key，立即可用）
python scripts/generate_sample_data.py

# 3. 跑完整 pipeline
python scripts/run_full_pipeline.py

# 4. 輸出檔案會出現在 outputs/，把 ratios_long.csv 匯入 Tableau
```

如果要用真實資料，請參考 `src/data_pipeline.py` 裡 `fetch_from_finmind()` 函式並填入 token。

---

## 4. 樣本公司組合 (Sample Portfolio)

刻意挑選跨產業，呈現比較分析能力：

| 股票代號 | 公司 | 產業 | 為何選擇 |
|---|---|---|---|
| 2330 | 台積電 | 半導體製造 | 高毛利、低槓桿，標竿案例 |
| 2317 | 鴻海 | 電子代工 | 低毛利、高週轉，OEM 典型 |
| 2308 | 台達電 | 電子零組件 | 毛利轉型中，觀察重點 |
| 2882 | 國泰金 | 金融控股 | 金融業（部分比率 N/A，獨立處理）|
| 2891 | 中信金 | 金融控股 | 同上，與國泰金做同業比較 |
| 2912 | 統一超 | 零售服務 | 高週轉、低毛利的服務業樣本 |
| 2412 | 中華電 | 電信服務 | 公用事業特性，現金流穩定 |

> ⚠️ **重要**：本 demo 使用**模擬資料**進行示範，數字僅為教學用途，不代表上述公司的實際財務數據。實際導入時請以 MOPS / 經會計師簽證之年報為準。

---

## 5. 為什麼這樣設計？(Key Design Choices)

| 問題 | 我的選擇 | 為什麼 |
|---|---|---|
| 資料來源 | FinMind + TWSE OpenAPI（demo 用模擬資料）| MOPS 直接爬蟲需 session 管理且不穩定；FinMind 是台灣 fintech 社群最常用的免費 API；正式上線時應改接 MOPS 公開 API + 銀行內部信用查詢系統 |
| 資料格式 | Long format | Tableau 對 long format 最友好；新增比率不需改 schema |
| 異常偵測模型 | Z-score（不是 Isolation Forest）| 樣本只有 7 家 × 5 年 = 35 列，sample size 不足以撐起 Isolation Forest；Z-score 結果可解釋（「這年數值偏離過去 5 年平均 2.5 個標準差」），核貸專員看得懂 |
| Altman Z 版本 | 用 Z'（私人公司版）| 雖然樣本是上市公司，但 Z' 對台灣製造業擬合較好（學界共識）；金融業不適用，明確標 N/A |
| LLM 角色 | 只做「初稿撰寫」，不做判斷 | 強制 prompt 引用儀表板數字、結尾掛人工覆核免責；防止 hallucination 是 banking 場景的硬要求 |
| Dashboard 工具 | Tableau Public | 客戶資安考量：Public 版不能傳機敏資料，但 demo 階段可分享連結；正式版需 Tableau Server 或 Power BI 內網部署 |

更詳細的 defense 見 `docs/methodology_and_defense.md`。

---

## 6. 已知限制 (What this tool is NOT)

- **不處理金融業核心比率**：銀行/保險業的資產負債結構不同，存貨/應收帳款週轉率不適用。本工具對 2882、2891 只計算 ROE、ROA，其餘標 N/A。正式版需另建金融業專用模型（NPL ratio、CAR、淨利差等）。
- **不做集團合併分析**：例如鴻海集團有眾多子公司，本工具只看母公司年報，未做合併調整。
- **不接信用查詢資料**：聯徵中心、跳票紀錄、銀行內部信用評等等都未納入。實際覆審必須有這些。
- **不做產業景氣分析**：無總體經濟變數、無產業週期判斷。Altman Z 只能告訴你「以歷史財報看，這家公司 stress 程度」，看不到「下一個半導體景氣下行週期」。
- **異常偵測的母體小**：5 年 35 個樣本，統計顯著性有限。應作為**警示系統**而非**判斷系統**。

---

## 7. 後續延伸方向 

1. 接 MOPS 真實 API，每季自動更新
2. 加入產業景氣領先指標（半導體：BB ratio、零售：消費者信心指數）
3. 風險評分模型從規則式改成監督式學習（需歷史違約資料）
4. Dashboard 加上 alert email 推播
5. 與聯徵 / 銀行內部信用評等系統打通

---

## 8. 致謝與資料來源

- 模擬資料：基於公開財報的 plausible 產生器，非真實數據
- 財務比率公式：CFA Curriculum 2024、台灣財務分析教科書（柯承恩等）
- Altman Z' 修正版：Altman, E.I. (1983, 2000)，台灣修正版參考張大成 (2003)
- LLM API：Anthropic Claude API（demo 階段；實際導入需資安評估）
