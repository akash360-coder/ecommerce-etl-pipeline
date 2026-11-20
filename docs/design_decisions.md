# Design Decisions

This project uses a star schema because the customer, product, seller, date, and ZIP-prefix dimensions support straightforward filtering and grouping while keeping descriptive attributes out of the item-level sales fact. The declared fact grains are explicit: sales has one row per order item, payments one row per payment, and reviews one row per review.

Payments and reviews remain separate facts. Joining either directly to item rows can multiply records when an order contains multiple items, payments, or reviews, which would distort sums and averages. Analyses that compare delivery outcomes with reviews first reduce sales delivery flags to order level.

Revenue is defined as `SUM(fact_sales.price)` and excludes orders whose status is `canceled` or `unavailable`. Freight is not revenue. Trend analysis also excludes 2016 and the latest incomplete month; rate/average rankings use minimum-volume thresholds to avoid unstable small samples.

SQLite provides a portable, zero-server database that is easy to run from VS Code and inspect with common tools. The loader enables foreign-key enforcement and recreates tables on each run for deterministic, idempotent loads.

Quality checks compare loaded table counts with cleaned inputs, test fact-sales foreign-key orphans, reconcile sales price and payment sums, and detect duplicate primary keys. The checks are persisted to CSV and cause the pipeline to fail when any check fails. The sample pipeline redirects data, database, logs, exports, and run metadata so it can be exercised without modifying real outputs.
