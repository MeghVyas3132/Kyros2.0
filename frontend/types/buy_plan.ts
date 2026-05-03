export interface BuyPlanFileOut {
  id: string;
  brand_id: string;
  season_id: string | null;
  name: string;
  source_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BuyPlanFileWithStats extends BuyPlanFileOut {
  total_lines: number;
  total_units: number;
  total_styles: number;
  categories: string[];
}

export interface BuyPlanLine {
  id: string;
  buy_plan_file_id: string;
  brand_id: string;
  sku_id: string;
  sku_code: string | null;
  style_code: string | null;
  style_name: string | null;
  category: string | null;
  size: string | null;
  colour: string | null;
  price_band: string | null;
  store_group_rule: string | null;
  style_risk_group: string | null;
  total_buy_qty: number | null;
  expected_first_allocation_qty: number | null;
  vendor_name: string | null;
  expected_delivery_week: string | null;
  planned_cost_per_unit: number | null;
  moq: number | null;
  planned_price_per_unit: number | null;
  planned_margin_pct: number | null;
  created_at: string;
  updated_at: string;
}

export interface BuyPlanLineUpdate {
  vendor_name?: string | null;
  expected_delivery_week?: string | null;
  planned_cost_per_unit?: number | null;
  moq?: number | null;
  planned_price_per_unit?: number | null;
  planned_margin_pct?: number | null;
  total_buy_qty?: number | null;
  store_group_rule?: string | null;
  style_risk_group?: string | null;
}

export interface OTBReconciliationRow {
  category: string;
  month: string;
  planned_sales: number;
  otb_value: number;
  buy_plan_cost: number;
  otb_usage_pct: number;
  is_overrun: boolean;
}

export interface BuyPlanReconciliation {
  buy_plan_file_id: string;
  season_id: string | null;
  rows: OTBReconciliationRow[];
  total_otb: number;
  total_committed: number;
  overall_usage_pct: number;
}

// Style-level grouping for the detail table
export interface StyleGroup {
  style_code: string;
  style_name: string | null;
  category: string | null;
  price_band: string | null;
  style_risk_group: string | null;
  colour: string | null;
  // These come from the first line of the style (all lines share vendor/delivery/cost/moq/margin)
  vendor_name: string | null;
  expected_delivery_week: string | null;
  planned_cost_per_unit: number | null;
  moq: number | null;
  planned_price_per_unit: number | null;
  planned_margin_pct: number | null;
  // Aggregated across all size lines
  total_buy_qty: number;
  // All individual lines (by size) for this style
  lines: BuyPlanLine[];
}
