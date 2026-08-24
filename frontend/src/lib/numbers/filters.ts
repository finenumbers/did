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

const PROVIDER_LABELS: Record<string, string> = {
  sipout: "SipOut",
  runexis: "Runexis",
  uis: "UIS",
  aurora: "Aurora Telecom",
  finenumbers: "Finenumbers",
  exolve: "Exolve",
  voximplant: "Voximplant",
  mcn: "MCN Telecom",
};

export function displayProviderCode(code: string): string {
  return PROVIDER_LABELS[code] ?? code;
}

const TWILIO_NUMBER_TYPE_LABELS: Record<string, string> = {
  local: "Local",
  toll_free: "Toll-free",
  mobile: "Mobile",
  voip: "VoIP",
  national: "National",
};

export function formatTwilioNumberType(type: string | null | undefined): string {
  if (type == null || type === "") return "—";
  return TWILIO_NUMBER_TYPE_LABELS[type] ?? type;
}

export function displayFacetValue(value: string, column?: string): string {
  if (value === "" || value === EMPTY_FILTER_TOKEN) return "(пусто)";
  if (column === "provider_code") return displayProviderCode(value);
  if (column === "number_type") return formatTwilioNumberType(value);
  return value;
}

export function toFilterToken(value: string): string {
  return value === "" ? EMPTY_FILTER_TOKEN : value;
}
