# Star Schema Data Dictionary

SQLite storage types follow `sql/create_schema.sql`. `TEXT` date/timestamp fields are stored as ISO-formatted strings; boolean flags use integer `0`/`1` values.

## Dimensions

### `dim_customers`

| Column | Type | Description |
|---|---|---|
| `customer_id` | TEXT | Olist customer-record identifier; primary key used by sales facts. |
| `customer_unique_id` | TEXT | Stable customer identity used to identify repeat buyers across records. |
| `customer_zip_code_prefix` | INTEGER | Customer's Brazilian ZIP-code prefix. |
| `customer_city` | TEXT | Normalized customer city name. |
| `customer_state` | TEXT | Normalized two-letter customer state code. |

### `dim_products`

| Column | Type | Description |
|---|---|---|
| `product_id` | TEXT | Product identifier; primary key used by sales facts. |
| `product_category_name` | TEXT | Original Portuguese category key; missing values use `unknown`. |
| `product_category_name_english` | TEXT | English category label, with `unknown` fallback. |
| `product_name_length` | REAL | Product-name character count from the source. |
| `product_description_length` | REAL | Product-description character count from the source. |
| `product_photos_qty` | REAL | Number of product photos listed. |
| `product_weight_g` | REAL | Product weight in grams. |
| `product_length_cm` | REAL | Product length in centimeters. |
| `product_height_cm` | REAL | Product height in centimeters. |
| `product_width_cm` | REAL | Product width in centimeters. |

### `dim_sellers`

| Column | Type | Description |
|---|---|---|
| `seller_id` | TEXT | Seller identifier; primary key used by sales facts. |
| `seller_zip_code_prefix` | INTEGER | Seller's Brazilian ZIP-code prefix. |
| `seller_city` | TEXT | Normalized seller city name. |
| `seller_state` | TEXT | Normalized two-letter seller state code. |

### `dim_date`

| Column | Type | Description |
|---|---|---|
| `date_key` | INTEGER | Primary key formatted as `YYYYMMDD`. |
| `full_date` | TEXT | Calendar date in ISO `YYYY-MM-DD` form. |
| `year` | INTEGER | Calendar year. |
| `quarter` | INTEGER | Calendar quarter, 1-4. |
| `month` | INTEGER | Calendar month, 1-12. |
| `month_name` | TEXT | English month name. |
| `day` | INTEGER | Day of month, 1-31. |
| `day_of_week` | INTEGER | Weekday index, Monday 0 through Sunday 6. |
| `day_name` | TEXT | English weekday name. |
| `is_weekend` | INTEGER | Weekend flag: 1 for Saturday/Sunday, otherwise 0. |

### `dim_geolocation`

| Column | Type | Description |
|---|---|---|
| `geolocation_zip_code_prefix` | INTEGER | ZIP-code prefix; primary key after coordinate aggregation. |
| `latitude` | REAL | Mean latitude for the ZIP prefix. |
| `longitude` | REAL | Mean longitude for the ZIP prefix. |
| `city` | TEXT | Normalized city associated with the ZIP prefix. |
| `state` | TEXT | Normalized two-letter state code. |

## Facts

### `fact_sales`

**Grain:** one row per order item. Composite primary key: (`order_id`, `order_item_id`).

| Column | Type | Description |
|---|---|---|
| `order_id` | TEXT | Olist order identifier. |
| `order_item_id` | INTEGER | Item sequence within the order. |
| `customer_id` | TEXT | Customer dimension foreign key. |
| `product_id` | TEXT | Product dimension foreign key. |
| `seller_id` | TEXT | Seller dimension foreign key. |
| `purchase_date_key` | INTEGER | Purchase-date dimension foreign key. |
| `order_status` | TEXT | Olist order status at extraction. |
| `price` | REAL | Item merchandise price, excluding freight. |
| `freight_value` | REAL | Item freight charge. |
| `total_item_value` | REAL | Price plus freight value. |
| `purchase_timestamp` | TEXT | Order purchase timestamp in ISO form. |
| `delivered_customer_date` | TEXT | Customer delivery timestamp; null for undelivered orders. |
| `delivery_days` | REAL | Elapsed purchase-to-delivery days. |
| `estimated_delivery_days` | REAL | Purchase-to-estimated-delivery days. |
| `delivery_delay_days` | REAL | Actual delivery date minus estimated date in days. |
| `is_late` | INTEGER | Late-delivery flag: 1 late, 0 on time, null when unavailable. |

### `fact_payments`

**Grain:** one row per payment record. Composite primary key: (`order_id`, `payment_sequential`). `order_id` is the order business identifier and is intentionally not a foreign key because the schema has no unique order-grain parent table.

| Column | Type | Description |
|---|---|---|
| `order_id` | TEXT | Olist order identifier. |
| `payment_sequential` | INTEGER | Payment sequence within the order. |
| `payment_type` | TEXT | Normalized payment method. |
| `payment_installments` | INTEGER | Number of installments for the payment. |
| `payment_value` | REAL | Amount recorded for this payment. |

### `fact_reviews`

**Grain:** one row per review. Primary key: `review_id`. `order_id` is retained as a business identifier and is not a foreign key because the schema has no unique order-grain parent table.

| Column | Type | Description |
|---|---|---|
| `review_id` | TEXT | Review identifier; primary key. |
| `order_id` | TEXT | Olist order identifier associated with the review. |
| `review_score` | INTEGER | Customer review score, generally 1-5. |
| `has_comment` | INTEGER | Comment-presence flag: 1 present, otherwise 0. |
| `review_creation_date` | TEXT | Review creation date in ISO form. |
| `review_answer_timestamp` | TEXT | Review response timestamp in ISO form. |
