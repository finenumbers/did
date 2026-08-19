"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { HighlightText } from "@/components/numbers/HighlightText";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import {
  applyDirectoryFilters,
  computeFacets,
  type DirectoryColumn,
} from "@/lib/directory/filters";
import { apiFetch } from "@/lib/api/client";
import { formatCount } from "@/lib/format";
import { useInfinitePage } from "@/lib/hooks/useInfinitePage";
import { encodeFilters } from "@/lib/numbers/filters";
import type { ColumnFilters, FacetResponse } from "@/lib/types/api";

export type DirectoryServerQuery = {
  searchQ: string;
  filters: ColumnFilters;
};

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
  getServerPath?: (
    page: number,
    pageSize: number,
    query: DirectoryServerQuery,
  ) => string;
  getServerFacets?: (args: {
    column: string;
    filters: ColumnFilters;
    searchQ: string;
    q: string;
  }) => string;
  reloadToken?: number;
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
  getServerPath,
  getServerFacets,
  reloadToken = 0,
}: Props<T>) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
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

  const filtersKey = useMemo(() => encodeFilters(filters) ?? "", [filters]);
  const serverEnabled = Boolean(getServerPath);

  const getPath = useCallback(
    (page: number, pageSize: number) => {
      if (!getServerPath) return null;
      return getServerPath(page, pageSize, { searchQ, filters });
    },
    [getServerPath, searchQ, filters],
  );

  const server = useInfinitePage<T>({
    getPath,
    deps: [searchQ, filtersKey, reloadToken],
    enabled: serverEnabled,
  });

  const visible = useMemo(
    () =>
      serverEnabled
        ? server.items
        : applyDirectoryFilters(items, columns, filters, searchQ, searchValue),
    [serverEnabled, server.items, items, columns, filters, searchQ, searchValue],
  );

  const listLoading = serverEnabled ? server.loading : loading;
  const listLoadingMore = serverEnabled ? server.loadingMore : false;
  const displayError = error || (serverEnabled ? server.error : null);
  const total = serverEnabled ? server.total : items.length;
  const sourceCount = serverEnabled ? server.items.length : items.length;

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
    }): Promise<FacetResponse> => {
      if (getServerFacets) {
        return apiFetch<FacetResponse>(
          getServerFacets({
            column,
            filters: facetFilters,
            searchQ: qSearch,
            q,
          }),
        );
      }
      return computeFacets(
        items,
        columns,
        column,
        facetFilters,
        qSearch,
        searchValue,
        q,
      );
    },
    [getServerFacets, items, columns, searchValue],
  );

  const meta = (() => {
    if (serverEnabled) {
      if (visible.length > 0) {
        return `загружено ${formatCount(visible.length)} из ${formatCount(total)}`;
      }
      return total === 0 ? "0 записей" : null;
    }
    if (items.length === 0) return "0 записей";
    return `загружено ${formatCount(visible.length)} из ${formatCount(items.length)}`;
  })();

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
          disabled={busy || listLoading}
          onClick={onExport}
        >
          {exporting ? "Экспорт…" : "Экспорт XLSX"}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || listLoading}
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
        {!exporting && !listLoading && meta && (
          <span className="filters-meta">{meta}</span>
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
      {displayError && <div className="state error">{displayError}</div>}
      <div className="table-scroll" ref={setScrollRoot}>
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
                    <td key={col.key} className={col.cellClassName}>
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
        {listLoading && sourceCount === 0 && <div className="state">Загрузка…</div>}
        {!listLoading && !importing && !displayError && visible.length === 0 && (
          <div className="state">
            {hasActiveFilters ? "Нет данных. Сбросьте фильтры." : emptyText}
          </div>
        )}
        {serverEnabled && (
          <InfiniteScrollSentinel
            root={scrollRoot}
            hasMore={server.hasMore}
            loading={listLoadingMore || (listLoading && visible.length > 0)}
            onLoadMore={server.loadMore}
            loadedCount={visible.length}
            total={total}
          />
        )}
      </div>
    </>
  );
}
