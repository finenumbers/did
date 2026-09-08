export type HighlightSpan = { start: number; end: number };

export function concatHighlightRanges(
  countryPrefix: string,
  areaPrefix: string,
  query?: string,
): { country: HighlightSpan | null; area: HighlightSpan | null } {
  const q = query?.trim() ?? "";
  const country = countryPrefix || "";
  const area = areaPrefix || "";
  const concat = country + area;
  if (!q || !concat) {
    return { country: null, area: null };
  }

  const idx = concat.toLowerCase().indexOf(q.toLowerCase());
  if (idx < 0) {
    return { country: null, area: null };
  }

  const start = idx;
  const end = idx + q.length;
  const split = country.length;
  const countryRange =
    start < split ? { start, end: Math.min(end, split) } : null;
  const areaRange =
    end > split
      ? { start: Math.max(start - split, 0), end: end - split }
      : null;
  return { country: countryRange, area: areaRange };
}
