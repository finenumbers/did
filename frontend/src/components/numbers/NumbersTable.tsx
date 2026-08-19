"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColumnFilters, NumberItem } from "@/lib/types/api";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { HighlightText } from "@/components/numbers/HighlightText";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import { formatCount, formatPrice } from "@/lib/format";
import { API_URL, apiDownload, apiFetch } from "@/lib/api/client";
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
    key: "operator",
    header: "Оператор",
    value: (r) => r.operator,
  },
  {
    key: "buy_price",
    header: "Покупка (Входящая)",
    value: (r) => formatPrice(r.buy_price),
  },
  {
    key: "period_price",
    header: "Абонплата (Входящая)",
    value: (r) => formatPrice(r.period_price),
  },
  {
    key: "mask_purchase",
    header: "Покупка",
    value: (r) => formatPrice(r.mask_purchase),
  },
  {
    key: "type_label",
    header: "Тип",
    value: (r) => r.type_label,
  },
  {
    key: "premium",
    header: "Премиум",
    value: (r) => formatPrice(r.premium),
  },
  {
    key: "rtu_connected",
    header: "Подключено в РТУ",
    value: (r) => r.rtu_connected,
  },
];

function formatExportEta(startedMs: number, done: number, total: number): string | null {
  if (done < 2000 || total <= 0 || done >= total) return null;
  const elapsed = (Date.now() - startedMs) / 1000;
  if (elapsed < 1) return null;
  const left = (elapsed / done) * (total - done);
  if (left < 15) return "меньше минуты";
  if (left < 90) return "~1 мин";
  return `~${Math.round(left / 60)} мин`;
}

type ExportJob = {
  id: string;
  status: string;
  phase?: string | null;
  rows_done: number;
  rows_total: number | null;
  from_snapshot?: boolean;
  error?: string | null;
  filename?: string;
  ticket?: string | null;
};

function exportStatusText(
  job: ExportJob,
  fallbackTotal: number,
): { label: string; pct: number | null } {
  const done = job.rows_done || 0;
  const total = job.rows_total != null ? job.rows_total : fallbackTotal;
  const pct =
    total > 0 ? Math.min(99, Math.floor((done / total) * 100)) : null;
  if (job.phase === "closing") {
    return { label: "Сохранение файла на сервере…", pct: pct == null ? 99 : Math.max(pct, 99) };
  }
  if (job.status === "queued" || job.phase === "queued") {
    return { label: "В очереди…", pct: 0 };
  }
  const verb = job.from_snapshot ? "Запись снимка" : "Запись XLSX";
  const counts = `${formatCount(done)} / ${total > 0 ? formatCount(total) : "…"}`;
  const percent = pct != null ? ` (${pct}%)` : "";
  return { label: `${verb}: ${counts}${percent}`, pct };
}

function triggerNativeDownload(path: string, filename: string) {
  const a = document.createElement("a");
  a.href = `${API_URL}${path}`;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function downloadExportFile(job: ExportJob, kind: "free" | "purchased") {
  const filename = job.filename || `${kind}-numbers.xlsx`;
  if (job.ticket) {
    triggerNativeDownload(
      `/api/v1/numbers/export-jobs/${job.id}/download?ticket=${encodeURIComponent(job.ticket)}`,
      filename,
    );
    return;
  }
  const blob = await apiDownload(`/api/v1/numbers/export-jobs/${job.id}/download`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

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
  const [exportPct, setExportPct] = useState<number | null>(null);
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
    setExportPct(total > 0 ? 0 : null);
    setExportProgress(total > 0 ? `0 / ${formatCount(total)}` : "запуск…");

    void (async () => {
      try {
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

        const applyProgress = (next: ExportJob) => {
          if (next.status === "ready") {
            setExportPct(100);
            setExportProgress("Скачивание файла…");
            return;
          }
          const { label, pct } = exportStatusText(next, total);
          const eta = formatExportEta(
            started,
            next.rows_done || 0,
            next.rows_total != null ? next.rows_total : total,
          );
          setExportPct(pct);
          setExportProgress(eta ? `${label} · ${eta}` : label);
        };

        applyProgress(current);
        while (current.status === "queued" || current.status === "running") {
          if (Date.now() - started > maxWaitMs) {
            throw new Error("Экспорт превысил 30 минут ожидания");
          }
          await new Promise((r) => setTimeout(r, 800));
          current = await apiFetch<ExportJob>(`/api/v1/numbers/export-jobs/${job.id}`);
          applyProgress(current);
        }

        if (current.status === "failed") {
          throw new Error(current.error || "Ошибка экспорта");
        }
        if (current.status !== "ready") {
          throw new Error(`Неожиданный статус экспорта: ${current.status}`);
        }

        setExportProgress("Скачивание файла…");
        setExportPct(100);
        await downloadExportFile(current, kind);
      } catch (e) {
        setExportError(e instanceof Error ? e.message : "Ошибка экспорта");
      } finally {
        setExporting(false);
        setExportProgress(null);
        setExportPct(null);
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
          {exporting
            ? exportPct != null
              ? `Экспорт… ${exportPct}%`
              : "Экспорт…"
            : "Экспорт XLSX"}
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
          {exportProgress || "Экспорт…"}
          {exportPct != null && (
            <div className="export-progress-track" aria-hidden="true">
              <div className="export-progress-bar" style={{ width: `${exportPct}%` }} />
            </div>
          )}
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
                  <td key={col.key} className={col.key === "number_local" ? "col-number-local" : undefined}>
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
