"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { HighlightText } from "@/components/numbers/HighlightText";
import {
  applyDirectoryFilters,
  computeFacets,
  type DirectoryColumn,
} from "@/lib/directory/filters";
import { formatCount } from "@/lib/format";
import type { ColumnFilters, FacetResponse } from "@/lib/types/api";

type Props<T extends { id: string }> = {
  items: T[];
  columns: DirectoryColumn<T>[];
  searchPlaceholder: string;
  searchChipLabel: string;
  searchValue: (row: T) => string;
  tableClassName: string;
  loading: boolean;
  error: string | null;
  exporting: boolean;
  importing: boolean;
  emptyText: string;
  onExport: () => void;
  onImport: (file: File) => void;
  rowClassName?: (row: T) => string | undefined;
};

export function DirectoryExplorer<T extends { id: string }>({
  items,
  columns,
  searchPlaceholder,
  searchChipLabel,
  searchValue,
  tableClassName,
  loading,
  error,
  exporting,
  importing,
  emptyText,
  onExport,
  onImport,
  rowClassName,
}: Props<T>) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [openColumn, setOpenColumn] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setSearchQ(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const headers = useMemo(
    () => Object.fromEntries(columns.map((col) => [col.key, col.header])),
    [columns],
  );

  const visible = useMemo(
    () => applyDirectoryFilters(items, columns, filters, searchQ, searchValue),
    [items, columns, filters, searchQ, searchValue],
  );

  const hasActiveFilters =
    Object.keys(filters).length > 0 || searchInput.trim().length > 0;
  const busy = exporting || importing;

  const setColumnFilter = (field: string, values: string[]) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (values.length === 0) delete next[field];
      else next[field] = values;
      return next;
    });
  };

  const removeFacetValue = (field: string, value: string) => {
    setColumnFilter(
      field,
      (filters[field] ?? []).filter((v) => v !== value),
    );
  };

  const clearAll = () => {
    setFilters({});
    setSearchInput("");
    setSearchQ("");
    setOpenColumn(null);
  };

  const facetLoader = useCallback(
    async ({
      column,
      filters: facetFilters,
      searchQ: qSearch,
      q,
    }: {
      column: string;
      filters: ColumnFilters;
      searchQ: string;
      q: string;
    }): Promise<FacetResponse> =>
      computeFacets(items, columns, column, facetFilters, qSearch, searchValue, q),
    [items, columns, searchValue],
  );

  return (
    <>
      <div className="filters">
        <button
          type="button"
          className="secondary"
          disabled={!hasActiveFilters}
          onClick={clearAll}
        >
          Сбросить фильтры
        </button>
        <input
          className="filters-phone-search"
          type="search"
          value={searchInput}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button
          type="button"
          className="secondary"
          disabled={busy || loading}
          onClick={onExport}
        >
          {exporting ? "Экспорт…" : "Экспорт XLSX"}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || loading}
          onClick={() => fileInputRef.current?.click()}
        >
          {importing ? "Импорт…" : "Импорт XLSX"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onImport(file);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
        />
        {!exporting && !loading && (
          <span className="filters-meta">
            {items.length === 0
              ? "0 записей"
              : `загружено ${formatCount(visible.length)} из ${formatCount(items.length)}`}
          </span>
        )}
      </div>
      <ActiveFiltersBar
        filters={filters}
        headers={headers}
        numberLocalQ={searchQ}
        searchChipLabel={searchChipLabel}
        onRemoveFacet={removeFacetValue}
        onClearNumberLocalQ={() => {
          setSearchInput("");
          setSearchQ("");
        }}
      />
      {error && <div className="state error">{error}</div>}
      <div className="table-scroll">
        <table className={tableClassName}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key}>
                  <ColumnFilterDropdown
                    facetLoader={facetLoader}
                    column={col.key}
                    header={col.header}
                    open={openColumn === col.key}
                    selected={filters[col.key] ?? []}
                    filters={filters}
                    numberLocalQ={searchQ}
                    onToggle={() =>
                      setOpenColumn((cur) => (cur === col.key ? null : col.key))
                    }
                    onChange={(values) => setColumnFilter(col.key, values)}
                    onClear={() => setColumnFilter(col.key, [])}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id} className={rowClassName?.(row)}>
                {columns.map((col) => {
                  const display = col.text(row);
                  return (
                    <td key={col.key}>
                      {col.highlight ? (
                        <HighlightText text={display} query={searchQ} />
                      ) : (
                        display
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && items.length === 0 && <div className="state">Загрузка…</div>}
        {!loading && !importing && !error && items.length === 0 && (
          <div className="state">{emptyText}</div>
        )}
        {!loading && !error && items.length > 0 && visible.length === 0 && (
          <div className="state">Нет данных. Сбросьте фильтры.</div>
        )}
      </div>
    </>
  );
}
