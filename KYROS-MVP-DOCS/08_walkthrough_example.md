# 08 — Walkthrough: 100 Stores, 1,000 Styles, ₹10Cr

A realistic end-to-end scenario. Follow a brand through Kyros for one season. At each step, see the decision, the math, and how the system's output changes what the VP would do without it.

---

## The Brand

**Astra** — Indian women's ethnic + western apparel brand.

- 100 stores (75 EBO + 25 SIS in malls + MBOs)
- Expected ~₹22Cr revenue for SS26
- Target IMU 52%, target margin 45%
- Season: SS26, April 1 → September 30, 2026 (26 weeks)

### Buy Budget
Total season OTB: **₹10Cr at cost** (~₹20Cr at retail).

### Category Structure
Historical revenue contribution (SS25):
| Category | % Revenue | Sellthrough |
|----------|-----------|-------------|
| Kurtis | 38% | 72% |
| Dresses | 22% | 68% |
| Tops | 15% | 60% |
| Bottoms | 14% | 75% |
| Coords | 8% | 55% |
| Accessories | 3% | 45% |

---

## Step 1 — Season Setup

**In Kyros**:
- Create season "SS26", dates 2026-04-01 → 2026-09-30
- Status: DRAFT → PLANNING
- Weeks remaining = 26

**Planner time**: 3 minutes.

Without Kyros: create a new Excel folder, clone last season's template.

---

## Step 2 — OTB Allocation

Planner opens the OTB grid. Enters planned sales per category per month. System computes:

| Category | OTB (cost) | % of total |
|----------|-----------|------------|
| Kurtis | ₹4.0Cr | 40% |
| Dresses | ₹2.3Cr | 23% |
| Tops | ₹1.4Cr | 14% |
| Bottoms | ₹1.3Cr | 13% |
| Coords | ₹0.7Cr | 7% |
| Accessories | ₹0.3Cr | 3% |
| **Total** | **₹10.0Cr** | **100%** |

Monthly split (kurtis example):
| Month | OTB | % |
|-------|-----|---|
| Apr | ₹1.4Cr | 35% |
| May | ₹1.0Cr | 25% |
| Jun | ₹0.8Cr | 20% |
| Jul | ₹0.4Cr | 10% |
| Aug | ₹0.25Cr | 7% |
| Sep | ₹0.15Cr | 3% |

Opening order % set to **65%** — ₹6.5Cr committed pre-season, ₹3.5Cr held for chase + mid-season fashion drops.

### System Feedback at This Step
- ✅ Category mix roughly matches last-season contribution with slight push to dresses (+1pp)
- ⚠️ Coords budget +30% YoY — flagged for acknowledgment (strategic push confirmed)
- ⚠️ Accessories planned sales below last-season actuals — flagged; VP confirms deliberate

**Planner time**: 25 minutes.

Without Kyros: 3 days of back-and-forth in Excel, version proliferation, no automated category-mix check.

---

## Step 3 — Data Ingestion

Upload four files:
1. SS25 sales history — 195,000 rows, 52 weeks, 87 stores (3 closed, 10 new opened post-SS25)
2. Store grades — 100 stores × 6 categories = 600 grade rows
3. Size guide — 6 categories × 6 sizes × 3 price bands = ~108 rows
4. Last-season closing stock — feeds opening stock for OTB

**Kyros ingests**:
- Auto-maps columns (handles "Store Code" vs "store_code")
- Synthetic week spreading applied where week_start_date missing (SS25 file had it)
- Stockout inference applied (was_in_stock missing; system infers from 0-sales streaks)

**Validation results**:
- 194,230 sales rows accepted (99.6%)
- 770 rejected: 420 unknown SKU codes (flagged for SKU master cleanup), 350 closed stores
- 100 stores confirmed active, 10 new stores flagged NEW (use conservative demand fallback)
- Grades: 4 cells missing — system prompts planner to fill

**Planner time**: 20 minutes (mostly fixing SKU master issues).

Without Kyros: the SKU duplicates would go undetected. Demand signal would be split across duplicate codes.

---

## Step 4 — Buy Plan

Planner uploads SS26 buy file (or designs in UI). Kurtis category shown here:

Total kurti buy: 100,000 units at avg cost ₹400 = **₹4.0Cr** (matches OTB).

Style-level breakdown:
| Segment | Style count | Avg depth | Units | Value |
|---------|-------------|-----------|-------|-------|
| Hero (proven) | 30 | 600 | 18,000 | ₹0.72Cr |
| Core | 180 | 350 | 63,000 | ₹2.52Cr |
| Fashion | 80 | 175 | 14,000 | ₹0.56Cr |
| Experimental | 40 | 125 | 5,000 | ₹0.20Cr |
| **Total** | **330** | — | **100,000** | **₹4.0Cr** |

### Kyros Catches at Buy Plan Entry

| Issue | Severity | Action |
|-------|----------|--------|
| Style K-112 depth 200, MOQ 500 | WARNING | Suggests aggregating with K-113 (same fabric) or cutting |
| Vendor V-007 = 28% of kurti buy | WARNING | Concentration; planner confirms |
| Experimental = 5% of category OTB | OK | Within cap |
| Style K-047 (hero) depth 600 — demand math suggests 800 | WARNING | Suggests increasing depth by 200; planner accepts, reduces K-049 |

Total buy reconciled: **₹4.0Cr exactly**.

**Planner time**: 90 minutes (most of it in vendor MOQ negotiations — Kyros surfaces gaps, vendor resolves).

Without Kyros: gaps discovered post-PO. MOQ breaches fixed by tripling orders or cutting styles under time pressure.

---

## Step 5 — GRN Received

Vendor V-012 delivers. GRN ASTR-GRN-0042 contains:
- Style **K-047 (hero kurti, A+/A grade)**: 500 units across sizes S/M/L/XL
- 3 other styles totaling 1,200 units

Planner creates GRN, reserves:
- E-com: 50 units of K-047 (10% reserve)
- ARS: 0 for now

Available for allocation: **450 units of K-047**.

---

## Step 6 — Allocation

Trigger allocation for ASTR-GRN-0042. Celery task runs.

For Style K-047:

**Step 6a — Store filtering**:
- 100 active stores
- Store group rule: A+/A grade in kurtis only → 42 eligible
- Climate filter: exclude 3 stores in monsoon-heavy coastal → 39 eligible
- 10 NEW stores flagged → use conservative grade-fallback demand

**Step 6b — Demand projection per store**:

| Store | Grade | Tier Used | ROS (units/wk) | Cover Target | Demand |
|-------|-------|-----------|----------------|--------------|--------|
| S-012 Mumbai Juhu | A+ | Store hist (34 wks) | 4.2 | 7 wks | 29.4 |
| S-008 Delhi SDA | A+ | Store hist (34 wks) | 3.8 | 7 wks | 26.6 |
| S-015 Bangalore Indiranagar | A | Store hist (28 wks) | 3.1 | 5 wks | 15.5 |
| S-031 Chennai T.Nagar | A | Cluster avg | 2.4 | 5 wks | 12.0 |
| S-058 Lucknow (NEW) | A | Grade avg × 0.7 | 1.8 | 5 wks | 9.0 |
| ... (34 more stores) | | | | | |

Sum of demands: ~630 units.

**Step 6c — Cap and scale**:
Available = 450. Demands = 630. Scale factor = 450 / 630 = 0.714.

Scaled demands:
- S-012 Juhu: 29.4 × 0.714 = **21 units**
- S-008 SDA: 26.6 × 0.714 = **19 units**
- S-015 Indiranagar: 15.5 × 0.714 = **11 units**
- S-031 T.Nagar: 12.0 × 0.714 = **9 units**
- S-058 Lucknow: 9.0 × 0.714 = **6 units**

**Step 6d — MVQ enforcement**:
Min presentation = 2. All stores above it; no floor triggers.

**Step 6e — Size split**:
For S-012 Juhu (A+, has 34 wks history): store-specific size curve applies.
- Historical: S=18%, M=34%, L=32%, XL=16%
- 21 units → S=4, M=7, L=7, XL=3

For S-058 Lucknow (NEW): fallback to category default.
- Default: S=15%, M=30%, L=30%, XL=20%, XXL=5%
- 6 units → S=1, M=2, L=2, XL=1

**Step 6f — Explanation generation**:

For S-012 Juhu:
> "Juhu gets 21 units because it sold 4.2 units/week of kurtis last season (grade A+, store history). This gives 7 weeks of cover at target. Size split uses store's own sales history."
> Confidence: HIGH. Source: Store history.

For S-058 Lucknow:
> "Lucknow gets 6 units because it opened 45 days ago; we used average sellthrough of A-grade stores (1.8 units/wk) with a 30% discount for new-store uncertainty. This gives 5 weeks of cover. Size split uses brand default."
> Confidence: MEDIUM. Source: Grade average × new-store adjustment.

**Task time**: 90 seconds (all 4 styles in GRN).

---

## Step 7 — Review

Planner opens the review page.

**Summary view shows**:
- Total units allocated: 1,640 (out of 1,650 received minus 50 e-com)
- By grade: A+ = 42%, A = 35%, B = 18%, C = 5%
- By region: West 31%, North 28%, South 24%, East 17%

**Exception panel shows**:
- 3 lines at LOW confidence (new-store styles, Tier 4 DNA fallback)
- 1 line flagged: store S-044 cover projection 12 weeks (above target 7) — possible overstock

**Planner decisions**:
- Reviews top 20 A+ allocations — all look reasonable, approves
- Reviews the 4 exception lines:
  - S-058 Lucknow: override 6 → 4 units. Reason: "Store reported category slowdown last week" (new override reason type added to dropdown)
  - S-044 Pune: override 14 → 10 units. Reason: "Known local competitor launch; reduce cover"
  - Other 2 exceptions: accept as-is
- Approves session.

**Planner time**: 18 minutes.

Without Kyros: the Lucknow over-allocation wouldn't be flagged. Pune's overstock wouldn't be preempted. Planner would review top-50 lines at random and approve.

---

## Step 8 — Approve + Export

Session marked APPROVED, status now DISPATCHED. CSV exported:

```
GRN Code, SKU, Style, Size, Store Code, City, Quantity, Reason
ASTR-GRN-0042, K-047-S, K-047, S, S-012, Mumbai, 4, AI
ASTR-GRN-0042, K-047-M, K-047, M, S-012, Mumbai, 7, AI
...
ASTR-GRN-0042, K-047-M, K-047, M, S-058, Lucknow, 1, Override: Category slowdown
```

Sent to WMS. Warehouse team picks and ships over next 48 hours.

---

## How Outputs Changed Decisions

A like-for-like comparison: what would the VP have allocated without Kyros?

### Scenario A — Without Kyros (Excel gut-feel)
Typical merchandiser behavior:
- K-047 500 units / 42 stores = ~12 units per store equal split
- Top A+ stores (Juhu, SDA) get 12 each — **under-served** (demand was 21)
- Bottom A stores and NEW stores get 12 each — **over-served** (demand was 6–9)
- Size split uniform category curve everywhere

Projected outcome:
- Juhu/SDA stock out week 3–4, miss ~15 units of full-price sales each (~₹45K/store)
- Lucknow/new stores carry excess, markdown ~30 units total (~₹10K margin loss)
- **Net margin impact on this one style: ~₹80K–100K lost**

### Scenario B — With Kyros
- Top stores get demand-weighted 19–21 units
- Weak stores get 4–6 units
- Size split per-store where history exists
- Override captured with structured reasons

Projected outcome:
- No stockouts in A+ on this style during full-price window
- No markdown pressure on bottom allocation
- **Net margin preserved: ~₹80K–100K on this style alone**

### Scaling Up
At Astra's level:
- 330 kurti styles × avg margin delta ~₹50K per style = **₹1.6Cr annual margin uplift from allocation alone**
- Add OTB-reconciled buy plan (catches 2–3 over-concentrated bets per season) = another **₹50–75L saved on markdown**
- Guided workflow catches data-quality issues that would have corrupted plan = **~5–10% of residual error eliminated**

**Aggregate impact: 8–12% margin improvement on a ₹22Cr revenue brand, ≈ ₹1.5–2.5Cr/year.**

Kyros pays for itself in the first season.

---

## The Decisions That Happened Because of the System

Count the decisions the VP would not have made without Kyros:

1. **Confirmed coord category push** was flagged and acknowledged, not sleepwalked into
2. **K-047 hero depth raised 600 → 800** on Kyros's demand projection
3. **K-112 cut from plan** due to MOQ gap instead of tripling the bet
4. **Vendor V-007 concentration** surfaced; diversification considered
5. **Juhu stock-out risk averted** by demand-weighted depth
6. **Lucknow over-allocation reduced** by recognizing new-store uncertainty
7. **Pune overstock pre-empted** by cover-week threshold flag
8. **Override reasons captured** — feeding next-season's learning loop

Each of these is a small decision. Together they represent the difference between an organized plan and a gut-feel plan.

That is the product. Not a dashboard. Not an oracle. A **decision system** that makes the right trade-offs visible at the moment they are made.
