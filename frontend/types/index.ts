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

export interface AllocationReasoning {
  // Demand
  weekly_ros: number;
  raw_weekly_ros: number;
  ros_source:
    | 'store_historical'
    | 'cluster_average'
    | 'grade_average'
    | 'style_dna_analogue'
    | 'minimum_presentation'
    | 'no_history';
  is_stockout_corrected: boolean;
  stockout_week: number | null;
  lost_sales_estimate: number | null;
  data_sample_size: number;
  cluster_store_count: number;

  // Projection
  cover_target_weeks: number;
  weeks_cover_at_recommended: number;
  weeks_cover_minus_25pct: number;
  weeks_cover_plus_25pct: number;
  season_weeks_remaining: number;
  raw_demand_units: number;
  scale_factor: number;

  // Store
  store_grade: string;
  grade_multiplier: number;
  category_affinity: number | null;
  fabric_affinity: number | null;
  category_affinity_label: string | null;
  fabric_affinity_label: string | null;
  affinity_adjustment_units: number | null;

  // Story concentration
  cannibalization_factor: number | null;
  cannibalization_reason: string | null;
  colourways_in_story_at_store: number | null;

  // Capacity
  excluded_by_capacity: boolean;
  exclusion_reason: string | null;

  // Size split
  size_split: Record<string, number>;
  size_distribution_source: 'store_historical' | 'cluster_historical' | 'brand_size_guide';
  size_distribution_season: string | null;

  // Narratives — always non-empty strings
  narrative_demand: string;
  narrative_adjustments: string;
  narrative_cap: string;
  confidence_basis: string;

  style_dna_match: {
    matched_style_code: string;
    similarity_score: number | null;
  } | null;

  // Backward compat
  [key: string]: any;
}

export interface AIReasoning extends AllocationReasoning {}

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
  season_id?: string | null;
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

export interface AllocationInsights {
  lost_sales_correction: {
    stores_corrected: number;
    estimated_recovered_units: number;
    headline: string;
    subtext: string;
  };
  under_covered_stores: {
    count: number;
    headline: string;
  };
  confidence_breakdown: {
    high: number;
    moderate: number;
    low: number;
  };
  total_lines: number;
  total_units_allocated: number;
}

export interface AllocationBenchmarkCheck {
  metric: string;
  operator: "<=" | ">=";
  target: number;
  actual: number;
  passed: boolean;
}

export interface AllocationBenchmarkBucket {
  key: string;
  lines: number;
  allocated_units: number;
  override_rate: number;
  under_coverage_rate: number;
  grade_compliance_rate: number;
}

export interface AllocationBenchmarkReport {
  session_id: string;
  session_status: string;
  summary: {
    total_lines: number;
    allocated_units_total: number;
    available_units_total: number;
    override_rate: number;
    under_coverage_rate: number;
    grade_compliance_rate: number;
    inventory_utilization_rate: number;
    high_confidence_share: number;
    quality_score: number;
  };
  acceptance: {
    overall_pass: boolean;
    checks: AllocationBenchmarkCheck[];
  };
  demand_source_mix: Array<{
    source: string;
    lines: number;
    share: number;
  }>;
  scorecards: {
    by_grade: AllocationBenchmarkBucket[];
    by_style_risk_group: AllocationBenchmarkBucket[];
  };
}
