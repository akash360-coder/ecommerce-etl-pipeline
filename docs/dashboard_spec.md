# Olist E-commerce Dashboard Build Specification

## Scope and Dataset Rules

The dashboard has three pages and uses exports from `dashboard/data/`. Canceled and unavailable orders are excluded from revenue and eligible order/item metrics. Trend exports exclude 2016 and the latest incomplete month. Seller-state and category visuals retain their configured minimum-volume thresholds. `sales_detail.csv` is regenerable and is not committed.

### Global Design

- **Palette:** Navy `#0B3C5D`, blue `#2878B5`, teal `#2A9D8F`, gold `#E9C46A`, orange `#F4A261`, red `#D1495B`, light neutral `#F3F6F8`, dark text `#24323D`.
- The palette is readable for common color-vision deficiencies; never encode a metric by red/green alone.
- Use 16:9 page size, 12–16 px body text, 22–28 px titles, and light gray backgrounds with white cards.
- Tooltips show exact values and totals. Use percent formats to two decimals and BRL values to two decimals.
- Apply slicers to all pages where supported: **year-month range**, **customer state**, and **category**.

## Page 1: Executive Overview

**Title:** E-commerce Performance at a Glance
**Subtitle:** Revenue and demand for eligible orders, with complete trend months only

```text
+-----------------------------+-----------------------------+
| KPI Cards: Revenue | Orders | KPI Cards: AOV | Customers |
+--------------------------------+----------------------------+
| Monthly Revenue + MoM Growth   | Revenue by Top Categories  |
|                                |                            |
+--------------------------------+----------------------------+
| Payment Mix                                                    |
+----------------------------------------------------------------+
```

1. **KPI cards**
   - **Visual:** 6-card row: total revenue, total orders, items sold, average order value, unique customers, repeat-customer rate.
   - **CSV/fields:** `kpi_summary.csv`; `kpi_name`, `kpi_value`, `kpi_unit`.
   - **Sort/order:** Cards in the listed KPI order.
   - **Filters:** Customer state and category; apply where a KPI source supports those fields. year-month range also filters transaction-backed measures.
   - **Takeaway:** The headline should show scale, basket value, customer breadth, and retention.

2. **Monthly revenue trend**
   - **Visual:** Line chart with `revenue` and a small line or card for `mom_growth_pct`.
   - **CSV/fields:** `monthly_revenue.csv`; `year_month`, `revenue`, `mom_growth_pct`.
   - **Sort/order:** Ascending `year_month`.
   - **Filters:** Year-month slicer only unless category/customer drill-through is available.
   - **Takeaway:** Revenue direction and month-over-month inflection points are visible immediately.

3. **Revenue by top categories**
   - **Visual:** Horizontal bar chart.
   - **CSV/fields:** `category_revenue.csv`; `category`, `revenue`, `revenue_share_pct`.
   - **Sort/order:** Descending revenue; show top 10.
   - **Filters:** Customer state; category slicer can select a category rather than hide the ranking.
   - **Takeaway:** A small number of categories should explain most visible revenue.

4. **Payment mix**
   - **Visual:** Donut or 100% stacked bar.
   - **CSV/fields:** `payment_mix.csv`; `payment_type`, `payment_value`, `payment_share_pct`.
   - **Sort/order:** Descending `payment_value`.
   - **Filters:** Year-month range and customer state.
   - **Takeaway:** Viewers should see which payment method carries the largest share.

## Page 2: Delivery and Customer Experience

**Title:** Delivery Reliability and Customer Experience
**Subtitle:** Seller-state risk, late-delivery trends, and review differences

```text
+------------------------------+------------------------------+
| Late Rate by Seller State    | Monthly Late-Delivery Trend |
| Map or horizontal bar        |                              |
+------------------------------+------------------------------+
| Avg Review: On-time vs Late  | Review Score Distribution    |
|                              |                              |
+------------------------------+------------------------------+
```

1. **Late delivery rate by seller state**
   - **Visual:** Brazil state choropleth or horizontal bar fallback.
   - **CSV/fields:** `delivery_by_state.csv`; `seller_state`, `late_delivery_rate_pct`, `delivered_items`.
   - **Sort/order:** Descending late rate in bar mode; choropleth alphabetic state legend.
   - **Filters:** Seller-state minimum threshold is pre-applied; year-month slicer and customer state are optional.
   - **Takeaway:** States with the highest sustained late rate are the clearest operational risks.

2. **Monthly late-delivery trend**
   - **Visual:** Line chart.
   - **CSV/fields:** `monthly_delivery.csv`; `year_month`, `late_delivery_rate_pct`.
   - **Sort/order:** Ascending `year_month`.
   - **Filters:** Year-month range.
   - **Takeaway:** The trend shows whether late delivery is improving or deteriorating.

3. **Average review score: on-time vs late**
   - **Visual:** Clustered bar or KPI pair.
   - **CSV/fields:** `sales_detail.csv`; join reviews to order IDs externally or in the data model; calculate fields with `is_late` and review score.
   - **Sort/order:** On-time, late.
   - **Filters:** Year-month range, customer state, category.
   - **Takeaway:** Late deliveries should reveal the gap in customer satisfaction.

4. **Review score distribution**
   - **Visual:** Column chart.
   - **CSV/fields:** `review_summary.csv`; filter `summary_type = "score_distribution"`; `review_score`, `review_count`, `share_pct`.
   - **Sort/order:** Review score ascending 1–5.
   - **Filters:** Year-month range only if available through the model.
   - **Takeaway:** The distribution shows whether satisfaction is concentrated at 5 stars or spread across poor scores.

## Page 3: Products and Customers

**Title:** Product and Customer Concentration
**Subtitle:** Top categories, geographic demand, and repeat purchasing

```text
+--------------------------------+-------------------------------+
| Top 10 Categories              | Revenue by Customer State     |
|                                | Map or bar                    |
+--------------------------------+-------------------------------+
| Repeat vs One-time Customers                                  |
+---------------------------------------------------------------+
```

1. **Top 10 categories**
   - **Visual:** Horizontal bar chart.
   - **CSV/fields:** `category_revenue.csv`; `category`, `revenue`, `items`.
   - **Sort/order:** Descending revenue; top 10.
   - **Filters:** Customer state and year-month range.
   - **Takeaway:** The leading categories are the clearest merchandising priorities.

2. **Revenue by customer state**
   - **Visual:** Brazil state choropleth or horizontal bar fallback.
   - **CSV/fields:** `customer_state_revenue.csv`; `customer_state`, `revenue`, `orders`.
   - **Sort/order:** Descending revenue in bar mode.
   - **Filters:** Category and year-month range.
   - **Takeaway:** Revenue is concentrated in a few customer states.

3. **Repeat vs one-time customers**
   - **Visual:** 100% stacked bar or two-card donut.
   - **CSV/fields:** `sales_detail.csv`; `customer_unique_id`, distinct `order_id`, `revenue`.
   - **Sort/order:** Repeat customers then one-time customers.
   - **Filters:** Year-month range and customer state.
   - **Takeaway:** Repeat purchasing is shown beside the share of customers who placed only one eligible order.

## Power BI

### Data Model

Import these CSVs:

- `kpi_summary.csv`
- `monthly_revenue.csv`
- `monthly_delivery.csv`
- `category_revenue.csv`
- `customer_state_revenue.csv`
- `delivery_by_state.csv`
- `review_summary.csv`
- `payment_mix.csv`
- `sales_detail.csv`

Use `sales_detail.csv` as the fact table for transaction and customer fields. Import `kpi_summary.csv` and `monthly_*`/summary tables as reporting tables. No prebuilt relationship is required between aggregate CSVs; if using both aggregate and detail tables in one visual, keep them on separate visual contexts or derive the measure from the detail table. Optionally create a `YearMonth` table from `monthly_revenue.csv` and relate it to `sales_detail[YearMonth]` for consistent month slicing. Create state lookup tables only if Brazilian map geometry requires them.

### DAX Measures

```dax
Revenue = SUM(sales_detail[revenue])

Orders = DISTINCTCOUNT(sales_detail[order_id])

AOV = DIVIDE([Revenue], [Orders])

MoM Growth % =
VAR CurrentRevenue = [Revenue]
VAR PreviousRevenue =
    CALCULATE(
        [Revenue],
        DATEADD('YearMonth'[MonthStart], -1, MONTH)
    )
RETURN
    DIVIDE(CurrentRevenue - PreviousRevenue, PreviousRevenue)

Late Delivery Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(sales_detail), sales_detail[is_late] = 1),
    CALCULATE(COUNTROWS(sales_detail), sales_detail[is_late] <> BLANK())
)

Average Review Score =
AVERAGE(review_summary[average_review_score])
```

For review score on-time vs late, use a review/order bridge modeled from `sales_detail` and `fact_reviews`; otherwise read the pre-exported review summary and clearly label it as the source grain.

## Tableau Public

### Calculated Fields

- **Revenue:** `SUM([revenue])`
- **Orders:** `COUNTD([order_id])`
- **AOV:** `SUM([revenue]) / COUNTD([order_id])`
- **MoM Growth %:** `(SUM([revenue]) - LOOKUP(SUM([revenue]), -1)) / ABS(LOOKUP(SUM([revenue]), -1))`
- **Late Delivery Rate %:** `SUM([is_late]) / COUNT([is_late])`
- **Average Review Score:** `AVG([review_score])`
- **Repeat Customer:** `IF COUNTD([order_id]) > 1 THEN "Repeat" ELSE "One-time" END`, aggregated at customer unique ID level.
- **Year-Month:** `DATETRUNC('month', DATETIME([purchase_timestamp]))`
- **On-time/Late:** `IF [is_late] = 1 THEN "Late" ELSE "On-time" END`

Import aggregate CSVs for their prepared visuals and `sales_detail.csv` for detail-level calculations. Tableau data joins are optional: separate worksheets should source the prepared aggregate relevant to that view. For state maps, join or associate the state abbreviation to Tableau's geographic role.

## Build Checklist

- [ ] Confirm all CSVs pass `python -m src.check_dashboard_data`
- [ ] Import and label fields with correct number/date geographic types
- [ ] Add the year-month, customer-state, and category slicers or filters
- [ ] Build KPI cards and validate totals against `kpi_summary.csv`
- [ ] Build Page 1: executive overview
- [ ] Build Page 2: delivery and customer experience
- [ ] Build Page 3: products and customers
- [ ] Verify canceled/unavailable orders are excluded
- [ ] Verify trend charts start after 2016 and omit the incomplete month
- [ ] Check cross-page titles, subtitles, tooltips, and color consistency
- [ ] Verify all charts sort as specified
- [ ] Export or screenshot for README validation

## Publishing and Screenshots

### Tableau Public

1. Sign in to Tableau Public and publish the workbook.
2. Choose a descriptive title and add a short data-source description.
3. Set a visible dashboard and disable unnecessary interactive elements that expose data accidentally.
4. Copy the public share URL into the main README live-dashboard placeholder.
5. Capture each page at 16:9 and save `docs/images/dashboard_overview.png` for the Executive Overview.

### Power BI

1. Save the source `.pbix` outside this Git repository, unless the file is intentionally small and approved for version control.
2. Export the Executive Overview to PDF or use a page screenshot.
3. Save the Executive Overview screenshot at `docs/images/dashboard_overview.png`.
4. Publish to Power BI if a workspace is available, or provide a local `.pbix` link outside Git.
5. Copy the public or shared report link into the main README live-dashboard placeholder.
