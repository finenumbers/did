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
  mask_purchase: string | null;
  type_label: string | null;
  premium: string | null;
  operator: string | null;
  rtu_connected?: string | null;
  is_currently_present: boolean;
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

/** One DIDWW DID Group (coverage row), not an individual E.164 number. */
export interface DidwwGroupItem {
  id: string;
  provider_group_key: string;
  country_name: string | null;
  country_iso: string | null;
  country_prefix: string | null;
  region_name: string | null;
  city_name: string | null;
  area_prefix: string | null;
  did_type: string | null;
  buy_price: string | null;
  period_price: string | null;
  channels_included: number | null;
  stock_count: number | null;
  number_select: boolean | null;
  features: string | null;
  needs_registration: boolean | null;
  is_metered: boolean | null;
}

export interface DidwwSyncJob {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  triggered_by: string | null;
  created_at: string;
  counts: Record<string, number>;
  progress: {
    current_stage_id?: string | null;
    stages?: SyncStage[];
  };
  stages: SyncStage[];
}

export interface TwilioCoverageRow {
  country_iso: string | null;
  country_name: string | null;
  number_type: string | null;
  status?: string;
  detail?: string;
  region_count?: number | null;
  city_count?: number | null;
  period_price?: string | number | null;
  price_unit?: string | null;
}

export interface TwilioNumberItem {
  id: string;
  phone_number: string;
  country_name: string | null;
  country_iso: string | null;
  number_type: string | null;
  region: string | null;
  locality: string | null;
  period_price: string | null;
  price_unit: string | null;
  voice: boolean | null;
  sms: boolean | null;
  mms: boolean | null;
  fax: boolean | null;
  address_requirements: string | null;
}

export interface TwilioSyncJob {
  id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  triggered_by: string | null;
  created_at: string;
  counts: Record<string, number>;
  progress: {
    current_stage_id?: string | null;
    stages?: SyncStage[];
    summary?: {
      requests?: number;
      cities_total?: number;
      numbers_unique?: number;
    };
    current?: {
      country_iso?: string | null;
      in_region?: string | null;
      contains?: string | null;
    };
    rows?: TwilioCoverageRow[];
  };
  stages: SyncStage[];
  last_success_at?: string | null;
}

export interface RegionCityItem {
  id: string;
  abc: string;
  digit_capacity: number;
  city_name: string;
  region_name: string | null;
}

export interface RegionsLoadResult {
  ok: boolean;
  count: number;
  message: string;
}

export interface MaskTypeItem {
  id: string;
  digit_capacity: string;
  category: string;
  abc: string;
  mask: string;
  type_label: string | null;
  premium: string | null;
  purchase: string | null;
}

export interface MaskTypesLoadResult {
  ok: boolean;
  count: number;
  updated: number;
  inserted: number;
  message: string;
}
