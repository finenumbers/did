"use client";

import type { ColumnFilters } from "@/lib/types/api";
import { displayFacetValue } from "@/lib/numbers/filters";

type Props = {
  filters: ColumnFilters;
  headers: Record<string, string>;
  numberLocalQ: string;
  searchChipLabel?: string;
  onRemoveFacet: (field: string, value: string) => void;
  onClearNumberLocalQ: () => void;
};

export function ActiveFiltersBar({
  filters,
  headers,
  numberLocalQ,
  searchChipLabel = "Номер телефона",
  onRemoveFacet,
  onClearNumberLocalQ,
}: Props) {
  const chips: { key: string; label: string; onRemove: () => void }[] = [];

  if (numberLocalQ) {
    chips.push({
      key: "number_local_q",
      label: `${searchChipLabel}: ${numberLocalQ}`,
      onRemove: onClearNumberLocalQ,
    });
  }

  for (const [field, values] of Object.entries(filters)) {
    const header = headers[field] ?? field;
    for (const value of values) {
      chips.push({
        key: `${field}:${value}`,
        label: `${header}: ${displayFacetValue(value, field)}`,
        onRemove: () => onRemoveFacet(field, value),
      });
    }
  }

  if (chips.length === 0) return null;

  return (
    <div className="active-filters">
      <span className="active-filters-label">Активные фильтры:</span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          className="active-filter-chip"
          onClick={chip.onRemove}
        >
          {chip.label}
          <span aria-hidden>×</span>
        </button>
      ))}
    </div>
  );
}
