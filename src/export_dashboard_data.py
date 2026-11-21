"""Export tidy dashboard tables from the SQLite star schema."""

from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from src.config import (
    DASHBOARD_DATA_DIR,
    DATABASE_PATH,
    MIN_DELIVERED_ITEMS_PER_STATE,
    MIN_REVIEWS_PER_CATEGORY,
)
from src.logger import get_logger


EXPORT_QUERIES: dict[str, str] = {
    "monthly_revenue.csv": """
        WITH latest AS (
            SELECT date(MAX(purchase_timestamp), 'start of month') AS latest_month
            FROM fact_sales
        ), monthly AS (
            SELECT
                d.year,
                d.month,
                d.month_name,
                strftime('%Y-%m', d.full_date) AS year_month,
                SUM(f.price) AS revenue,
                COUNT(DISTINCT f.order_id) AS orders
            FROM fact_sales AS f
            JOIN dim_date AS d ON d.date_key = f.purchase_date_key
            CROSS JOIN latest AS l
            WHERE f.order_status NOT IN ('canceled', 'unavailable')
              AND d.year > 2016
              AND date(d.full_date, 'start of month') < l.latest_month
            GROUP BY d.year, d.month, d.month_name, year_month
        )
        SELECT
            year,
            month,
            month_name,
            year_month,
            ROUND(revenue, 2) AS revenue,
            orders,
            ROUND(revenue / NULLIF(orders, 0), 2) AS average_order_value,
            ROUND(
                100.0 * (revenue - LAG(revenue) OVER (ORDER BY year, month))
                / NULLIF(LAG(revenue) OVER (ORDER BY year, month), 0),
                2
            ) AS mom_growth_pct
        FROM monthly
        ORDER BY year, month
    """,
    "category_revenue.csv": """
        WITH category_totals AS (
            SELECT
                p.product_category_name_english AS category,
                SUM(f.price) AS revenue,
                COUNT(*) AS items,
                COUNT(DISTINCT f.order_id) AS orders
            FROM fact_sales AS f
            JOIN dim_products AS p ON p.product_id = f.product_id
            WHERE f.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY p.product_category_name_english
        )
        SELECT
            category,
            ROUND(revenue, 2) AS revenue,
            items,
            orders,
            ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS revenue_share_pct
        FROM category_totals
        ORDER BY revenue DESC
    """,
    "delivery_by_state.csv": """
        SELECT
            s.seller_state,
            COUNT(*) AS delivered_items,
            SUM(CASE WHEN f.is_late = 1 THEN 1 ELSE 0 END) AS late_items,
            ROUND(
                100.0 * SUM(CASE WHEN f.is_late = 1 THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) AS late_delivery_rate_pct
        FROM fact_sales AS f
        JOIN dim_sellers AS s ON s.seller_id = f.seller_id
        WHERE f.is_late IS NOT NULL
        GROUP BY s.seller_state
        HAVING COUNT(*) >= :minimum_delivered_items
        ORDER BY late_delivery_rate_pct DESC
    """,
    "customer_state_revenue.csv": """
        SELECT
            c.customer_state,
            ROUND(SUM(f.price), 2) AS revenue,
            COUNT(DISTINCT f.order_id) AS orders,
            COUNT(*) AS items
        FROM fact_sales AS f
        JOIN dim_customers AS c ON c.customer_id = f.customer_id
        WHERE f.order_status NOT IN ('canceled', 'unavailable')
        GROUP BY c.customer_state
        ORDER BY revenue DESC
    """,
    "review_summary.csv": """
        WITH score_counts AS (
            SELECT
                'score_distribution' AS summary_type,
                CAST(review_score AS TEXT) AS review_score,
                NULL AS category,
                COUNT(DISTINCT review_id) AS review_count,
                NULL AS average_review_score,
                ROUND(
                    100.0 * COUNT(DISTINCT review_id)
                    / SUM(COUNT(DISTINCT review_id)) OVER (),
                    2
                ) AS share_pct
            FROM fact_reviews
            WHERE review_score IS NOT NULL
            GROUP BY review_score
        ), order_categories AS (
            SELECT DISTINCT
                f.order_id,
                p.product_category_name_english AS category
            FROM fact_sales AS f
            JOIN dim_products AS p ON p.product_id = f.product_id
            WHERE f.order_status NOT IN ('canceled', 'unavailable')
        ), category_scores AS (
            SELECT
                'category_average' AS summary_type,
                NULL AS review_score,
                oc.category,
                COUNT(DISTINCT r.review_id) AS review_count,
                ROUND(AVG(r.review_score), 2) AS average_review_score,
                NULL AS share_pct
            FROM order_categories AS oc
            JOIN fact_reviews AS r ON r.order_id = oc.order_id
            WHERE r.review_score IS NOT NULL
            GROUP BY oc.category
            HAVING COUNT(DISTINCT r.review_id) >= :minimum_reviews
        )
        SELECT * FROM score_counts
        UNION ALL
        SELECT * FROM category_scores
    """,
    "payment_mix.csv": """
        WITH eligible_orders AS (
            SELECT DISTINCT order_id
            FROM fact_sales
            WHERE order_status NOT IN ('canceled', 'unavailable')
        ), payment_totals AS (
            SELECT
                p.payment_type,
                SUM(p.payment_value) AS payment_value
            FROM fact_payments AS p
            JOIN eligible_orders AS e ON e.order_id = p.order_id
            GROUP BY p.payment_type
        )
        SELECT
            payment_type,
            ROUND(payment_value, 2) AS payment_value,
            ROUND(100.0 * payment_value / SUM(payment_value) OVER (), 2)
                AS payment_share_pct
        FROM payment_totals
        ORDER BY payment_value DESC
    """,
    "sales_detail.csv": """
        SELECT
            f.order_id,
            f.order_item_id,
            f.purchase_date_key,
            f.purchase_timestamp,
            f.order_status,
            f.customer_id,
            c.customer_unique_id,
            c.customer_state,
            f.product_id,
            p.product_category_name,
            p.product_category_name_english AS category,
            f.seller_id,
            s.seller_state,
            f.price,
            f.freight_value,
            f.total_item_value,
            CASE
                WHEN f.order_status IN ('canceled', 'unavailable') THEN 0
                ELSE f.price
            END AS revenue,
            CASE
                WHEN f.order_status IN ('canceled', 'unavailable') THEN 0
                ELSE 1
            END AS revenue_eligible,
            f.delivery_days,
            f.delivery_delay_days,
            f.is_late
        FROM fact_sales AS f
        JOIN dim_customers AS c ON c.customer_id = f.customer_id
        JOIN dim_products AS p ON p.product_id = f.product_id
        JOIN dim_sellers AS s ON s.seller_id = f.seller_id
        ORDER BY f.purchase_timestamp, f.order_id, f.order_item_id
    """,
    "kpi_summary.csv": """
        WITH eligible_items AS (
            SELECT *
            FROM fact_sales
            WHERE order_status NOT IN ('canceled', 'unavailable')
        ), customer_orders AS (
            SELECT
                c.customer_unique_id,
                COUNT(DISTINCT e.order_id) AS order_count
            FROM eligible_items AS e
            JOIN dim_customers AS c ON c.customer_id = e.customer_id
            GROUP BY c.customer_unique_id
        ), eligible_reviews AS (
            SELECT DISTINCT r.review_id, r.review_score
            FROM fact_reviews AS r
            JOIN eligible_items AS e ON e.order_id = r.order_id
            WHERE r.review_score IS NOT NULL
        )
        SELECT
            'total_revenue' AS kpi_name,
            ROUND(SUM(price), 2) AS kpi_value,
            'BRL' AS kpi_unit
        FROM eligible_items
        UNION ALL
        SELECT 'total_orders', COUNT(DISTINCT order_id), 'orders'
        FROM eligible_items
        UNION ALL
        SELECT 'total_items_sold', COUNT(*), 'items'
        FROM eligible_items
        UNION ALL
        SELECT
            'average_order_value',
            ROUND(SUM(price) / NULLIF(COUNT(DISTINCT order_id), 0), 2),
            'BRL'
        FROM eligible_items
        UNION ALL
        SELECT
            'unique_customers',
            COUNT(DISTINCT c.customer_unique_id),
            'customers'
        FROM eligible_items AS e
        JOIN dim_customers AS c ON c.customer_id = e.customer_id
        UNION ALL
        SELECT
            'repeat_customer_rate_pct',
            ROUND(
                100.0 * SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                2
            ),
            'percent'
        FROM customer_orders
        UNION ALL
        SELECT
            'late_delivery_rate_pct',
            ROUND(
                100.0 * SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN is_late IS NOT NULL THEN 1 ELSE 0 END), 0),
                2
            ),
            'percent'
        FROM eligible_items
        UNION ALL
        SELECT 'average_review_score', ROUND(AVG(review_score), 2), 'score'
        FROM eligible_reviews
        UNION ALL
        SELECT
            'average_delivery_days',
            ROUND(AVG(delivery_days), 2),
            'days'
        FROM eligible_items
        WHERE delivery_days IS NOT NULL
    """,
    "monthly_delivery.csv": """
        WITH latest AS (
            SELECT date(MAX(purchase_timestamp), 'start of month') AS latest_month
            FROM fact_sales
        ), monthly_sales AS (
            SELECT
                strftime('%Y-%m', d.full_date) AS year_month,
                COUNT(*) AS delivered_items,
                SUM(CASE WHEN f.is_late = 1 THEN 1 ELSE 0 END) AS late_items,
                AVG(f.delivery_days) AS average_delivery_days
            FROM fact_sales AS f
            JOIN dim_date AS d ON d.date_key = f.purchase_date_key
            CROSS JOIN latest AS l
            WHERE f.order_status = 'delivered'
              AND d.year > 2016
              AND date(d.full_date, 'start of month') < l.latest_month
              AND f.is_late IS NOT NULL
            GROUP BY year_month
        ), monthly_review_orders AS (
            SELECT DISTINCT
                f.order_id,
                strftime('%Y-%m', d.full_date) AS year_month
            FROM fact_sales AS f
            JOIN dim_date AS d ON d.date_key = f.purchase_date_key
            CROSS JOIN latest AS l
            WHERE f.order_status = 'delivered'
              AND d.year > 2016
              AND date(d.full_date, 'start of month') < l.latest_month
        ), monthly_reviews AS (
            SELECT
                m.year_month,
                AVG(r.review_score) AS average_review_score
            FROM monthly_review_orders AS m
            JOIN fact_reviews AS r ON r.order_id = m.order_id
              AND r.review_score IS NOT NULL
            GROUP BY m.year_month
        )
        SELECT
            s.year_month,
            s.delivered_items,
            s.late_items,
            ROUND(
                100.0 * s.late_items / NULLIF(s.delivered_items, 0),
                2
            ) AS late_delivery_rate_pct,
            ROUND(s.average_delivery_days, 2) AS average_delivery_days,
            ROUND(r.average_review_score, 2) AS average_review_score
        FROM monthly_sales AS s
        LEFT JOIN monthly_reviews AS r ON r.year_month = s.year_month
        ORDER BY s.year_month
    """,
}


def export_dashboard_data(
    engine: Engine,
    output_directory: Path = DASHBOARD_DATA_DIR,
) -> dict[str, tuple[int, list[str]]]:
    """Run dashboard aggregates and write their tidy CSV files."""
    logger = get_logger(__name__)
    output_directory.mkdir(parents=True, exist_ok=True)
    query_parameters: dict[str, dict[str, int]] = {
        "delivery_by_state.csv": {
            "minimum_delivered_items": MIN_DELIVERED_ITEMS_PER_STATE
        },
        "review_summary.csv": {"minimum_reviews": MIN_REVIEWS_PER_CATEGORY},
    }
    export_details: dict[str, tuple[int, list[str]]] = {}
    with engine.connect() as connection:
        for filename, query in EXPORT_QUERIES.items():
            dataframe = pd.read_sql_query(
                text(query),
                connection,
                params=query_parameters.get(filename, {}),
            )
            output_path = output_directory / filename
            dataframe.to_csv(output_path, index=False)
            export_details[filename] = (len(dataframe), dataframe.columns.tolist())
            logger.info(
                "Exported %s: rows=%d columns=%d",
                output_path.name,
                len(dataframe),
                len(dataframe.columns),
            )
    return export_details


def main() -> None:
    """Export dashboard data from the configured SQLite database."""
    logger = get_logger(__name__)
    if not DATABASE_PATH.is_file():
        logger.error("SQLite database is missing: %s", DATABASE_PATH)
        raise SystemExit(1)

    engine = create_engine(f"sqlite:///{DATABASE_PATH.as_posix()}")
    try:
        export_dashboard_data(engine)
        logger.info("Dashboard data export completed successfully.")
    except Exception as error:
        logger.error("Dashboard data export failed: %s", error)
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
