"""
DASHBOARD
---------
Streamlit app that reads directly from warehouse.duckdb (the Gold layer)
and visualizes revenue, growth, and top products.

No transformation logic lives here - if a number looks wrong, the bug is
in the pipeline (scripts/), not the dashboard. The dashboard only queries
and displays.

Run with:
    streamlit run dashboard/app.py
"""

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "warehouse.duckdb"

st.set_page_config(page_title="Sales Data Warehouse", layout="wide")


@st.cache_resource
def get_connection():
    # read_only=True: the dashboard should never write to the warehouse
    return duckdb.connect(DB_PATH, read_only=True)


con = get_connection()

st.title("Sales Data Warehouse")
st.caption("Live queries against a DuckDB star schema (Bronze -> Silver -> Gold)")

# ---------------------------------------------------------------
# Filters
# ---------------------------------------------------------------
categories = con.execute("SELECT DISTINCT category FROM dim_product ORDER BY 1").fetchdf()["category"].tolist()
selected_categories = st.multiselect("Category", categories, default=categories)

if not selected_categories:
    st.warning("Select at least one category.")
    st.stop()

cat_filter = ", ".join(f"'{c}'" for c in selected_categories)

# ---------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------
kpis = con.execute(f"""
    SELECT
        SUM(f.revenue) AS total_revenue,
        SUM(f.profit) AS total_profit,
        COUNT(DISTINCT f.order_id) AS total_orders
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    WHERE p.category IN ({cat_filter})
""").fetchdf().iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Total Revenue", f"${kpis['total_revenue']:,.0f}")
col2.metric("Total Profit", f"${kpis['total_profit']:,.0f}")
col3.metric("Total Orders", f"{int(kpis['total_orders']):,}")

st.divider()

# ---------------------------------------------------------------
# Monthly revenue trend by category
# ---------------------------------------------------------------
st.subheader("Monthly Revenue by Category")

monthly = con.execute(f"""
    SELECT
        d.full_date,
        d.year,
        d.month,
        p.category,
        SUM(f.revenue) AS total_revenue
    FROM fact_sales f
    JOIN dim_date d ON f.order_date_key = d.date_key
    JOIN dim_product p ON f.product_id = p.product_id
    WHERE p.category IN ({cat_filter})
    GROUP BY d.full_date, d.year, d.month, p.category
    ORDER BY d.full_date
""").fetchdf()

# collapse to one point per year-month per category for a clean trend line
monthly["year_month"] = pd.to_datetime(
    monthly["year"].astype(str) + "-" + monthly["month"].astype(str) + "-01"
)
monthly_grouped = (
    monthly.groupby(["year_month", "category"], as_index=False)["total_revenue"].sum()
)

fig = px.line(
    monthly_grouped,
    x="year_month",
    y="total_revenue",
    color="category",
    markers=True,
    labels={"year_month": "Month", "total_revenue": "Revenue"},
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------
# Month-over-month growth table (the window function query)
# ---------------------------------------------------------------
st.subheader("Month-over-Month Growth by Category")

mom = con.execute(f"""
    WITH monthly_sales AS (
        SELECT
            d.year, d.month, d.month_name,
            p.category,
            SUM(f.revenue) AS total_revenue
        FROM fact_sales f
        JOIN dim_date d ON f.order_date_key = d.date_key
        JOIN dim_product p ON f.product_id = p.product_id
        WHERE p.category IN ({cat_filter})
        GROUP BY d.year, d.month, d.month_name, p.category
    )
    SELECT
        year, month_name, category,
        total_revenue,
        LAG(total_revenue) OVER (PARTITION BY category ORDER BY year, month) AS prev_month_revenue,
        ROUND(
            (total_revenue - LAG(total_revenue) OVER (PARTITION BY category ORDER BY year, month))
            / LAG(total_revenue) OVER (PARTITION BY category ORDER BY year, month) * 100,
            2
        ) AS mom_growth_pct
    FROM monthly_sales
    ORDER BY category, year, month
""").fetchdf()

st.dataframe(mom, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------
# Top products
# ---------------------------------------------------------------
st.subheader("Top 10 Products by Revenue")

top_products = con.execute(f"""
    SELECT
        p.product_name,
        p.category,
        SUM(f.revenue) AS total_revenue,
        SUM(f.quantity) AS total_quantity
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    WHERE p.category IN ({cat_filter})
    GROUP BY p.product_name, p.category
    ORDER BY total_revenue DESC
    LIMIT 10
""").fetchdf()

fig2 = px.bar(
    top_products.sort_values("total_revenue"),
    x="total_revenue",
    y="product_name",
    color="category",
    orientation="h",
    labels={"total_revenue": "Revenue", "product_name": "Product"},
)
st.plotly_chart(fig2, use_container_width=True)
