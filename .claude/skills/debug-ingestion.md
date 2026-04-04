# Debug Ingestion

Debug CSV/Excel upload issues when files fail to upload, columns don't map correctly, or data doesn't appear after upload.

## Usage

Given symptoms like "upload failed", "columns not recognized", "data not showing up", or "wrong data type detected", invoke this skill to diagnose ingestion issues.

## Debug Checklist

### 1. Check Upload Pipeline

The upload flow is: `ingestion.py` → `process_upload_with_fallback()` → `processor.py`

### 2. Verify File Format

Upload supports:
- CSV files (.csv)
- Excel files (.xlsx, .xlsm)
- Multi-sheet Excel with `smart-upload` endpoint

### 3. Column Mapping Issues

If columns aren't recognized:

```python
# Read the mapping code in mapping.py
# Check UPLOAD_FIELD_ALIASES for your upload type
# Verify your CSV column names match expected aliases
```

Common aliases:
- `style_code`: style_code, Style Code, Style_Code, STYLE CODE
- `color_code`: color_code, Color Code, Color_Code, COLOUR
- `size_name`: size_name, Size, Size Name, SIZE
- `quantity`: quantity, Qty, Quantity, UNITS

### 4. Check Processor Logic

Read `processor.py` and trace:

1. `_process_upload_async()` - Main entry point
2. `process_buy_file()` / `process_sales_history()` / etc - Type-specific processors
3. `_upsert_sales()` - For sales data (note synthetic week spreading)

### 5. Synthetic Week Spreading

If sales data is missing `week_start_date`, the system spreads units across synthetic weeks. Check:

```python
SYNTHETIC_SALES_WEEKS = 8

# In _upsert_sales():
parsed_week = _try_parse_week_start_date(row.get("week_start_date"))
if parsed_week is None:
    # Units spread across 8 synthetic weeks
    synthetic_week_starts = _generate_synthetic_week_starts(SYNTHETIC_SALES_WEEKS)
```

### 6. Verify Upload Status

```sql
-- Check upload status
SELECT
    id,
    filename,
    upload_type,
    status,
    error_summary,
    created_at,
    processed_at
FROM uploads
WHERE brand_id = :brand_id
ORDER BY created_at DESC
LIMIT 10;
```

### 7. Common Ingestion Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "Unable to parse file" | Wrong file format or corrupted | Check file opens in Excel/LibreOffice |
| "MAPPING_REQUIRED" | Column names don't match aliases | Upload with manual column_mapping_json |
| Data not appearing after upload | Celery task failed | Check uploads.error_summary column |
| Wrong upload_type detected | Sheet type detection failed | Use manual sheet_mapping_json |
| Sales appear compressed | Missing week_start_date | Add week_start_date column or accept synthetic spread |
| Duplicates in sales_data | Multiple uploads of same file | Check for existing data before upload |

### 8. Manual Override

If automatic detection fails, use manual mapping:

```json
{
  "column_mapping_json": "{\"style_code\": \"STYLE CODE\", \"color_code\": \"COLOUR\"}"
}
```

For smart-upload with multiple sheets:

```json
{
  "sheet_mapping_json": "{\"Sheet1\": {\"upload_type\": \"BUY_FILE\", \"mapping\": {\"style_code\": \"Style\"}}}"
}
```

### 9. Check Error Reports

If upload has errors, download error report:

```
GET /api/v1/ingestion/uploads/{upload_id}/errors
```

## Output Format

When complete, report:
1. Root cause identified
2. File(s) and line(s) needing change
3. Suggested fix or workaround
4. Verification steps
