export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface NumberItem {
  id: string;
  provider_code: string;
  inventory_kind: string;
  provider_number_key: string;
  msisdn: string | null;
  abc_code: string | null;
  number_category: string | null;
  number_local: string | null;
  region_name: string | null;
  city_name: string | null;
  buy_price: string | null;
  period_price: string | null;
  mask: string | null;
  display_mask: string | null;
  number_type: string | null;
  points: string | null;
  notes: string | null;
  class: string | null;
  operator: string | null;
  rtu_connected?: string | null;
  is_currently_present: boolean;
  mapping_confidence: string;
}

export interface FacetItem {
  value: string;
  count: number;
}

export interface FacetResponse {
  column: string;
  items: FacetItem[];
  truncated: boolean;
}

/** Multi-select facet filters: field -> selected values (`__empty__` for blank/NULL). */
export type ColumnFilters = Record<string, string[]>;

export interface ProviderSettings {
  provider_code: string;
  base_url: string | null;
  auth_settings_masked: Record<string, string>;
  extra_settings: Record<string, unknown>;
  is_enabled: boolean;
  last_tested_at?: string | null;
  last_test_status?: string | null;
  last_test_message?: string | null;
  docs_notice: string;
}

export interface SyncStage {
  id: string;
  group: string;
  label: string;
  status: string;
  detail: string;
  substage?: string;
  progress?: {
    current: number | null;
    total: number | null;
    unit: string;
  };
  started_at: string | null;
  finished_at: string | null;
}

export interface PstnInnOperator {
  id: string;
  name: string;
  inn: string;
  enabled: boolean;
  required: boolean;
  ranges_count: number;
  numbers_count: number;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface PstnInnCacheStatus {
  min_cache_ready: boolean;
  missing_required: string[];
  gar_territory_missing?: boolean;
  refresh: {
    status?: string;
    detail?: string;
    error?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
  };
  operators: PstnInnOperator[];
}

export interface SyncSchedule {
  enabled: boolean;
  timezone: string;
  hour: number;
  minute: number;
}

export interface SyncRun {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  progress: {
    current_stage_id: string | null;
    stages: SyncStage[];
  };
  stats: Record<string, unknown>;
  error_summary: string | null;
  triggered_by: string | null;
  created_at: string;
}

export interface ProviderHealth {
  provider_code: string;
  connection_status: string;
  free_count: number;
  purchased_count: number;
  limitations: string[];
}

export interface RegionCityItem {
  id: string;
  digit_capacity: number;
  city_name: string;
  region_name: string | null;
}

export interface RegionsLoadResult {
  ok: boolean;
  count: number;
  message: string;
}
