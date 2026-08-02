export type FieldVerification =
  | "documentation_verified"
  | "example_confirmed"
  | "derived"
  | "unresolved"
  | "missing";

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
  status_raw: string | null;
  region_name: string | null;
  city_name: string | null;
  price_amount: string | null;
  price_currency: string | null;
  has_sms: boolean | null;
  tariff_name: string | null;
  last_seen_at: string;
  is_currently_present: boolean;
  mapping_confidence: string;
  field_verification: Record<string, FieldVerification | string>;
}

export interface ProviderOut {
  id: string;
  code: string;
  name: string;
  is_enabled: boolean;
  capabilities: Record<string, { supported: boolean; action?: string; reason_code?: string }>;
  last_tested_at?: string | null;
  last_test_status?: string | null;
}

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

export interface SyncJob {
  id: string;
  provider_code: string;
  job_type: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown>;
  error_summary: string | null;
  created_at: string;
}

export interface ProviderHealth {
  provider_code: string;
  connection_status: string;
  free_count: number;
  purchased_count: number;
  limitations: string[];
}
