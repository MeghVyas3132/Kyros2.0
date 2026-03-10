# Pilot Data Changes — Kyros MVP

## Governing Principle
Every pattern in this document was discovered from real pilot data, but the patterns are universal across Indian fashion retail. What varies across brands is terminology, thresholds, and column names. What does not vary is the underlying pattern. Build for the pattern. Make terminology configurable. Never hardcode a specific brand's values into the allocation engine.

## Why These Changes Exist
The first pilot data exposed six structural retail patterns the pre-pilot MVP did not model: multi-dimensional store grading, pre-buy style targeting, multi-channel reservation deductions, configurable size guides, risk-tiered distribution, and story concentration visibility. Without these, allocation outputs violate buyer intent and store capability, causing heavy manual overrides and loss of trust. Before these changes, allocator-agreement is expected around 30-40%. With these changes, expected agreement is 65-75%, with the remaining gap driven by planner judgment and local context.

## Change 1: Multi-Dimensional Store Grading

### What changes
Replace single-grade-per-store with `store × product_category × optional price_band` grading.

### Schema (SQL)
```sql
ALTER TABLE stores DROP COLUMN IF EXISTS store_grade;

CREATE TABLE store_product_grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    product_category VARCHAR(100) NOT NULL,
    price_band VARCHAR(100),
    grade VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, store_id, product_category, price_band)
);

CREATE INDEX idx_store_product_grades_lookup
    ON store_product_grades (brand_id, store_id, product_category, price_band);
```

### Engine logic
```python
GRADE_SCORES = {"A+": 5, "A": 4, "B": 3, "C": 2}

async def get_store_grade(
    store_id: UUID,
    product_category: str,
    price_band: str | None,
    brand_id: UUID,
    db: AsyncSession,
) -> str:
    exact = await db.scalar(
        select(StoreProductGrade.grade).where(
            StoreProductGrade.brand_id == brand_id,
            StoreProductGrade.store_id == store_id,
            StoreProductGrade.product_category == product_category,
            StoreProductGrade.price_band == price_band,
        )
    )
    if exact:
        return exact

    product_level = await db.scalar(
        select(StoreProductGrade.grade).where(
            StoreProductGrade.brand_id == brand_id,
            StoreProductGrade.store_id == store_id,
            StoreProductGrade.product_category == product_category,
            StoreProductGrade.price_band.is_(None),
        )
    )
    if product_level:
        return product_level

    logger.warning(
        "No grade found for store=%s product=%s price_band=%s. Defaulting to C.",
        store_id,
        product_category,
        price_band,
    )
    return "C"
```

### Ingestion + column mapping
- Upload type: `STORE_GRADES`
- Semantic fields: `store_name`, `product_category`, optional `price_band`, `grade`
- Store name match: case-insensitive trimmed match to `stores.store_name`
- Raw grade normalization via `brand_settings.grade_mapping`
- Upsert on `(brand_id, store_id, product_category, price_band)`

### Onboarding screen: Grade Configuration
- Upload file
- Auto-detect columns, request manual mapping if unresolved
- Display unique raw grade values and map each to normalized `A+|A|B|C`
- Save to `brand_settings.grade_mapping`
- Confirm import

### Test cases
1. Kurta allocations use Kurta grade, not Dress grade.
2. Missing grade row defaults to `C` and logs warning.
3. `A+` score outranks `A` at equal other factors.
4. Unmatched store names produce row-level reference errors.

---

## Change 2: Pre-Buy Style Targeting

### What changes
Store group constraints are hard eligibility rules before scoring and distribution.

### Schema (SQL)
```sql
ALTER TABLE skus ADD COLUMN store_group_rule VARCHAR(200);
ALTER TABLE skus ADD COLUMN resolved_min_grade VARCHAR(10);

CREATE TABLE style_store_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    list_name VARCHAR(100) NOT NULL,
    store_ids UUID[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, list_name)
);

ALTER TABLE skus ADD COLUMN store_list_id UUID REFERENCES style_store_lists(id);
```

### Mapping-driven target resolution
Use `brand_settings.store_group_mapping`:
```json
{
  "store_group_mapping": {
    "A+ Stores": "A+",
    "A+ & A Stores": "A",
    "A+, A & B Stores": "B",
    "All Stores": null,
    "Tier 1": "A+",
    "Tier 2": "A"
  }
}
```

### Eligibility filter (hard-rule ordering)
```python
async def is_store_eligible_for_sku(store: Store, sku: SKU, brand_id: UUID, db: AsyncSession) -> tuple[bool, str]:
    if sku.store_list_id:
        store_list = await db.get(StyleStoreList, sku.store_list_id)
        if not store_list or store.id not in set(store_list.store_ids):
            return False, f"Store not in required list: {store_list.list_name if store_list else 'unknown'}"

    if sku.resolved_min_grade:
        store_grade = await get_store_grade(store.id, sku.category, sku.price_band, brand_id, db)
        if GRADE_SCORES.get(store_grade, 1) < GRADE_SCORES.get(sku.resolved_min_grade, 1):
            return False, f"Store grade {store_grade} below required {sku.resolved_min_grade}"

    if not climate_match(store.climate_zone, sku):
        return False, "Climate mismatch"

    if await get_remaining_display_capacity(store.id, sku.category, db) <= 0:
        return False, "No display capacity"

    return True, ""
```

### Onboarding screen: Store Group Configuration
- Show unique raw store-group values from buy file
- Map each to minimum grade or `All`
- Save to `brand_settings.store_group_mapping`

### UI specs
- Show store-group badge and eligible-store count on style header
- Manual add outside eligibility must show confirm warning modal with reason

### Test cases
1. `A+` style never auto-allocates to A/B/C stores.
2. `All Stores` style considers all active stores (subject to climate/capacity).
3. Manual add for non-eligible store shows warning.
4. Named list restriction wins even when grade is high.

---

## Change 3: Inventory Reservation System

### What changes
Reservations are dynamic and brand-configured; availability is calculated from active deducting reservation types.

### Schema (SQL)
```sql
CREATE TABLE inventory_reservation_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    code VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    deducts_from_first_allocation BOOLEAN DEFAULT true,
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, code)
);

CREATE TABLE grn_line_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grn_line_id UUID NOT NULL REFERENCES grn_lines(id),
    brand_id UUID NOT NULL REFERENCES brands(id),
    reservation_type_id UUID NOT NULL REFERENCES inventory_reservation_types(id),
    reserved_qty INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(grn_line_id, reservation_type_id)
);

ALTER TABLE grn_lines ADD COLUMN total_buy_qty INTEGER;
ALTER TABLE grn_lines ADD COLUMN ecom_reserved_qty INTEGER DEFAULT 0;
ALTER TABLE grn_lines ADD COLUMN ars_reserved_qty INTEGER DEFAULT 0;
```

### Dynamic allocation ceiling
```python
async def get_available_for_first_allocation(grn_line_id: UUID, db: AsyncSession) -> int:
    grn_line = await db.get(GRNLine, grn_line_id)
    if not grn_line:
        return 0

    total_reserved = await db.scalar(
        select(func.coalesce(func.sum(GrnLineReservation.reserved_qty), 0))
        .join(InventoryReservationType, InventoryReservationType.id == GrnLineReservation.reservation_type_id)
        .where(
            GrnLineReservation.grn_line_id == grn_line_id,
            InventoryReservationType.is_active.is_(True),
            InventoryReservationType.deducts_from_first_allocation.is_(True),
        )
    )
    return max(0, int(grn_line.units_received) - int(total_reserved or 0))
```

### Onboarding screen: Reservation Type Configuration
- Create/edit reservation types: `code`, `label`, `deducts_from_first_allocation`, `display_order`

### UI specs
- Allocation panel must show total received, deductions by reservation type, available, allocated, remaining.

### Test cases
1. Ceiling equals `units_received - sum(active deducting reservations)`.
2. Non-deducting reservation types do not affect ceiling.
3. Negative availability clamps to 0 and style is skipped with warning.
4. UI breakdown sums reconcile exactly.

---

## Change 4: Flexible Size Guide

### What changes
Add configurable size guide with mandatory/optional logic, ratio weights, grade-level applicability, and set-size handling.

### Schema (SQL)
```sql
CREATE TABLE size_guides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    product_category VARCHAR(100) NOT NULL,
    size VARCHAR(20) NOT NULL,
    size_type VARCHAR(20) NOT NULL DEFAULT 'PIVOTAL',
    min_max_ratio INTEGER NOT NULL DEFAULT 1,
    is_size_set BOOLEAN DEFAULT false,
    applies_to_grades VARCHAR(20) DEFAULT 'ALL',
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, product_category, size)
);

CREATE INDEX idx_size_guides_lookup
    ON size_guides (brand_id, product_category, display_order);
```

### Historical ratio fallback chain (required)
```python
async def load_historical_size_ratios(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    db: AsyncSession,
) -> dict[str, float]:
    """
    Fallback chain:
    1) Store-level ratios for product_category
    2) Cluster-level ratios for product_category
    3) Brand-level ratios for product_category
    4) Empty dict (caller falls back to size-guide ratio only)
    """
    store_ratios = await query_store_size_ratios(brand_id, product_category, store_id, db)
    if has_min_sample(store_ratios):
        return normalise_ratios(store_ratios)

    cluster_id = await db.scalar(select(Store.cluster_id).where(Store.id == store_id))
    cluster_ratios = await query_cluster_size_ratios(brand_id, product_category, cluster_id, db)
    if has_min_sample(cluster_ratios):
        return normalise_ratios(cluster_ratios)

    brand_ratios = await query_brand_size_ratios(brand_id, product_category, db)
    if has_min_sample(brand_ratios):
        return normalise_ratios(brand_ratios)

    logger.warning(
        "No historical size ratios for brand=%s product=%s store=%s. Using size guide defaults.",
        brand_id,
        product_category,
        store_id,
    )
    return {}
```

### Set-size distribution function (required)
```python
async def distribute_size_sets(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    total_units: int,
    eligible_guides: list[SizeGuide],
    db: AsyncSession,
) -> dict[str, int]:
    """
    For products where sizes are sets (for example S/M, L/XL).
    Uses store->cluster->brand historical set ratios via load_historical_size_ratios.
    Falls back to guide weights when no history.
    """
    hist = await load_historical_size_ratios(brand_id, product_category, store_id, db)
    set_sizes = [g.size for g in eligible_guides if g.is_size_set]

    weights: dict[str, float] = {}
    for g in eligible_guides:
        if not g.is_size_set:
            continue
        # history first; guide ratio fallback
        weights[g.size] = hist.get(g.size, float(max(1, g.min_max_ratio)))

    if not weights:
        return {}

    return reconcile_weighted_quantities(weights, total_units)
```

### Reconciliation utility (required)
```python
def reconcile_weighted_quantities(
    weights: dict[str, float],
    total_units: int,
) -> dict[str, int]:
    """
    Distribute total_units proportionally to weights and ensure
    output sums exactly to total_units after rounding.
    """
    if not weights or total_units <= 0:
        return {}

    total_weight = sum(weights.values()) or 1.0
    raw = {size: (w / total_weight) * total_units for size, w in weights.items()}
    floored = {size: int(qty) for size, qty in raw.items()}
    remainder = total_units - sum(floored.values())

    fractional = sorted(
        raw.keys(),
        key=lambda s: raw[s] - floored[s],
        reverse=True,
    )
    for i in range(remainder):
        floored[fractional[i % len(fractional)]] += 1

    return {size: qty for size, qty in floored.items() if qty > 0}
```

### Core size distribution
```python
async def calculate_size_distribution(
    brand_id: UUID,
    product_category: str,
    store_id: UUID,
    store_grade: str,
    total_units: int,
    db: AsyncSession,
) -> dict[str, int]:
    guides = await load_size_guides(brand_id, product_category, db)

    eligible: list[SizeGuide] = []
    for g in guides:
        if g.min_max_ratio == 0:
            continue
        if g.applies_to_grades == "A+_ONLY" and store_grade != "A+":
            continue
        if g.applies_to_grades == "A+_A" and store_grade not in {"A+", "A"}:
            continue
        eligible.append(g)

    if not eligible:
        return {}

    if len(eligible) == 1 and eligible[0].size.upper() in {"FS", "FREE SIZE", "ONE SIZE"}:
        return {eligible[0].size: total_units}

    if any(g.is_size_set for g in eligible):
        return await distribute_size_sets(brand_id, product_category, store_id, total_units, eligible, db)

    hist = await load_historical_size_ratios(brand_id, product_category, store_id, db)
    base_weights = {g.size: float(max(1, g.min_max_ratio)) for g in eligible}

    base_total = sum(base_weights.values()) or 1.0
    adjusted: dict[str, float] = {}
    for size, w in base_weights.items():
        expected_ratio = w / base_total
        observed_ratio = hist.get(size)
        if observed_ratio and expected_ratio > 0:
            adjusted[size] = w * min(observed_ratio / expected_ratio, 1.5)
        else:
            adjusted[size] = w

    return reconcile_weighted_quantities(adjusted, total_units)
```

### Cold-start behavior (explicit)
For brands with no historical data:
- Use size guide `min_max_ratio` only
- Allocation score should prioritize grade and configured rules (not ROS)
- Mark confidence as `LOW`
- Show UI banner: "First season on Kyros: recommendations are configuration-based and will improve after sales history accrues."

### Onboarding screen: Size Guide Configuration
- Upload + detect/mapping
- Preview parsed grid by category
- Validate at least one mandatory size (`min_max_ratio > 0`) per category
- Configure `applies_to_grades`
- Confirm import

### Test cases
1. Ratio `0` sizes are never allocated.
2. Optional sizes obey `applies_to_grades`.
3. Set-size products allocate set sizes only.
4. Total size quantities reconcile exactly to target quantity.
5. Cold-start mode works with zero historical data.

---

## Change 5: Style Risk Groups

### What changes
Normalize risk labels to `PROVEN|CONFIDENT|EXPERIMENTAL` and apply concentrated distribution for experimental styles.

### Schema (SQL)
```sql
ALTER TABLE skus ADD COLUMN style_risk_group VARCHAR(50);
ALTER TABLE skus ADD COLUMN resolved_risk_level VARCHAR(20);
```

### Config
```json
{
  "allocation": {
    "risk_group_mapping": {
      "Group A": "PROVEN",
      "Group B": "CONFIDENT",
      "Group C": "EXPERIMENTAL",
      "No Group": "PROVEN",
      "New": "EXPERIMENTAL"
    },
    "experimental_max_stores": 5,
    "experimental_min_units_per_store": 6,
    "experimental_store_selection": "TOP_BY_SCORE"
  }
}
```

### Concentrated distribution
```python
def distribute_concentrated(
    ranked_store_ids: list[UUID],
    available_units: int,
    max_stores: int,
    min_units_per_store: int,
) -> dict[UUID, int]:
    if not ranked_store_ids or available_units <= 0:
        return {}

    affordable_stores = min(max_stores, max(1, available_units // max(1, min_units_per_store)))
    selected = ranked_store_ids[:affordable_stores]

    per_store = available_units // len(selected)
    rem = available_units % len(selected)

    allocation: dict[UUID, int] = {}
    for idx, sid in enumerate(selected):
        qty = per_store + (1 if idx < rem else 0)
        if qty > 0:
            allocation[sid] = qty
    return allocation
```

### UI requirements
- Risk badge per style (`PROVEN`, `CONFIDENT`, `EXPERIMENTAL`)
- If `affordable_stores < configured_max_stores`, show informational message:
  - "Only N stores can receive this style at min X units (Y units available)."

### Onboarding screen: Risk Group Configuration
- Show unique raw risk labels from buy file
- Map to normalized levels
- Configure concentration knobs

### Test cases
1. Experimental styles capped at `experimental_max_stores`.
2. Experimental distribution honors minimum units per store.
3. Informational UI message appears when store count is reduced by min-units constraint.
4. Proven/confident styles use standard strategy.

---

## Change 6: Story Concentration

### What changes
Capture story metadata and surface concentration insights in UI (informational only).

### Schema (SQL)
```sql
ALTER TABLE skus ADD COLUMN story VARCHAR(200);
ALTER TABLE skus ADD COLUMN sub_story VARCHAR(200);
```

### Story concentration calculation
```python
async def get_story_threshold_from_settings(
    brand_id: UUID,
    db: AsyncSession,
    default: int = 4,
) -> int:
    value = await db.scalar(
        select(BrandSettings.config["allocation"]["story_concentration_warn_threshold"]).where(
            BrandSettings.brand_id == brand_id
        )
    )
    return int(value) if value else default
```

```python
async def compute_story_concentration(
    session_id: UUID,
    store_id: UUID,
    brand_id: UUID,
    db: AsyncSession,
) -> list[dict]:
    rows = await db.execute(
        select(SKU.story, func.count(AllocationLine.id))
        .join(SKU, SKU.id == AllocationLine.sku_id)
        .where(AllocationLine.session_id == session_id, AllocationLine.store_id == store_id)
        .group_by(SKU.story)
    )

    threshold = await get_story_threshold_from_settings(brand_id=brand_id, db=db, default=4)
    result = []
    for story, count in rows.all():
        if not story:
            continue
        result.append({
            "story": story,
            "style_count": int(count),
            "is_high": int(count) > threshold,
        })
    return sorted(result, key=lambda x: x["style_count"], reverse=True)
```

### UI panel spec
- Per selected store: story counts, top-heavy visualization
- Amber warning above threshold
- No blocking behavior in v1

### Test cases
1. Story counts match allocated lines.
2. Warning appears only above threshold.
3. Warning is amber and informational.

---

## New Upload Types

### Upload type summary
1. `STORE_GRADES` -> `store_product_grades`
2. `SIZE_GUIDE` -> `size_guides`
3. `BUY_FILE` -> `skus` metadata + buy-plan tables (not `grn_lines`)
4. `RESERVATION_TYPES` -> `inventory_reservation_types`

### BUY_FILE vs GRN separation (critical)
BUY file is planning intent, GRN is physical receipt. Do not write BUY uploads directly into `grn_lines`.

#### Schema for buy intent
```sql
CREATE TABLE buy_plan_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    season_id UUID REFERENCES seasons(id),
    source_upload_id UUID REFERENCES uploads(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE buy_plan_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buy_plan_file_id UUID NOT NULL REFERENCES buy_plan_files(id),
    brand_id UUID NOT NULL REFERENCES brands(id),
    sku_id UUID NOT NULL REFERENCES skus(id),
    total_buy_qty INTEGER NOT NULL DEFAULT 0,
    expected_first_allocation_qty INTEGER,
    store_group_rule VARCHAR(200),
    style_risk_group VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(buy_plan_file_id, sku_id)
);

ALTER TABLE grn_lines ADD COLUMN buy_plan_line_id UUID REFERENCES buy_plan_lines(id);
```

### Full alias dictionaries (required)

```python
STORE_GRADES_ALIASES = {
    "store_name": ["store name", "store", "store_name", "outlet", "outlet name", "location name", "shop name"],
    "product_category": ["product", "category", "product category", "department", "item category", "product_category"],
    "price_band": ["price band", "price_band", "price range", "mrp band", "price tier", "band"],
    "grade": ["grade", "store grade", "store grade - prod price band", "store classification", "tier", "rating", "store tier"],
}

SIZE_GUIDE_ALIASES = {
    "product_category": ["product", "category", "product category", "department", "store name"],
    "size": ["size", "size code", "size_name", "dimension"],
    "size_type": ["size type", "mandatory", "pivotal", "core/fringe", "must have flag"],
    "min_max_ratio": ["min/max", "min / max", "ratio", "ratio weight", "weight", "allocation ratio"],
    "is_size_set": ["is size set", "size set", "combined size", "set size flag"],
    "applies_to_grades": ["applies to grades", "min grade to send", "grade eligibility", "store grades"],
}

BUY_FILE_ALIASES = {
    "sku_code": ["style number", "sku", "sku code", "style code", "item code"],
    "style_name": ["style name", "design name", "description", "style"],
    "category": ["product", "category", "product category", "department"],
    "size": ["size", "size code"],
    "store_group_rule": ["store group", "store tier", "target stores", "distribution group"],
    "style_risk_group": ["style group", "risk group", "group", "style tier"],
    "story": ["story", "collection", "theme"],
    "sub_story": ["sub story", "sub-story", "sub collection", "sub theme"],
    "buyer_name": ["buyer", "buyer name", "merchandiser"],
    "vendor_name": ["vendor", "supplier", "partner"],
    "total_buy_qty": ["total buy qty", "buy qty", "ordered qty", "po qty", "total quantity"],
    "units_received": ["units received", "received qty", "grn qty", "received quantity"],
    "reservation_ecom": ["ecom reserved qty", "ecom reserve", "online reserve"],
    "reservation_ars": ["reserved qty for ars", "ars reserved qty", "replenishment reserve"],
}

RESERVATION_TYPES_ALIASES = {
    "code": ["code", "reservation code", "type code"],
    "label": ["label", "reservation label", "name", "reservation type"],
    "deducts_from_first_allocation": ["deducts", "deduct from allocation", "is deducting", "reduces first allocation"],
    "display_order": ["display order", "order", "sort order"],
    "is_active": ["active", "is active", "enabled"],
}
```

### Mapping-required payload contract
```json
{
  "error": {
    "code": "MAPPING_REQUIRED",
    "message": "Column mapping required before processing upload.",
    "details": {
      "upload_type": "SIZE_GUIDE",
      "missing_fields": ["size_type", "min_max_ratio"],
      "available_columns": ["Product", "Size", "MIN / MAX", "SIZE TYPE"]
    }
  }
}
```

### Error cases
- Missing required semantic mapping
- Unknown grade labels not in grade mapping
- Negative reservation quantity
- Reservation totals inconsistent with file totals (warning or fail by brand policy)
- Unresolved store/SKU references

---

## Configuration Schema

### Schema (SQL)
```sql
CREATE TABLE brand_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL UNIQUE REFERENCES brands(id),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brand_settings_config_gin
    ON brand_settings USING gin (config);
```

### Suggested `config` shape
```json
{
  "grade_mapping": {
    "A+ Stores": "A+",
    "A Stores": "A",
    "B Stores": "B",
    "C Stores": "C"
  },
  "store_group_mapping": {
    "A+ Stores": "A+",
    "A+ & A Stores": "A",
    "A+, A & B Stores": "B",
    "All Stores": null
  },
  "column_mappings": {
    "STORE_GRADES": {
      "store_name": "Store Name",
      "product_category": "Product",
      "price_band": "Price Band",
      "grade": "Store Grade - Prod Price Band"
    },
    "SIZE_GUIDE": {
      "product_category": "Product",
      "size": "Size",
      "size_type": "SIZE TYPE",
      "min_max_ratio": "MIN / MAX"
    },
    "BUY_FILE": {
      "sku_code": "Style Number",
      "category": "Product",
      "store_group_rule": "Store Group",
      "style_risk_group": "Style Group",
      "story": "Story",
      "sub_story": "Sub Story"
    }
  },
  "allocation": {
    "experimental_max_stores": 5,
    "experimental_min_units_per_store": 6,
    "experimental_store_selection": "TOP_BY_SCORE",
    "story_concentration_warn_threshold": 4,
    "risk_group_mapping": {
      "Group A": "PROVEN",
      "Group B": "CONFIDENT",
      "Group C": "EXPERIMENTAL",
      "No Group": "PROVEN"
    }
  },
  "cold_start": {
    "enabled": true,
    "size_distribution_mode": "SIZE_GUIDE_ONLY",
    "scoring_mode": "GRADE_WEIGHTED_ONLY",
    "default_confidence": "LOW"
  }
}
```

---

## Onboarding Screens Required
1. Grade Configuration
2. Store Group Configuration
3. Reservation Type Configuration
4. Size Guide Configuration
5. Risk Group Configuration

All mappings/settings persist in `brand_settings` and are reused automatically.

---

## Implementation Order
1. Database migration (all new tables/columns/indexes in one revision)
2. Brand settings table + read/write service
3. Onboarding APIs/UI for mappings and reservation types
4. Upload pipelines (`STORE_GRADES`, `SIZE_GUIDE`, `BUY_FILE`, `RESERVATION_TYPES`) with alias auto-detect + mapping-required flow
5. Allocation engine updates (grade lookup, hard eligibility, dynamic reservations, size-guide logic, concentrated experimental distribution, cold-start path)
6. Allocation UI updates (targeting/risk badges, reservation breakdown, story concentration panel, experimental-store-limit explanation)
7. Seed data update to exercise all new behaviors

---

## Testing Checklist

### Unit tests
1. `get_store_grade` fallback chain and no cross-category leakage.
2. Hard eligibility gate blocks below-target stores.
3. Reservation ceiling uses active deducting reservation types only.
4. `load_historical_size_ratios` fallback chain works store->cluster->brand->default.
5. `distribute_size_sets` returns set-size allocations and reconciles totals.
6. Ratio-0 sizes never allocated.
7. Experimental distribution obeys max stores and min units.
8. Cold-start scoring and confidence behavior apply when no history exists.
9. Story concentration threshold logic works.

### Integration tests
1. `STORE_GRADES` upload with fuzzy column labels and grade normalization mapping.
2. `SIZE_GUIDE` upload with mapping-required then successful import.
3. `RESERVATION_TYPES` upload and reservation calculations in allocation.
4. `BUY_FILE` upload enriches SKU + buy-plan tables without creating GRN lines.
5. GRN upload links to buy-plan lines and uses reservation deductions.
6. Allocation payload contains targeting/risk/story/reservation metadata.

### UI tests
1. Onboarding mapping screens persist and auto-apply on next upload.
2. Allocation table shows target group and risk badges.
3. Reservation breakdown matches backend totals.
4. Story concentration panel shows counts and amber warning above threshold.
5. Manual non-eligible store add shows warning modal.
6. Experimental store-limit explanatory message appears when min-units constraint reduces store count.
7. Cold-start banner appears for first-season brands.

### Performance checks
1. `POST /allocation/generate` under 30s for pilot-scale GRN.
2. `POST /allocation/simulate` under 200ms.
3. Story concentration query under 200ms per store.

---

## Remaining Accuracy Gap (Post-Changes)
Expected remaining 25-35% override gap includes local events, visual-merchandising judgment, new trends not yet in data, and competitive/markdown timing decisions. This residual is expected and should be captured as structured override feedback.
