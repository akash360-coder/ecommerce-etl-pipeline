PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_reviews;
DROP TABLE IF EXISTS fact_payments;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_geolocation;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_sellers;
DROP TABLE IF EXISTS dim_products;
DROP TABLE IF EXISTS dim_customers;

CREATE TABLE dim_customers (
    customer_id TEXT PRIMARY KEY NOT NULL,
    customer_unique_id TEXT,
    customer_zip_code_prefix INTEGER,
    customer_city TEXT,
    customer_state TEXT
);

CREATE TABLE dim_products (
    product_id TEXT PRIMARY KEY NOT NULL,
    product_category_name TEXT,
    product_category_name_english TEXT,
    product_name_length REAL,
    product_description_length REAL,
    product_photos_qty REAL,
    product_weight_g REAL,
    product_length_cm REAL,
    product_height_cm REAL,
    product_width_cm REAL
);

CREATE TABLE dim_sellers (
    seller_id TEXT PRIMARY KEY NOT NULL,
    seller_zip_code_prefix INTEGER,
    seller_city TEXT,
    seller_state TEXT
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY NOT NULL,
    full_date TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);

CREATE TABLE dim_geolocation (
    geolocation_zip_code_prefix INTEGER PRIMARY KEY NOT NULL,
    latitude REAL,
    longitude REAL,
    city TEXT,
    state TEXT
);

CREATE TABLE fact_sales (
    order_id TEXT NOT NULL,
    order_item_id INTEGER NOT NULL,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    purchase_date_key INTEGER NOT NULL,
    order_status TEXT,
    price REAL NOT NULL,
    freight_value REAL NOT NULL,
    total_item_value REAL NOT NULL,
    purchase_timestamp TEXT NOT NULL,
    delivered_customer_date TEXT,
    delivery_days REAL,
    estimated_delivery_days REAL,
    delivery_delay_days REAL,
    is_late INTEGER CHECK (is_late IN (0, 1)),
    PRIMARY KEY (order_id, order_item_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customers (customer_id),
    FOREIGN KEY (product_id) REFERENCES dim_products (product_id),
    FOREIGN KEY (seller_id) REFERENCES dim_sellers (seller_id),
    FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE fact_payments (
    order_id TEXT NOT NULL,
    payment_sequential INTEGER NOT NULL,
    payment_type TEXT,
    payment_installments INTEGER,
    payment_value REAL NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE fact_reviews (
    review_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    review_score INTEGER,
    has_comment INTEGER NOT NULL CHECK (has_comment IN (0, 1)),
    review_creation_date TEXT,
    review_answer_timestamp TEXT
);

CREATE INDEX idx_fact_sales_customer_id ON fact_sales (customer_id);
CREATE INDEX idx_fact_sales_product_id ON fact_sales (product_id);
CREATE INDEX idx_fact_sales_seller_id ON fact_sales (seller_id);
CREATE INDEX idx_fact_sales_purchase_date_key ON fact_sales (purchase_date_key);
CREATE INDEX idx_fact_payments_order_id ON fact_payments (order_id);
CREATE INDEX idx_fact_reviews_order_id ON fact_reviews (order_id);
