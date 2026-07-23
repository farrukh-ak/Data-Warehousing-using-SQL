# Sales Data Warehouse

An end-to-end ETL pipeline that ingests raw retail sales data, models it
into a star schema, and answers analytical questions (month-over-month
growth by category) using SQL window functions.

Built with **Python + DuckDB** - a serverless, embedded analytical
database with the same SQL surface (CTEs, window functions, joins) as
production warehouses like Snowflake or BigQuery, with zero setup cost.

## Architecture

```
Raw CSV (Superstore sales data)
      │
      ▼  Extract          (Python + pandas)
┌─────────────┐
│   BRONZE    │  raw data landed as-is, untouched
└─────────────┘
      │
      ▼  Transform         (Python)
┌─────────────┐
│   SILVER    │  cleaned types, standardized column names
└─────────────┘
      │
      ▼  Model              (SQL)
┌─────────────┐
│    GOLD     │  star schema: fact_sales + 4 dimension tables
└─────────────┘
```

**Star schema:**

```
        dim_customer        dim_product
              \                  /
               \                /
                fact_sales
               /                \
              /                  \
        dim_location          dim_date
```

`fact_sales` holds only transaction measures (revenue, quantity, discount,
profit) and foreign keys - no descriptive text is duplicated across rows.

## What's in each layer

| Layer | Table(s) | Purpose |
|---|---|---|
| Bronze | `bronze_sales` | Raw CSV landed untouched, plus load metadata |
| Silver | `silver_sales` | Fixed types (dates), standardized snake_case columns |
| Gold | `dim_customer`, `dim_product`, `dim_location`, `dim_date`, `fact_sales` | Normalized star schema |

## A real data quality bug found and fixed

While building `dim_customer`, `SELECT DISTINCT` on the full row produced
4,910 rows for only 793 unique customers. The root cause: this dataset's
`customer_id` maps to one *person*, but that person ships to a different
location on nearly every order — so `SELECT DISTINCT *` treated each
location variation as a "different" customer row.

Joining `fact_sales` naively against that broken dimension would have
silently multiplied revenue for any customer with multiple shipping
addresses — a classic and dangerous star-schema bug, since nothing
throws an error; the numbers are just wrong.

**Fix:** dimension tables are built with `GROUP BY <key> ` + `MIN()`
(picks one deterministic value per key) instead of `SELECT DISTINCT *`,
and shipping location was split into its own `dim_location` table, since
"who the customer is" and "where an order shipped" are different
dimensions with different grains.

Every Gold-layer run verifies `COUNT(*) == COUNT(DISTINCT key)` for each
dimension before considering the build successful.

## Example query: month-over-month growth by category

```sql
WITH monthly_sales AS (
    SELECT
        d.year, d.month, d.month_name,
        p.category,
        SUM(f.revenue) AS total_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.order_date_key = d.date_key
    JOIN dim_product p ON f.product_id = p.product_id
    GROUP BY d.year, d.month, d.month_name, p.category
)
SELECT
    *,
    LAG(total_revenue) OVER (
        PARTITION BY category ORDER BY year, month
    ) AS prev_month_revenue,
    ROUND(
        (total_revenue - LAG(total_revenue) OVER (PARTITION BY category ORDER BY year, month))
        / LAG(total_revenue) OVER (PARTITION BY category ORDER BY year, month) * 100,
        2
    ) AS mom_growth_pct
FROM monthly_sales
ORDER BY category, year, month;
```

This uses a CTE, two joins across the star schema, and a window function
(`LAG` + `PARTITION BY`) to compute growth without collapsing rows -
each month/category keeps its own row while still "seeing" the prior
month's value.

## Running it

```bash
pip install duckdb pandas
python run_pipeline.py
```

This runs Bronze → Silver → Gold in order and prints row counts plus
dimension key uniqueness checks at the end. The full warehouse lives in
a single file: `warehouse.duckdb`.

## Project structure

```
sales_dw/
├── data/
│   └── Sample - Superstore.csv
├── scripts/
│   ├── 01_bronze.py
│   ├── 02_silver.py
│   └── 03_gold.py
├── run_pipeline.py
├── warehouse.duckdb          (generated on run)
└── README.md
```

## Dataset

[Superstore Sales dataset](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final)
via Kaggle — ~10,000 rows of US retail order transactions, 2014-2017.

## Tech stack

- **Python** (pandas) — extract + light transform
- **DuckDB** — embedded analytical SQL warehouse
- **SQL** — star schema modeling, CTEs, window functions
