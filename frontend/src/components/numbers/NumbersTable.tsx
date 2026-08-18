"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColumnFilters, NumberItem } from "@/lib/types/api";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { HighlightText } from "@/components/numbers/HighlightText";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import { formatCount, formatPoints, formatPrice } from "@/lib/format";
import { apiDownload, apiFetch } from "@/lib/api/client";
import { useInfinitePage } from "@/lib/hooks/useInfinitePage";
import { displayProviderCode, encodeFilters } from "@/lib/numbers/filters";

type Col = {
  key: string;
  header: string;
  value: (row: NumberItem) => string | number | boolean | null | undefined;
};

function cellText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

/** Full unified catalog columns (same set on free and purchased pages). */
const CATALOG_COLUMNS: Col[] = [
  {
    key: "provider_code",
    header: "Провайдер",
    value: (r) => displayProviderCode(r.provider_code),
  },
  {
    key: "abc_code",
    header: "ABC",
    value: (r) => r.abc_code,
  },
  {
    key: "number_local",
    header: "Номер",
    value: (r) => r.number_local,
  },
  {
    key: "number_category",
    header: "Категория",
    value: (r) => r.number_category,
  },
  {
    key: "status_raw",
    header: "Статус",
    value: (r) => r.status_raw,
  },
  {
    key: "city_name",
    header: "Город",
    value: (r) => r.city_name,
  },
  {
    key: "region_name",
    header: "Регион",
    value: (r) => r.region_name,
  },
  {
    key: "buy_price",
    header: "Покупка",
    value: (r) => formatPrice(r.buy_price),
  },
  {
    key: "period_price",
    header: "Абонплата",
    value: (r) => formatPrice(r.period_price),
  },
  {
    key: "mask",
    header: "Маска",
    value: (r) => r.mask,
  },
  {
    key: "display_mask",
    header: "Display mask",
    value: (r) => r.display_mask,
  },
  {
    key: "book_date",
    header: "Book date",
    value: (r) => r.book_date,
  },
  {
    key: "number_type",
    header: "Тип",
    value: (r) => r.number_type,
  },
  {
    key: "points",
    header: "Баллы",
    value: (r) => formatPoints(r.points),
  },
  {
    key: "date_from",
    header: "date_from",
    value: (r) => r.date_from,
  },
  {
    key: "last_operation_date",
    header: "last_operation_date",
    value: (r) => r.last_operation_date,
  },
  {
    key: "operator",
    header: "Оператор",
    value: (r) => r.operator,
  },
  {
    key: "rtu_connected",
    header: "Подключено в РТУ",
    value: (r) => r.rtu_connected,
  },
  {
    key: "operator_id",
    header: "operator_id",
    value: (r) => r.operator_id,
  },
  {
    key: "manager_id",
    header: "manager_id",
    value: (r) => r.manager_id,
  },
  {
    key: "notes",
    header: "notes",
    value: (r) => r.notes,
  },
  {
    key: "abcdef",
    header: "abcdef",
    value: (r) => r.abcdef,
  },
  {
    key: "order_id",
    header: "order_id",
    value: (r) => r.order_id,
  },
  {
    key: "doc_status",
    header: "doc_status",
    value: (r) => r.doc_status,
  },
  {
    key: "doc_required",
    header: "doc_required",
    value: (r) => r.doc_required,
  },
  {
    key: "order_doc_required",
    header: "order_doc_required",
    value: (r) => r.order_doc_required,
  },
  {
    key: "sign",
    header: "sign",
    value: (r) => r.sign,
  },
  {
    key: "tariff",
    header: "Тариф",
    value: (r) => r.tariff,
  },
  {
    key: "class",
    header: "Класс",
    value: (r) => r.class,
  },
  {
    key: "partner",
    header: "Партнёр",
    value: (r) => r.partner,
  },
  {
    key: "project",
    header: "Проект",
    value: (r) => r.project,
  },
  {
    key: "equipment",
    header: "Оборудование",
    value: (r) => r.equipment,
  },
  {
    key: "mapping_confidence",
    header: "confidence",
    value: (r) => r.mapping_confidence,
  },
  {
    key: "last_seen_at",
    header: "Обновлено",
    value: (r) => new Date(r.last_seen_at).toLocaleString(),
  },
];

const HEADER_MAP = Object.fromEntries(CATALOG_COLUMNS.map((c) => [c.key, c.header]));

export function NumbersTable({ kind }: { kind: "free" | "purchased" }) {
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [numberLocalInput, setNumberLocalInput] = useState("");
  const [numberLocalQ, setNumberLocalQ] = useState("");
  const sortBy = "abc_code";
  const sortDir: "asc" | "desc" = "asc";
  const [openColumn, setOpenColumn] = useState<string | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const columns = useMemo(
    () =>
      kind === "purchased"
        ? CATALOG_COLUMNS
        : CATALOG_COLUMNS.filter((c) => c.key !== "rtu_connected"),
    [kind],
  );

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
    setExportProgress(total > 0 ? `0 / ${formatCount(total)}` : "запуск…");

    void (async () => {
      try {
        type ExportJob = {
          id: string;
          status: string;
          rows_done: number;
          rows_total: number | null;
          from_snapshot?: boolean;
          error?: string | null;
          filename?: string;
        };
        const job = await apiFetch<ExportJob>(`/api/v1/numbers/${kind}/export-jobs`, {
          method: "POST",
          body: JSON.stringify({
            sort_by: sortBy,
            sort_dir: sortDir,
            filters: filtersKey || null,
            number_local_q: numberLocalQ || null,
          }),
        });

        let current = job;
        const started = Date.now();
        const maxWaitMs = 30 * 60 * 1000;
        while (current.status === "queued" || current.status === "running") {
          if (Date.now() - started > maxWaitMs) {
            throw new Error("Экспорт превысил 30 минут ожидания");
          }
          const done = formatCount(current.rows_done || 0);
          const tot =
            current.rows_total != null ? formatCount(current.rows_total) : formatCount(total);
          setExportProgress(`${done} / ${tot}`);
          await new Promise((r) => setTimeout(r, 1500));
          current = await apiFetch<ExportJob>(`/api/v1/numbers/export-jobs/${job.id}`);
        }

        if (current.status === "failed") {
          throw new Error(current.error || "Ошибка экспорта");
        }
        if (current.status !== "ready") {
          throw new Error(`Неожиданный статус экспорта: ${current.status}`);
        }

        setExportProgress(
          current.from_snapshot
            ? "скачивание готового файла…"
            : `скачивание ${formatCount(current.rows_done || total)} строк…`,
        );
        const blob = await apiDownload(`/api/v1/numbers/export-jobs/${job.id}/download`);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = current.filename || `${kind}-numbers.xlsx`;
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) {
        setExportError(e instanceof Error ? e.message : "Ошибка экспорта");
      } finally {
        setExporting(false);
        setExportProgress(null);
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
          {total > 0 ? ` по ${formatCount(total)} строкам` : ""}
          {exportProgress ? ` — ${exportProgress}` : ""} — дождитесь скачивания в браузере.
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
              {columns.map((col) => (
                <th key={col.key}>
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
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr
                key={row.id}
                className={
                  row.operator === "Нет в реестре"
                    ? "row-operator-not-in-registry"
                    : kind === "purchased" && row.rtu_connected === "Не подключено"
                      ? "row-rtu-not-connected"
                      : kind === "purchased" && row.rtu_connected === "Внешняя нумерация"
                        ? "row-rtu-external"
                        : undefined
                }
              >
                {columns.map((col) => (
                  <td key={col.key}>
                    <HighlightText
                      text={cellText(col.value(row))}
                      query={col.key === "number_local" ? numberLocalQ : undefined}
                    />
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
