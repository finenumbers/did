/** Integer with space thousands separator, e.g. "379 099". */
export function formatCount(value: number): string {
  const int = Math.trunc(value);
  const sign = int < 0 ? "-" : "";
  const abs = Math.abs(int).toString();
  return sign + abs.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** Format price as a whole number with space thousands separator, e.g. "2 222". */
export function formatPrice(
  value: string | number | null | undefined,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const raw = typeof value === "number" ? value : Number(String(value).replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(raw)) return null;
  const int = Math.round(raw);
  const sign = int < 0 ? "-" : "";
  const abs = Math.abs(int).toString();
  return sign + abs.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/**
 * Keep fractional amounts intact, e.g. DIDWW SKU prices "0.3" or "1.5".
 * Rounding them like rubles would show every price as 0 or 1.
 */
export function formatDecimal(
  value: string | number | null | undefined,
  maxFractionDigits = 4,
): string | null {
  if (value === null || value === undefined || value === "") return null;
  const raw = typeof value === "number" ? value : Number(String(value).replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(raw)) return null;
  const [intPart, fractionPart] = Math.abs(raw).toFixed(maxFractionDigits).split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const fraction = (fractionPart ?? "").replace(/0+$/, "");
  const sign = raw < 0 ? "-" : "";
  return sign + (fraction ? `${grouped}.${fraction}` : grouped);
}
