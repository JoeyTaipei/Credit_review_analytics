-- ============================================================
-- SQL Showcase: Credit Review Analytics
-- 專案常用 SQL 查詢，模擬核貸專員實際會問的問題
-- ============================================================

-- Q1. 列出 2024 年所有風險評級為「高風險」或「警示」的公司
-- 商業情境：每月覆審會議要看的觀察名單
SELECT 
    ticker,
    company_name,
    industry_zh,
    risk_score,
    risk_band,
    debt_ratio,
    altman_z_prime
FROM ratios
WHERE year = 2024
  AND risk_band IN ('高風險', '警示')
ORDER BY risk_score DESC;


-- Q2. 計算每個產業在 2024 年的平均風險分數與標準差
-- 商業情境：產業別投資組合監控
SELECT 
    broad_industry_zh AS industry,
    COUNT(*) AS n_companies,
    ROUND(AVG(risk_score)::numeric, 1) AS avg_risk,
    ROUND(STDDEV(risk_score)::numeric, 1) AS stddev_risk,
    ROUND(AVG(debt_ratio)::numeric, 3) AS avg_debt_ratio
FROM ratios
WHERE year = 2024
  AND risk_score IS NOT NULL    -- 排除金融業（另採模型）
GROUP BY broad_industry_zh
ORDER BY avg_risk DESC;


-- Q3. 找出風險分數連續兩年上升的公司（趨勢惡化）
-- 商業情境：早期警訊偵測，這類公司應提前介入
WITH risk_trend AS (
    SELECT 
        ticker,
        company_name,
        year,
        risk_score,
        LAG(risk_score, 1) OVER (PARTITION BY ticker ORDER BY year) AS prev_year,
        LAG(risk_score, 2) OVER (PARTITION BY ticker ORDER BY year) AS two_years_ago
    FROM ratios
    WHERE risk_score IS NOT NULL
)
SELECT 
    ticker,
    company_name,
    two_years_ago,
    prev_year,
    risk_score AS current_year_score,
    (risk_score - two_years_ago) AS total_increase
FROM risk_trend
WHERE year = 2024
  AND risk_score > prev_year
  AND prev_year > two_years_ago
ORDER BY total_increase DESC;


-- Q4. 異常事件熱點 — 哪一年觸發最多異常？
-- 商業情境：總體經濟事件影響評估（疫情年、升息年）
SELECT 
    year,
    COUNT(DISTINCT ticker) AS affected_companies,
    COUNT(*) AS total_anomalies,
    ARRAY_AGG(DISTINCT signal) AS signal_types
FROM anomalies
WHERE is_anomaly = true
GROUP BY year
ORDER BY total_anomalies DESC;


-- Q5. 公司風險分數 vs 產業中位數的差距 — 找出產業內的離群值
-- 商業情境：相對風險評估（公司在自己產業裡是好生還是壞生？）
WITH industry_stats AS (
    SELECT 
        broad_industry_zh,
        year,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY risk_score) AS median_risk
    FROM ratios
    WHERE risk_score IS NOT NULL
    GROUP BY broad_industry_zh, year
)
SELECT 
    r.ticker,
    r.company_name,
    r.broad_industry_zh,
    r.year,
    r.risk_score,
    s.median_risk,
    (r.risk_score - s.median_risk) AS deviation_from_peer
FROM ratios r
JOIN industry_stats s 
    ON r.broad_industry_zh = s.broad_industry_zh 
    AND r.year = s.year
WHERE r.year = 2024
  AND r.risk_score IS NOT NULL
ORDER BY ABS(r.risk_score - s.median_risk) DESC
LIMIT 5;