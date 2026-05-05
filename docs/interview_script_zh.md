# 🎤 Deloitte Data Analyst Intern 面試腳本
## 年度授信覆審 AI 分析工具｜繁中面試版

> 使用方式：  
> 這份文件不是要逐字背，而是幫你在 video interview 中講得清楚。  
> 面試時重點是：**我做了什麼 → 為什麼這樣做 → 對企業有什麼價值**。

---

## 0. 面試定位

我不會把這個專案包裝成「完整的自動核貸系統」。

我會把它定位成：

```text
AI-assisted credit review analytics tool
```

也就是：

```text
用 Python + 財務風險邏輯 + Tableau dashboard，
協助授信分析師在年度覆審時更快找出高風險公司。
```

最重要的一句話：

```text
這不是 automated loan approval，而是 AI-assisted decision support。
AI 協助分析，人類負責最終決策。
```

---

## 1. 30 秒中文自我介紹專案

```text
我做了一個 AI 輔助的授信覆審分析工具，目標是模擬金融機構在年度授信覆審時，如何用資料分析快速找出高風險公司。

這個系統會讀取 9 家公司、5 年的模擬財務資料，自動計算負債比、利息保障倍數、Altman Z' Score 等財務指標，並結合風險旗標和異常偵測，產出每家公司的風險分數與建議行動。

最後我把結果輸出成 CSV，並用 Tableau 做成 dashboard，呈現公司風險排名、產業風險分布，以及 5 年風險趨勢。

這個專案的重點不是取代授信人員，而是協助分析師更快整理資料、辨識風險，並準備覆審報告。
```

---

## 2. 60 秒英文版本

```text
I built an AI-assisted credit review analytics tool to simulate how a financial institution could support its annual credit review process with data analytics.

The pipeline uses five years of synthetic financial data across nine companies. It automatically calculates financial ratios such as debt ratio, interest coverage, and Altman Z' Score. Then it combines rule-based risk flags with anomaly detection to generate a risk score and suggested credit actions for each company.

The final output is a Tableau dashboard showing company risk ranking, industry risk distribution, and five-year risk trends. The system also generates structured CSV outputs and Markdown credit review reports.

The key design idea is human-in-the-loop. This is not an automated loan approval system. The AI helps analysts identify risks and prepare review materials, but the final credit decision should still be made by human reviewers.

I designed this project to show my ability to connect Python data pipelines, financial risk logic, dashboard visualization, and business communication.
```

---

## 3. 如果被問：你在這個專案做了什麼？

```text
我做了四個部分。

第一，我用 Python 建立資料 pipeline，從模擬財務資料開始，做資料清理、財務比率計算、風險旗標和異常偵測。

第二，我設計了一個風險評分邏輯，把 rule-based signals 和 anomaly score 結合起來，產生每家公司的 risk score。

第三，我輸出 dashboard_credit_review.csv 給 Tableau 使用，建立互動式 dashboard，讓使用者可以從 portfolio 層級 drill down 到公司與產業層級。

第四，我加入自動產生報告的功能，將結構化風險資料轉成 Markdown credit review report，模擬顧問或授信分析師會交付的一頁式摘要。
```

---

## 4. 如果被問：為什麼不用真實資料？

```text
因為授信資料涉及客戶隱私、金融機構內部資訊和資料授權問題，所以我使用模擬資料展示系統設計。

這個專案的目標不是證明模型在真實世界的 default prediction accuracy，而是展示我能設計完整的 data analytics workflow，包括資料處理、風險邏輯、dashboard 和商業解讀。

如果是真實專案，我會依照客戶授權、資料治理和保密規範來處理真實資料。
```

---

## 5. 如果被問：為什麼不用 LangChain / RAG？

```text
我目前沒有硬加 LangChain 或 RAG，因為這個專案的主要資料是結構化財務資料，不是大量非結構化文件。

RAG 比較適合用在大量文件檢索，例如授信合約、年報、新聞、產業報告。如果現在硬加 RAG，反而會讓技術選擇和 business problem 不匹配。

所以我目前選擇先把結構化資料分析做扎實：Python pipeline、風險評分、Tableau dashboard 和自動報告生成。

未來如果加入年報或新聞資料，我會再考慮用 RAG 讓分析師可以查詢：這家公司去年管理層提到哪些營運風險？
```

---

## 6. 如果被問：Auto-generated report 是什麼？

```text
Auto-generated report 是把結構化分析結果轉成一頁式授信覆審摘要。

例如系統會根據某家公司 2024 年的 risk score、risk level、財務比率、異常訊號和 suggested action，自動產生 Markdown 報告。

這個功能的價值是減少分析師寫報告的時間，讓他們不用從零開始整理資料，而是先拿到一份 draft，再由人工覆核和修改。
```

---

## 7. 如果被問：Tableau dashboard 怎麼設計？

```text
我用三個問題設計 dashboard。

第一，哪家公司風險最高？所以我做了公司風險分數排名。

第二，風險集中在哪些產業？所以我做了產業風險分布圖。

第三，風險是變好還是變差？所以我做了 5 年風險趨勢折線圖。

接下來我會加入互動功能，例如年度篩選、風險等級篩選、產業點選聯動，讓使用者可以從 portfolio view drill down 到 company view。
```

---

## 8. 如果被問：這是不是自動核貸？

```text
不是。這是 AI-assisted decision support，不是 automated loan approval。

AI 的角色是幫助分析師整理資料、計算風險、提出建議行動。最後是否續貸、降額、提高擔保品或進一步覆審，仍然要由授信人員或授信委員會決定。

這樣設計比較符合金融業對模型治理、人工覆核和風險控管的要求。
```

---

## 9. 如果被問：這個專案有什麼限制？

```text
最大的限制是資料是模擬的，沒有真實違約標籤，所以不能證明模型真的可以預測 default。

第二，風險權重目前是 heuristic，不是用歷史資料訓練出來的。

第三，沒有加入總體經濟因素，例如利率、GDP 或產業景氣循環。

所以我會把這個專案定位成 proof of concept。它展示的是 data pipeline、風險邏輯、dashboard 和 business communication，而不是 production-ready credit risk model。
```

---

## 10. 如果被問：接下來 10 天你會怎麼改？

```text
我會做三件事。

第一，優化 README 和 interview story，讓專案目的、架構和商業價值更清楚。

第二，強化 Tableau dashboard 的互動性，例如 Year filter、Risk Band filter、Industry filter 和 dashboard action。

第三，完善 auto-generated report，讓每家公司都可以產出一頁式 credit review memo，並在 dashboard 裡透過 tooltip 或 URL action 連到報告。

我會先把現有功能做穩，不會為了履歷硬加和問題不匹配的技術。
```

---

## 11. 面試前最後 10 分鐘只背這段

```text
我的專案是一個 AI-assisted credit review analytics tool。

它用 9 家公司、5 年模擬財務資料，計算財務比率、風險旗標、異常偵測和建議行動。

我用 Python 建立資料流程，用 Tableau 做 dashboard，呈現公司風險排名、產業風險分布和 5 年風險趨勢。

我也加入 auto-generated report，把結構化風險資料轉成一頁式授信覆審摘要。

這不是自動核貸，而是輔助分析師做年度授信覆審。

我想展示的是：我能把資料處理、金融風險邏輯、視覺化和商業溝通整合成一個完整的 data analytics project。
```
