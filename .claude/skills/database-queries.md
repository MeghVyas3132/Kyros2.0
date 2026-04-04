# Database Queries

Essential PostgreSQL queries for debugging and analyzing Kyros data.

## Connection

```bash
# Via docker-compose
docker-compose exec postgres psql -U kyros -d kyros_dev

# Direct
psql postgresql://kyros:kyros_dev_password@localhost:5432/kyros_dev
```

## Brand Context

Most queries need `brand_id`. Get it first:

```sql
-- List brands
SELECT id, name, code FROM brands;

-- Or get from current user
SELECT brand_id FROM users WHERE email = 'user@example.com';
```

## Data Availability Checks

### Verify All Required Data Exists

```sql
-- Complete data inventory
SELECT 'Buy File (GRN)' as source, COUNT(*) as rows FROM grn_line WHERE brand_id = :brand_id
UNION ALL
SELECT 'Sales History', COUNT(*) FROM sales_data WHERE brand_id = :brand_id
UNION ALL
SELECT 'Stores', COUNT(*) FROM stores WHERE brand_id = :brand_id
UNION ALL
SELECT 'Store Grades', COUNT(*) FROM store_grades WHERE brand_id = :brand_id
UNION ALL
SELECT 'SKUs', COUNT(*) FROM skus WHERE brand_id = :brand_id
UNION ALL
SELECT 'Size Guides', COUNT(*) FROM size_guides WHERE brand_id = :brand_id
UNION ALL
SELECT 'Uploads', COUNT(*) FROM uploads WHERE brand_id = :brand_id;
```

### Sales Data Deep Dive

```sql
-- Sales coverage by week
SELECT
    DATE_TRUNC('week', week_start_date) as week,
    COUNT(*) as records,
    SUM(units_sold) as total_units
FROM sales_data
WHERE brand_id = :brand_id
GROUP BY 1
ORDER BY 1 DESC
LIMIT 20;

-- Sales by store (top 10)
SELECT
    s.name as store_name,
    COUNT(*) as sales_records,
    SUM(sd.units_sold) as total_units
FROM sales_data sd
JOIN stores s ON s.id = sd.store_id
WHERE sd.brand_id = :brand_id
GROUP BY s.name
ORDER BY total_units DESC
LIMIT 10;

-- Sales by SKU (top 10)
SELECT
    sku.sku_code,
    sku.style_code,
    sku.color_code,
    COUNT(*) as sales_records,
    SUM(sd.units_sold) as total_units
FROM sales_data sd
JOIN skus sku ON sku.id = sd.sku_id
WHERE sd.brand_id = :brand_id
GROUP BY sku.sku_code, sku.style_code, sku.color_code
ORDER BY total_units DESC
LIMIT 10;
```

## Allocation Analysis

### Latest Allocation Summary

```sql
-- Latest allocation
SELECT
    a.id,
    a.name,
    a.status,
    a.created_at,
    COUNT(al.id) as total_lines,
    SUM(al.grn_qty) as total_grn,
    SUM(al.recommended_qty) as total_recommended,
    SUM(al.final_qty) as total_final,
    AVG(CASE WHEN al.ai_reasoning IS NOT NULL THEN 1.0 ELSE 0 END) * 100 as pct_with_reasoning
FROM allocations a
LEFT JOIN allocation_lines al ON al.allocation_id = a.id
WHERE a.brand_id = :brand_id
GROUP BY a.id, a.name, a.status, a.created_at
ORDER BY a.created_at DESC
LIMIT 5;
```

### Allocation Line Details

```sql
-- Top 20 allocations by recommended qty
SELECT
    al.id,
    s.name as store_name,
    sku.sku_code,
    sku.style_code,
    sku.color_code,
    al.grn_qty,
    al.recommended_qty,
    al.final_qty,
    al.ai_reasoning->>'ros_source' as ros_source,
    al.ai_reasoning->>'store_grade' as grade,
    (al.ai_reasoning->>'weekly_ros')::float as ros,
    (al.ai_reasoning->>'cover_target_weeks')::float as cover_weeks
FROM allocation_lines al
JOIN stores s ON s.id = al.store_id
JOIN skus sku ON sku.id = al.sku_id
WHERE al.allocation_id = :allocation_id
ORDER BY al.recommended_qty DESC
LIMIT 20;
```

### Explainability Check

```sql
-- Reasoning completeness
SELECT
    COUNT(*) as total_lines,
    COUNT(CASE WHEN ai_reasoning IS NULL THEN 1 END) as null_reasoning,
    COUNT(CASE WHEN ai_reasoning->>'weekly_ros' IS NULL THEN 1 END) as missing_ros,
    COUNT(CASE WHEN ai_reasoning->>'narrative_demand' IS NULL THEN 1 END) as missing_demand_narrative,
    COUNT(CASE WHEN ai_reasoning->>'size_split' IS NULL THEN 1 END) as missing_size_split,
    COUNT(CASE WHEN ai_reasoning->>'ros_source' IS NULL THEN 1 END) as missing_ros_source
FROM allocation_lines
WHERE allocation_id = :allocation_id;
```

## Store Analysis

```sql
-- Store grades distribution
SELECT
    sg.grade,
    COUNT(*) as store_count,
    STRING_AGG(s.name, ', ' ORDER BY s.name) as stores
FROM store_grades sg
JOIN stores s ON s.id = sg.store_id
WHERE sg.brand_id = :brand_id
GROUP BY sg.grade
ORDER BY
    CASE sg.grade
        WHEN 'A+' THEN 1
        WHEN 'A' THEN 2
        WHEN 'B' THEN 3
        WHEN 'C' THEN 4
        ELSE 5
    END;

-- Stores without grades
SELECT s.id, s.name, s.code
FROM stores s
LEFT JOIN store_grades sg ON sg.store_id = s.id AND sg.brand_id = :brand_id
WHERE s.brand_id = :brand_id
    AND sg.id IS NULL;

-- Store sales velocity
SELECT
    s.name,
    s.code,
    COUNT(sd.id) as weeks_with_sales,
    SUM(sd.units_sold) as total_units,
    ROUND(SUM(sd.units_sold)::numeric / NULLIF(COUNT(sd.id), 0), 2) as avg_weekly_units
FROM stores s
LEFT JOIN sales_data sd ON sd.store_id = s.id AND sd.brand_id = :brand_id
WHERE s.brand_id = :brand_id
GROUP BY s.id, s.name, s.code
ORDER BY avg_weekly_units DESC NULLS LAST
LIMIT 20;
```

## SKU Analysis

```sql
-- SKU inventory position
SELECT
    sku.sku_code,
    sku.style_code,
    sku.color_code,
    sku.size_name,
    sku.total_quantity,
    COALESCE(SUM(sd.units_sold), 0) as units_sold,
    sku.total_quantity - COALESCE(SUM(sd.units_sold), 0) as remaining
FROM skus sku
LEFT JOIN sales_data sd ON sd.sku_id = sku.id AND sd.brand_id = :brand_id
WHERE sku.brand_id = :brand_id
GROUP BY sku.id, sku.sku_code, sku.style_code, sku.color_code, sku.size_name, sku.total_quantity
ORDER BY remaining DESC
LIMIT 20;

-- Style-level summary
SELECT
    sku.style_code,
    COUNT(DISTINCT sku.color_code) as colors,
    COUNT(*) as total_skus,
    SUM(sku.total_quantity) as total_qty
FROM skus sku
WHERE sku.brand_id = :brand_id
GROUP BY sku.style_code
ORDER BY total_qty DESC
LIMIT 20;
```

## Upload Debugging

```sql
-- Recent uploads with errors
SELECT
    u.id,
    u.filename,
    u.upload_type,
    u.status,
    u.error_summary,
    u.created_at,
    usr.email as uploaded_by
FROM uploads u
JOIN users usr ON usr.id = u.uploaded_by
WHERE u.brand_id = :brand_id
ORDER BY u.created_at DESC
LIMIT 10;

-- Uploads with error reports
SELECT
    u.id,
    u.filename,
    u.error_summary->>'error_report_path' as error_path
FROM uploads u
WHERE u.brand_id = :brand_id
    AND u.error_summary->>'error_report_path' IS NOT NULL
ORDER BY u.created_at DESC
LIMIT 5;
```

## Performance Queries

```sql
-- Table sizes
SELECT
    relname as table,
    pg_size_pretty(pg_total_relation_size(relid)) as total_size,
    pg_size_pretty(pg_relation_size(relid)) as table_size,
    pg_size_pretty(pg_indexes_size(relid)) as index_size,
    n_live_tup as row_estimate
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;

-- Long-running queries
SELECT
    pid,
    state,
    query_start,
    NOW() - query_start as duration,
    LEFT(query, 100) as query_preview
FROM pg_stat_activity
WHERE state != 'idle'
    AND query_start IS NOT NULL
ORDER BY duration DESC
LIMIT 10;
```

## Common Quick Checks

```sql
-- Is allocation running?
SELECT
    id,
    status,
    NOW() - created_at as time_running
FROM allocation_sessions
WHERE status IN ('QUEUED', 'RUNNING')
    AND brand_id = :brand_id;

-- Any failed tasks?
SELECT
    id,
    task_name,
    status,
    error_message,
    created_at
FROM background_tasks
WHERE status = 'FAILED'
    AND brand_id = :brand_id
ORDER BY created_at DESC
LIMIT 10;

-- Data freshness
SELECT
    MAX(created_at) as latest_upload,
    MAX(processed_at) as latest_processed
FROM uploads
WHERE brand_id = :brand_id;
```
