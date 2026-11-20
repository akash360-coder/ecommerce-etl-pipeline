-- query: monthly_revenue
SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.price), 2) AS revenue
FROM fact_sales AS f
JOIN dim_date AS d ON d.date_key = f.purchase_date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

-- query: top_10_product_categories_by_revenue
SELECT
    p.product_category_name_english AS category,
    ROUND(SUM(f.price), 2) AS revenue
FROM fact_sales AS f
JOIN dim_products AS p ON p.product_id = f.product_id
GROUP BY p.product_category_name_english
ORDER BY revenue DESC
LIMIT 10;

-- query: late_delivery_rate_by_seller_state
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
ORDER BY late_delivery_rate_pct DESC;

-- query: average_review_score_by_category
WITH order_categories AS (
    SELECT DISTINCT
        f.order_id,
        p.product_category_name_english AS category
    FROM fact_sales AS f
    JOIN dim_products AS p ON p.product_id = f.product_id
)
SELECT
    oc.category,
    ROUND(AVG(r.review_score), 2) AS average_review_score,
    COUNT(DISTINCT r.review_id) AS review_count
FROM order_categories AS oc
JOIN fact_reviews AS r ON r.order_id = oc.order_id
GROUP BY oc.category
ORDER BY average_review_score DESC, review_count DESC;

-- query: payment_type_mix
SELECT
    payment_type,
    ROUND(SUM(payment_value), 2) AS payment_value,
    ROUND(
        100.0 * SUM(payment_value) / (SELECT SUM(payment_value) FROM fact_payments),
        2
    ) AS payment_share_pct
FROM fact_payments
GROUP BY payment_type
ORDER BY payment_value DESC;
