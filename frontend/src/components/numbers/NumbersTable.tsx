"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColumnFilters, NumberItem } from "@/lib/types/api";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { CertaintyCell } from "@/components/numbers/CertaintyCell";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import { formatCount, formatPoints, formatPrice } from "@/lib/format";
import { apiUrl } from "@/lib/api/client";
import { useInfinitePage } from "@/lib/hooks/useInfinitePage";
import { displayProviderCode, encodeFilters } from "@/lib/numbers/filters";

type Col = {
  key: string;
  header: string;
  value: (row: NumberItem) => string | number | boolean | null | undefined;
  verification?: (row: NumberItem) => string | undefined;
  mode: "facet" | "plain";
};

function fv(row: NumberItem, field: string): string | undefined {
  return row.field_verification?.[field];
}

/** Full unified catalog columns (same set on free and purchased pages). */
const CATALOG_COLUMNS: Col[] = [
  {
    key: "provider_code",
    header: "Провайдер",
    value: (r) => displayProviderCode(r.provider_code),
    mode: "facet",
  },
  {
    key: "abc_code",
    header: "ABC",
    value: (r) => r.abc_code,
    verification: (r) => fv(r, "abc_code"),
    mode: "facet",
  },
  {
    key: "number_local",
    header: "Номер",
    value: (r) => r.number_local,
    verification: (r) => fv(r, "number_local"),
    mode: "facet",
  },
  {
    key: "status_raw",
    header: "Статус",
    value: (r) => r.status_raw,
    verification: (r) => fv(r, "status_raw"),
    mode: "facet",
  },
  {
    key: "region_name",
    header: "Регион",
    value: (r) => r.region_name,
    verification: (r) => fv(r, "region_name"),
    mode: "facet",
  },
  {
    key: "city_name",
    header: "Город",
    value: (r) => r.city_name,
    verification: (r) => fv(r, "city_name"),
    mode: "facet",
  },
  {
    key: "buy_price",
    header: "Покупка",
    value: (r) => formatPrice(r.buy_price),
    verification: (r) => fv(r, "buy_price"),
    mode: "facet",
  },
  {
    key: "period_price",
    header: "Абонплата",
    value: (r) => formatPrice(r.period_price),
    verification: (r) => fv(r, "period_price"),
    mode: "facet",
  },
  {
    key: "mask",
    header: "Маска",
    value: (r) => r.mask,
    verification: (r) => fv(r, "mask"),
    mode: "facet",
  },
  {
    key: "display_mask",
    header: "Display mask",
    value: (r) => r.display_mask,
    verification: (r) => fv(r, "display_mask"),
    mode: "facet",
  },
  {
    key: "book_date",
    header: "Book date",
    value: (r) => r.book_date,
    verification: (r) => fv(r, "book_date"),
    mode: "facet",
  },
  {
    key: "number_type",
    header: "Тип",
    value: (r) => r.number_type,
    verification: (r) => fv(r, "number_type"),
    mode: "facet",
  },
  {
    key: "points",
    header: "Баллы",
    value: (r) => formatPoints(r.points),
    verification: (r) => fv(r, "points"),
    mode: "facet",
  },
  {
    key: "date_from",
    header: "date_from",
    value: (r) => r.date_from,
    verification: (r) => fv(r, "date_from"),
    mode: "facet",
  },
  {
    key: "last_operation_date",
    header: "last_operation_date",
    value: (r) => r.last_operation_date,
    verification: (r) => fv(r, "last_operation_date"),
    mode: "facet",
  },
  {
    key: "operator",
    header: "Оператор",
    value: (r) => r.operator,
    verification: (r) => fv(r, "operator"),
    mode: "facet",
  },
  {
    key: "operator_id",
    header: "operator_id",
    value: (r) => r.operator_id,
    verification: (r) => fv(r, "operator_id"),
    mode: "facet",
  },
  {
    key: "manager_id",
    header: "manager_id",
    value: (r) => r.manager_id,
    verification: (r) => fv(r, "manager_id"),
    mode: "facet",
  },
  {
    key: "notes",
    header: "notes",
    value: (r) => r.notes,
    verification: (r) => fv(r, "notes"),
    mode: "facet",
  },
  {
    key: "abcdef",
    header: "abcdef",
    value: (r) => r.abcdef,
    verification: (r) => fv(r, "abcdef"),
    mode: "facet",
  },
  {
    key: "order_id",
    header: "order_id",
    value: (r) => r.order_id,
    verification: (r) => fv(r, "order_id"),
    mode: "facet",
  },
  {
    key: "doc_status",
    header: "doc_status",
    value: (r) => r.doc_status,
    verification: (r) => fv(r, "doc_status"),
    mode: "facet",
  },
  {
    key: "doc_required",
    header: "doc_required",
    value: (r) => r.doc_required,
    verification: (r) => fv(r, "doc_required"),
    mode: "facet",
  },
  {
    key: "order_doc_required",
    header: "order_doc_required",
    value: (r) => r.order_doc_required,
    verification: (r) => fv(r, "order_doc_required"),
    mode: "facet",
  },
  {
    key: "sign",
    header: "sign",
    value: (r) => r.sign,
    verification: (r) => fv(r, "sign"),
    mode: "facet",
  },
  {
    key: "tariff",
    header: "Тариф",
    value: (r) => r.tariff,
    verification: (r) => fv(r, "tariff"),
    mode: "facet",
  },
  {
    key: "class",
    header: "Класс",
    value: (r) => r.class,
    verification: (r) => fv(r, "class"),
    mode: "facet",
  },
  {
    key: "partner",
    header: "Партнёр",
    value: (r) => r.partner,
    verification: (r) => fv(r, "partner"),
    mode: "facet",
  },
  {
    key: "project",
    header: "Проект",
    value: (r) => r.project,
    verification: (r) => fv(r, "project"),
    mode: "facet",
  },
  {
    key: "equipment",
    header: "Оборудование",
    value: (r) => r.equipment,
    verification: (r) => fv(r, "equipment"),
    mode: "facet",
  },
  {
    key: "mapping_confidence",
    header: "confidence",
    value: (r) => r.mapping_confidence,
    mode: "facet",
  },
  {
    key: "last_seen_at",
    header: "Обновлено",
    value: (r) => new Date(r.last_seen_at).toLocaleString(),
    mode: "facet",
  },
];

const HEADER_MAP = Object.fromEntries(CATALOG_COLUMNS.map((c) => [c.key, c.header]));

export function NumbersTable({ kind }: { kind: "free" | "purchased" }) {
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [numberLocalInput, setNumberLocalInput] = useState("");
  const [numberLocalQ, setNumberLocalQ] = useState("");
  const [sortBy] = useState("abc_code");
  const [sortDir] = useState<"asc" | "desc">("asc");
  const [openColumn, setOpenColumn] = useState<string | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setNumberLocalQ(numberLocalInput), 300);
    return () => clearTimeout(t);
  }, [numberLocalInput]);

  const filtersKey = useMemo(() => encodeFilters(filters) ?? "", [filters]);

  const getPath = useCallback(
    (page: number, pageSize: number) => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      if (filtersKey) params.set("filters", filtersKey);
      if (numberLocalQ) params.set("number_local_q", numberLocalQ);
      return `/api/v1/numbers/${kind}?${params}`;
    },
    [kind, sortBy, sortDir, filtersKey, numberLocalQ],
  );

  const { items, total, hasMore, loading, loadingMore, error, loadMore } =
    useInfinitePage<NumberItem>({
      getPath,
      deps: [kind, sortBy, sortDir, filtersKey, numberLocalQ],
    });

  const setColumnFilter = (field: string, values: string[]) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (values.length === 0) delete next[field];
      else next[field] = values;
      return next;
    });
  };

  const removeFacetValue = (field: string, value: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      const values = (next[field] ?? []).filter((v) => v !== value);
      if (values.length === 0) delete next[field];
      else next[field] = values;
      return next;
    });
  };

  const clearAll = () => {
    setFilters({});
    setNumberLocalInput("");
    setNumberLocalQ("");
    setOpenColumn(null);
  };

  const hasActiveFilters =
    Object.keys(filters).length > 0 || numberLocalInput.trim().length > 0;

  const exportXlsx = () => {
    setExporting(true);
    setExportError(null);
    const params = new URLSearchParams({
      sort_by: sortBy,
      sort_dir: sortDir,
    });
    if (filtersKey) params.set("filters", filtersKey);
    if (numberLocalQ) params.set("number_local_q", numberLocalQ);
    const url = apiUrl(`/api/v1/numbers/${kind}/export.xlsx?${params}`);

    // Prefer fetch so auth proxy + HTTP errors are visible; fall back to iframe
    // only for very large exports where buffering may be heavy.
    if (total > 50_000) {
      const iframe = document.createElement("iframe");
      iframe.style.display = "none";
      iframe.setAttribute("aria-hidden", "true");
      iframe.src = url;
      document.body.appendChild(iframe);
      const waitMs = total > 200_000 ? 120_000 : 75_000;
      window.setTimeout(() => setExporting(false), waitMs);
      window.setTimeout(() => iframe.remove(), waitMs + 180_000);
      return;
    }

    void (async () => {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const msg =
            (data as { error?: { message?: string }; detail?: string })?.error?.message ||
            (data as { detail?: string })?.detail ||
            res.statusText ||
            "Ошибка экспорта";
          throw new Error(msg);
        }
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${kind}-numbers.xlsx`;
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) {
        setExportError(e instanceof Error ? e.message : "Ошибка экспорта");
      } finally {
        setExporting(false);
      }
    })();
  };

  return (
    <div className="panel numbers-panel">
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
          value={numberLocalInput}
          placeholder="Номер телефона"
          aria-label="Номер телефона"
          onChange={(e) => setNumberLocalInput(e.target.value)}
        />
        <button
          type="button"
          className="secondary"
          disabled={exporting || (loading && items.length === 0)}
          onClick={() => void exportXlsx()}
        >
          {exporting ? "Экспорт…" : "Экспорт XLSX"}
        </button>
        {!exporting && !loading && (
          <span className="filters-meta">
            {items.length > 0
              ? `загружено ${formatCount(items.length)} из ${formatCount(total)}`
              : total === 0
                ? "0 записей"
                : null}
          </span>
        )}
      </div>
      {exporting && (
        <div className="export-banner" role="status">
          Формируется XLSX
          {total > 0 ? ` по ${formatCount(total)} строкам` : ""} —
          дождитесь начала загрузки в браузере
          {total > 50_000 ? " (полная свободная нумерация ~1 мин)" : ""}.
        </div>
      )}
      {exportError && <div className="state error">{exportError}</div>}
      <ActiveFiltersBar
        filters={filters}
        headers={HEADER_MAP}
        numberLocalQ={numberLocalQ}
        onRemoveFacet={removeFacetValue}
        onClearNumberLocalQ={() => {
          setNumberLocalInput("");
          setNumberLocalQ("");
        }}
      />

      {error && <div className="state error">{error}</div>}

      <div className="table-scroll" ref={setScrollRoot}>
        <table>
          <thead>
            <tr>
              {CATALOG_COLUMNS.map((col) => (
                <th key={col.key}>
                  {col.mode === "facet" ? (
                    <ColumnFilterDropdown
                      kind={kind}
                      column={col.key}
                      header={col.header}
                      open={openColumn === col.key}
                      selected={filters[col.key] ?? []}
                      filters={filters}
                      numberLocalQ={numberLocalQ}
                      onToggle={() =>
                        setOpenColumn((cur) => (cur === col.key ? null : col.key))
                      }
                      onChange={(values) => setColumnFilter(col.key, values)}
                      onClear={() => setColumnFilter(col.key, [])}
                    />
                  ) : (
                    <span className="col-header-label">{col.header}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                {CATALOG_COLUMNS.map((col) => (
                  <td key={col.key}>
                    {col.verification ? (
                      <CertaintyCell
                        value={col.value(row)}
                        verification={col.verification(row)}
                        highlight={
                          col.key === "number_local" ? numberLocalQ : undefined
                        }
                      />
                    ) : (
                      <span>{col.value(row) ?? "—"}</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && items.length === 0 && <div className="state">Загрузка…</div>}
        {!loading && !error && items.length === 0 && (
          <div className="state">
            Нет данных. Запустите синхронизацию на странице «Синхронизация» или сбросьте фильтры.
          </div>
        )}
        <InfiniteScrollSentinel
          root={scrollRoot}
          hasMore={hasMore}
          loading={loadingMore || (loading && items.length > 0)}
          onLoadMore={loadMore}
          loadedCount={items.length}
          total={total}
        />
      </div>
    </div>
  );
}
