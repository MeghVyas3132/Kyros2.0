export type Role = "ADMIN" | "PLANNER" | "VIEWER";

export interface ApiMeta {
  request_id: string;
  timestamp: string;
}

export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
  meta: ApiMeta;
}

export interface User {
  id: string;
  brand_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface AlertCount {
  unread: number;
  high: number;
  medium: number;
  low: number;
}

export interface Alert {
  id: string;
  brand_id: string;
  alert_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  title: string;
  message: string;
  store_id: string | null;
  sku_id: string | null;
  grn_id: string | null;
  action_url: string | null;
  is_read: boolean;
  is_dismissed: boolean;
  generated_at: string;
}

export interface GRN {
  id: string;
  brand_id: string;
  grn_code: string;
  grn_date: string;
  warehouse_id: string | null;
  supplier_name: string | null;
  status: "RECEIVED" | "ALLOCATED" | "DISPATCHED";
  total_units: number;
  total_skus: number;
  season_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AllocationLine {
  id: string;
  session_id: string;
  brand_id: string;
  store_id: string;
  sku_id: string;
  ai_recommended_qty: number;
  ai_confidence: "HIGH" | "MEDIUM" | "LOW" | null;
  ai_reasoning: AIReasoning;
  ai_projections?: AIProjections | null;
  final_qty: number | null;
  was_overridden: boolean;
  override_reason: string | null;
  override_notes: string | null;
  store_code?: string | null;
  store_name?: string | null;
  store_city?: string | null;
  sku_code?: string | null;
  style_name?: string | null;
  sku_size?: string | null;
  sku_category?: string | null;
  sku_fabric?: string | null;
  sku_colour?: string | null;
  sku_price_band?: string | null;
  sku_store_group_rule?: string | null;
  sku_resolved_min_grade?: string | null;
  sku_style_risk_group?: string | null;
  sku_resolved_risk_level?: string | null;
  sku_story?: string | null;
  sku_sub_story?: string | null;
  grn_units_received?: number | null;
  grn_total_buy_qty?: number | null;
  grn_ecom_reserved_qty?: number | null;
  grn_ars_reserved_qty?: number | null;
  grn_available_for_first_allocation?: number | null;
  grn_reservations?: Array<{
    code: string;
    label: string;
    reserved_qty: number;
    deducts_from_first_allocation: boolean;
    is_active: boolean;
  }> | null;
}

export interface AIReasoning {
  weekly_ros?: number;
  store_grade: string;
  store_ros_attribute: number | string;
  cluster_avg_ros_attribute: number | string;
  ros_vs_cluster_pct: number;
  ros_source?: string;
  is_stockout_corrected?: boolean;
  stockout_correction_applied?: boolean;
  stockout_week?: number | null;
  lost_sales_estimate?: number | null;
  cover_target_weeks?: number;
  current_stock_cover_days: number;
  display_capacity_available: number | null;
  season_weeks_remaining: number;
  raw_demand_units?: number;
  scale_factor?: number;
  grade_multiplier?: number;
  weeks_cover_at_recommended: number;
  weeks_cover_minus_25?: number;
  weeks_cover_plus_25?: number;
  weeks_cover_at_minus_25pct: number;
  weeks_cover_at_plus_25pct: number;
  stockout_risk_at_lower_qty: boolean;
  climate_match: boolean;
  data_sample_size: number;
  confidence_basis: string;
  category_affinity?: string | null;
  fabric_affinity?: string | null;
  affinity_adjustment_units?: number | null;
  cannibalization_factor?: number | null;
  cannibalization_reason?: string | null;
  colourways_in_story_at_store?: number | null;
  size_split?: Record<string, number>;
  size_distribution_source?: string;
  size_distribution_season?: string | null;
  narrative_demand?: string;
  narrative_adjustments?: string;
  narrative_cap?: string;
  style_dna_match?: number | null;
}

export interface AIProjections {
  size_split: Record<string, number>;
  size_distribution_source: string;
  cap_scale_factor: number;
  total_demand_before_cap: number;
  available_qty: number;
}

export interface AllocationSession {
  id: string;
  brand_id: string;
  grn_id: string;
  status: "DRAFT" | "GENERATING" | "FAILED" | "UNDER_REVIEW" | "APPROVED" | "DISPATCHED" | "CANCELLED";
  total_stores: number;
  total_skus: number;
  total_units_recommended: number;
  total_units_approved: number;
  failure_reason?: string | null;
  approved_by: string | null;
  approved_at: string | null;
  generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SimulationResult {
  quantity: number;
  weeks_cover: number;
  fills_display_capacity: boolean;
  remaining_capacity_after: number;
  projected_sellthrough_eow: number;
  stockout_risk: boolean;
  overstock_risk: boolean;
  notes: string;
}

export interface StorePerformanceRow {
  store_id: string;
  store_name: string;
  store_grade?: string | null;
  avg_sell_through_pct: number | null;
  avg_ros: number | null;
  avg_stock_cover_days: number | null;
  styles_exposed: number;
  styles_healthy: number;
  styles_watch: number;
  styles_problem: number;
  styles_critical: number;
  styles_stockout: number;
}

export interface StoryConcentration {
  story: string;
  style_count: number;
  is_high: boolean;
}
