# ✅ 10 天專案完成計畫｜Deloitte Video Interview 版

## 核心判斷

這週四只是 video interview，不需要現場展示完整 demo。  
你的目標不是「加最多技術」，而是能清楚說明：

```text
我做了什麼 → 為什麼這樣做 → 對企業有什麼價值 → 下一步怎麼改
```

---

## 不建議現在硬加 LangChain / RAG

原因：

1. 目前資料是結構化財務資料，主要問題是 risk scoring，不是文件檢索。
2. RAG 適合用在大量非結構化文件，例如年報、新聞、授信合約、產業報告。
3. 若現在硬加 RAG，面試官可能會問「為什麼這裡需要 RAG？」反而增加風險。
4. 10 天內更值得做的是：README、interview story、Tableau interactivity、auto-generated report。

---

## 正確的 AI 擴充方向

先做：

```text
Structured data → Auto-generated credit review report
```

未來再做：

```text
Annual reports / news / credit memos → RAG Q&A
```

面試時可以這樣說：

```text
I did not add RAG yet because the current project mainly uses structured financial data. 
RAG would be more valuable in the next phase when we integrate annual reports, news, or internal credit memos.
```

---

## 優先順序

### Priority 1：README 改成繁中

已完成。請把 `README_zh.md` 改名成 `README.md` 後放到 project root。

---

### Priority 2：加入 auto-generated reports

新增：

```text
scripts/generate_company_reports.py
```

執行：

```powershell
python scripts/generate_company_reports.py
```

它會：

```text
1. 讀取 outputs/dashboard_credit_review.csv
2. 自動產生 reports/<ticker>_<year>_credit_review.md
3. 在 dashboard_credit_review.csv 加上 report_path / report_url
```

---

### Priority 3：Tableau 加互動

最值得做的 4 個：

```text
1. Year filter
2. Risk Band filter
3. Industry filter
4. Dashboard Action：點泡泡圖 → 其他圖跟著篩選
```

---

## Auto-generated report 在 Tableau 哪裡點？

Tableau 不能直接點按鈕去執行 Python。  
正確做法是：

```text
先用 Python 產生 reports/*.md
再讓 Tableau 顯示 report_path 或 report_url
```

### 做法 A：Tooltip 顯示報告路徑

在 Tableau 的公司風險排名圖或泡泡圖：

```text
Marks → Tooltip
```

加入：

```text
Company: <Company Name>
Risk Score: <Risk Score>
Suggested Action: <suggested_action>
Report: <report_path>
```

這是最簡單、最穩定的做法。

### 做法 B：URL Action 打開 GitHub report

如果你把 reports/ push 到 GitHub，並且 dashboard_credit_review.csv 有 `report_url` 欄位：

```text
Dashboard → Actions → Add Action → Go to URL
```

URL 欄位選：

```text
<report_url>
```

使用者點公司後，就可以打開該公司的 Markdown report。

---

## 10 天排程

### Day 1–2：Video interview 準備

- 背 30 秒中文 pitch
- 背 60 秒英文 pitch
- 背 10 題 Q&A
- README 改成繁中
- GitHub 首頁看起來乾淨

### Day 3–4：Auto-generated report

- 加 `generate_company_reports.py`
- 產生 `reports/*.md`
- CSV 增加 `report_path`
- README 補上 reports 說明

### Day 5–6：Tableau 互動

- 加 Year filter
- 加 Risk Band filter
- 加 Industry filter
- 加 dashboard action
- Tooltip 加 suggested_action / review_reason / report_path

### Day 7–8：整理 GitHub

- 加 `.gitignore`
- 移除不必要 logs
- 檢查 README 圖片或 dashboard screenshot
- 確認一鍵 pipeline 能跑

### Day 9–10：錄 3 分鐘 demo

Demo 流程：

```text
1. 商業問題
2. Python pipeline
3. Tableau dashboard
4. Auto-generated report
5. 限制與下一步
```

---

## 面試一句話版本

```text
I focused on building a practical AI-assisted analytics workflow instead of adding RAG too early. 
The current version analyzes structured financial data, generates risk scores, creates Tableau dashboard outputs, and auto-generates credit review reports. 
RAG would be a logical next step when unstructured documents such as annual reports or credit memos are added.
```
