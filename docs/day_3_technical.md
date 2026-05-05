# Day 3 — Technical Documentation
## PostgreSQL + Docker + SQLAlchemy + SQL Showcase

---

## 1. Docker Compose (`docker-compose.yml`)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: credit_review_db
    environment:
      POSTGRES_USER: credit_user
      POSTGRES_PASSWORD: credit_pass_dev
      POSTGRES_DB: credit_review
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U credit_user -d credit_review"]
      interval: 5s
      retries: 5

volumes:
  postgres_data:
```

**Technical Breakdown**
- `postgres:16-alpine` — Alpine Linux base image，比 `postgres:16` 小 70%（~80MB vs ~400MB），啟動更快，攻擊面更小
- `environment` 區塊：hardcoded 只在 dev 環境，production 應改用 `.env` + secret manager（AWS Secrets Manager / HashiCorp Vault）
- `ports: "5432:5432"` — host:container port mapping，讓 host 機器的 Python 可以連 `localhost:5432`
- `volumes: postgres_data:...` — named volume（非 bind mount），資料存在 Docker 管理的位置，容器砍掉 volume 還在（persistence）
- `healthcheck` — Docker 定期執行 `pg_isready`，確保 DB 真的可以接受連線才報 healthy，防止 pipeline 在 DB 還沒起來就嘗試寫入

---

## 2. Database Layer (`src/db.py`)

```python
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def get_engine() -> Engine:
    url = os.getenv("DB_URL")
    if not url:
        raise RuntimeError("DB_URL not set. Check .env exists.")
    return create_engine(url, pool_pre_ping=True)
```

**Technical Breakdown**
- `load_dotenv(explicit_path)` — 明確指定 .env 路徑，無論從哪個目錄執行 script 都能找到。不用隱式搜尋（`load_dotenv()` 預設找 cwd）
- `os.getenv("DB_URL")` + 明確 RuntimeError — fail-fast：不設定就立刻報錯，不讓程式帶著 None 繼續跑到後面才崩
- `create_engine(url, pool_pre_ping=True)` — `pool_pre_ping` 在每次 checkout connection 前先測試連線是否還活著，防止 connection timeout 後的 stale connection 問題
- **SQLAlchemy 的抽象層**：換資料庫（SQLite → PostgreSQL → MySQL）只改 `DB_URL`，上層程式碼不動

---

```python
def healthcheck() -> bool:
    from sqlalchemy import text
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"DB healthcheck failed: {e}")
        return False
```

**Technical Breakdown**
- `text("SELECT 1")` — SQLAlchemy 2.0 要求 raw SQL 必須用 `text()` 包裝（type safety），直接傳字串會警告
- `with engine.connect() as conn` — context manager 確保 connection 使用完自動釋放回 pool，不會 leak
- `return bool` 而非 raise exception — healthcheck 是 polling 用的，呼叫端決定要怎麼處理 False（重試 / 報錯 / 繼續）

---

## 3. Pipeline 寫入 DB

```python
# 在 run_full_pipeline.py 新增的第 9 步
engine = get_engine()
wide.to_sql("ratios",          engine, if_exists="replace", index=False)
long.to_sql("ratios_long",     engine, if_exists="replace", index=False)
anomalies.to_sql("anomalies",  engine, if_exists="replace", index=False)
fin.to_sql("financials_raw",   engine, if_exists="replace", index=False)
flagged.to_sql("risk_flags",   engine, if_exists="replace", index=False)
```

**Technical Breakdown**
- `pd.DataFrame.to_sql()` — pandas 內建的 DB 寫入，自動從 DataFrame schema 推斷 column types
- `if_exists="replace"` — 每次跑 pipeline 都整個重建 table（drop + create + insert），適合 demo。Production 應用 `"append"` + partition by year，或用 CDC（Change Data Capture）
- `index=False` — 不把 pandas 的 RangeIndex 寫進 DB（會多一個無意義的 `index` 欄位）
- 寫入 5 個 tables 的設計：每層一個 table，審計時可以查到任何一層的原始資料，不只看最終結果

---

## 4. SQL Showcase (`docs/sql_showcase.sql`)

```sql
-- Q1. 2024 年警示 / 高風險公司名單
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
```

**Technical Breakdown**
- `IN ('高風險', '警示')` — 比兩個 OR 條件可讀性高，且 PostgreSQL query planner 可以用 hash join 優化
- 這個查詢對應 dashboard Page 1 橫條圖的資料切片，面試可以說「我的 dashboard 跟 SQL 是同一個邏輯，視覺化只是 presentation layer」
- 為什麼重要：核貸主管的月度覆審會議要看這張名單

---

```sql
-- Q3. 風險分數連續兩年上升（趨勢惡化）
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
```

**Technical Breakdown**
- **CTE（Common Table Expression）`WITH ... AS (...)`** — 把子查詢命名，提高可讀性，也讓 query planner 可能做 materialization 優化
- **Window Function `LAG(value, offset) OVER (PARTITION BY ... ORDER BY ...)`**：
  - `PARTITION BY ticker` — 每家公司獨立計算，不跨公司
  - `ORDER BY year` — 按年份排序後取前 n 列的值
  - `LAG(risk_score, 1)` = 上一年；`LAG(risk_score, 2)` = 兩年前
  - 為什麼不用 self-join：self-join 需要兩次 table scan，window function 一次掃完，O(n log n) vs O(n²)
- `WHERE risk_score IS NOT NULL` — 在 CTE 就排除金融業（NaN），防止後面比較時 NULL > number 返回 NULL

---

```sql
-- Q5. 公司風險 vs 產業中位數差距
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
```

**Technical Breakdown**
- **`PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col)`** — PostgreSQL 的 ordered-set aggregate，計算連續百分位數（中位數）
  - 為什麼不用 `AVG`：中位數對離群值（展騰餐飲 76.7 分）不敏感，平均值會被拉偏
  - PostgreSQL 沒有內建 `MEDIAN()` function（MySQL 有），要用 `PERCENTILE_CONT`
- **JOIN ON 兩個條件**：`broad_industry_zh AND year` — 確保對的產業、對的年份才能配對，不能只 JOIN 一個
- `ABS(deviation)` 排序 — 正偏離（風險高於同業）和負偏離（風險低於同業）都是有意義的離群值
- `LIMIT 5` — 只看最極端的 5 家，這是 dashboard Page 1「離群值即時提醒」的 SQL 版本

---

## 5. Tableau 連 PostgreSQL

**目標**：把 dashboard data source 從本地 CSV 換成 PostgreSQL live connection，然後 Extract 成 .hyper 檔上傳 Tableau Public。

**要達成的目標**：
- Connect → To a Server → PostgreSQL → `localhost:5432` / `credit_review` / `credit_user`
- 拖入 `ratios` table（對應原來的 ratios_wide.csv）
- 現有 dashboard 用 Replace Data Source 換掉 CSV 連線
- File → Extract Data → 存成 .hyper
- 把容器停掉（`docker compose stop`），dashboard 在 Tableau Desktop 還能不能動 → **不能動 = live connection 設定正確**，之後 Extract 才有意義

**驗證方法**：
```powershell
# 停容器
docker compose stop

# 去 Tableau 試著 Refresh → 應該出現 connection error
# 這證明你的 dashboard 真的是 live 連 PostgreSQL，不是 cache

# 恢復
docker compose start
```

---

---

# Day 3 面試 Q&A

---

## 🔧 Pipeline Engineering

**Q: 為什麼用 Docker 跑 PostgreSQL 而不直接裝本機？**
> 「三個理由：(1) **環境一致性** — Docker 確保開發、測試、正式環境用完全相同的 Postgres 版本，不會有『我本機沒問題，你那邊跑不起來』 (2) **零污染** — 不需要的時候 `docker compose down` 一鍵清除，不留任何系統設定 (3) **接近生產** — 所有大型企業的 DB 都跑在容器（Kubernetes）或雲端（RDS / Cloud SQL）裡，這個工作流程跟 Deloitte client 的 infra 一致。」

**Q: `pool_pre_ping=True` 是什麼？為什麼要設？**
> 「SQLAlchemy 的 connection pool 會保留已建立的 DB 連線以便重用。但如果 DB 重啟過（或 network timeout），pool 裡的 connection 是 stale 的。`pool_pre_ping=True` 讓每次 checkout connection 前先發一個 lightweight query（`SELECT 1`），確認連線還活著，如果掛掉就自動重新建立。沒有這個的話，長時間跑的 pipeline 到後面會出現神秘的 connection error。」

**Q: `to_sql(if_exists="replace")` 跟 `"append"` 差在哪？你什麼時候該用哪個？**
> 「`replace` 是 DROP + CREATE + INSERT，每次都全部重建。`append` 是直接 INSERT，不清舊資料。Demo 和 backfill 用 `replace` — 每次跑都要有乾淨的 baseline。Production incremental load 用 `append` — 每天只加新的資料，不動歷史資料。如果要更精細，應該做 upsert（INSERT ON CONFLICT DO UPDATE），確保同一 (ticker, year) 不重複，但 pandas 的 to_sql 不直接支援，要手寫 SQL 或用 sqlalchemy ORM。」

**Q: Window function 比 self-join 快在哪？**
> 「Self-join 需要兩次 full table scan：一次掃原表，一次掃 join 的複本，然後對每列做匹配，時間複雜度 O(n²)。Window function 一次掃描，每列都能訪問 partition 內的所有值，時間複雜度 O(n log n)（因為要先排序）。對 1000 列資料，self-join 是 1,000,000 次操作，window function 是約 10,000 次。這個差距在百萬列 production data 上才會真的感受到，但 code 品質指標上 window function 代表你懂 SQL 不只是初學者。」

---

## 💰 Financial Logic

**Q: 為什麼 Q5 用 PERCENTILE_CONT 不用 AVG 算產業中位數？**
> 「我們的 portfolio 裡有展騰餐飲（76.7 分），如果只有它一家高風險戶在服務業，用 AVG 算出來的產業平均會被這個離群值大幅拉高，讓其他服務業公司（統一超、中華電）看起來比實際更有風險。中位數對離群值不敏感，更能代表『同業的正常水準』，對比才有意義。」

**Q: SQL Q3 找出的『連續兩年上升』有什麼業務意義？**
> 「Credit deterioration 通常是漸進的，不是突然從好變差。如果一家公司風險分數連兩年都在上升，代表不是一次性的壞消息，而是結構性的惡化趨勢。這種早期警訊如果只看當期快照（dashboard 橫條圖）會看不出來。這個 SQL query 是橫條圖的補充 — 告訴你哪些公司的方向不對，即使現在分數還在 medium 級別，也應該提前介入。」

---

## 📊 Dashboard / Narrative

**Q: Tableau 連 PostgreSQL 比連 CSV 好在哪？**
> 「三個層面：(1) **Single source of truth** — 所有分析工具（Tableau、Python、SQL client）都連同一個 DB，不會出現 Python 算出一個數字、Tableau 顯示另一個數字的 data drift (2) **可更新** — pipeline 重跑後 Tableau 只要 Refresh 就更新，不需要手動換 CSV 檔案 (3) **面試故事** — 說『我做了 ETL pipeline 寫進 PostgreSQL，Tableau 從 DB 讀』比說『我把 CSV 拖進 Tableau』完整地多。」

**Q: Tableau Public 不支援 live PostgreSQL connection，你怎麼處理？**
> 「先在 Tableau Desktop 設定 PostgreSQL live connection，確認資料對了，然後 File → Extract Data 把 live connection 轉成 .hyper 格式的本地 extract。Upload 到 Tableau Public 時用的是這個 extract snapshot，不是 live connection。缺點是 extract 不會自動更新，需要手動 re-extract 後重新上傳。Production 環境用 Tableau Server 就可以做 scheduled extract 自動化更新。」

**Q: Dashboard 什麼時候讓核貸主管一眼看懂？你怎麼驗證？**
> 「我給自己設的標準是：不認識這個 project 的人，30 秒之內要能說出（1）哪家公司最危險（2）哪個產業曝險最大（3）風險是在好轉還是惡化。驗證方法：請一個非金融背景的朋友看 30 秒後問他。如果他能說出展騰餐飲風險最高、製造業曝險最大、某家公司的趨勢線在往上走，代表 dashboard 設計成功了。」
