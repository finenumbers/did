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
