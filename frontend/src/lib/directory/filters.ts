import type { ColumnFilters, FacetItem, FacetResponse } from "@/lib/types/api";
import { toFilterToken } from "@/lib/numbers/filters";

export type DirectoryColumn<T> = {
  key: string;
  header: string;
  /** Cell text, including "—" for empty. */
  text: (row: T) => string;
  /** Canonical value for facet/filter tokens; "" if empty. */
  facet: (row: T) => string;
  highlight?: boolean;
};

const FACET_LIMIT = 200;

export function matchesSearch(value: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return value.toLowerCase().includes(q);
}

export function rowMatchesFilters<T>(
  row: T,
  columns: DirectoryColumn<T>[],
  filters: ColumnFilters,
  excludeColumn?: string,
): boolean {
  const byKey = new Map(columns.map((col) => [col.key, col]));
  for (const [field, selected] of Object.entries(filters)) {
    if (!selected?.length || field === excludeColumn) continue;
    const col = byKey.get(field);
    if (!col) continue;
    const token = toFilterToken(col.facet(row));
    if (!selected.includes(token)) return false;
  }
  return true;
}

export function applyDirectoryFilters<T>(
  rows: T[],
  columns: DirectoryColumn<T>[],
  filters: ColumnFilters,
  searchQ: string,
  searchValue: (row: T) => string,
): T[] {
  const q = searchQ.trim();
  return rows.filter((row) => {
    if (q && !matchesSearch(searchValue(row), q)) return false;
    return rowMatchesFilters(row, columns, filters);
  });
}

export function computeFacets<T>(
  rows: T[],
  columns: DirectoryColumn<T>[],
  columnKey: string,
  filters: ColumnFilters,
  searchQ: string,
  searchValue: (row: T) => string,
  q: string,
  limit = FACET_LIMIT,
): FacetResponse {
  const col = columns.find((c) => c.key === columnKey);
  if (!col) {
    return { column: columnKey, items: [], truncated: false };
  }
  const needle = q.trim().toLowerCase();
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (searchQ.trim() && !matchesSearch(searchValue(row), searchQ)) continue;
    if (!rowMatchesFilters(row, columns, filters, columnKey)) continue;
    const raw = col.facet(row);
    const token = toFilterToken(raw);
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }
  let items: FacetItem[] = [...counts.entries()].map(([value, count]) => ({
    value: value === "__empty__" ? "" : value,
    count,
  }));
  if (needle) {
    items = items.filter((item) => {
      const label = item.value === "" ? "(пусто)" : item.value;
      return label.toLowerCase().includes(needle);
    });
  }
  items.sort((a, b) => b.count - a.count || a.value.localeCompare(b.value, "ru"));
  const truncated = items.length > limit;
  return { column: columnKey, items: items.slice(0, limit), truncated };
}
