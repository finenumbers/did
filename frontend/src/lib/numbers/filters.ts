import { formatCount } from "@/lib/format";
import type { ColumnFilters } from "@/lib/types/api";

const EMPTY_FILTER_TOKEN = "__empty__";

export function encodeFilters(filters: ColumnFilters): string | null {
  const cleaned: ColumnFilters = {};
  for (const [key, values] of Object.entries(filters)) {
    if (values?.length) cleaned[key] = values;
  }
  if (Object.keys(cleaned).length === 0) return null;
  return JSON.stringify(cleaned);
}

export function formatFacetCount(n: number): string {
  return formatCount(n);
}

const PROVIDER_LABELS: Record<string, string> = {
  sipout: "SipOut",
  runexis: "Runexis",
  uis: "UIS",
  aurora: "Aurora Telecom",
  finenumbers: "Finenumbers",
};

export function displayProviderCode(code: string): string {
  return PROVIDER_LABELS[code] ?? code;
}

export function displayFacetValue(value: string, column?: string): string {
  if (value === "" || value === EMPTY_FILTER_TOKEN) return "(пусто)";
  if (column === "provider_code") return displayProviderCode(value);
  return value;
}

export function toFilterToken(value: string): string {
  return value === "" ? EMPTY_FILTER_TOKEN : value;
}
