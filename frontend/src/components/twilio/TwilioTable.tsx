"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import { apiDownload, apiFetch } from "@/lib/api/client";
import { formatCount, formatDecimal } from "@/lib/format";
import { useInfinitePage } from "@/lib/hooks/useInfinitePage";
import { encodeFilters } from "@/lib/numbers/filters";
import type {
  ColumnFilters,
  FacetResponse,
  TwilioCoverageRow,
  TwilioNumberItem,
  TwilioSyncJob,
} from "@/lib/types/api";

type Col = {
  key: string;
  header: string;
  value: (row: TwilioNumberItem) => string | number | boolean | null | undefined;
};

const TWILIO_COLUMNS: Col[] = [
  { key: "country_name", header: "Страна", value: (r) => r.country_name },
  { key: "phone_number", header: "Номер", value: (r) => r.phone_number },
  { key: "number_type", header: "Тип", value: (r) => r.number_type },
  { key: "region", header: "Регион", value: (r) => r.region },
  { key: "locality", header: "Город", value: (r) => r.locality },
  { key: "period_price", header: "Абонплата", value: (r) => formatDecimal(r.period_price) },
  { key: "voice", header: "Voice", value: (r) => r.voice },
  { key: "sms", header: "SMS", value: (r) => r.sms },
  { key: "mms", header: "MMS", value: (r) => r.mms },
  { key: "fax", header: "Fax", value: (r) => r.fax },
  { key: "address_requirements", header: "Адрес", value: (r) => r.address_requirements },
];

const HEADER_MAP = Object.fromEntries(TWILIO_COLUMNS.map((c) => [c.key, c.header]));
const ACTIVE_STATUSES = new Set(["pending", "running"]);

function cellText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

function countText(value: number | null | undefined, type: string | null | undefined): string {
  if (type !== "local") return "—";
  if (value == null || value === 0) return "—";
  return formatCount(value);
}

function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU");
}

function jobStatusLabel(job: TwilioSyncJob | null): string {
  if (!job) return "Нет прогона";
  if (ACTIVE_STATUSES.has(job.status)) return "Идёт";
  if (job.status === "success") return "Успешно";
  if (job.status === "failed") return "Ошибка";
  return job.status;
}

function rowStatusText(row: TwilioCoverageRow): string {
  if (row.status === "running") return row.detail ? `сейчас · ${row.detail}` : "сейчас";
  if (row.status === "success") return row.detail || "";
  if (row.status === "failed") return row.detail || "ошибка";
  return "";
}

export function TwilioTable() {
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [openColumn, setOpenColumn] = useState<string | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
  const [job, setJob] = useState<TwilioSyncJob | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [regionsOpen, setRegionsOpen] = useState(false);

  const sortBy = "country_name";
  const sortDir: "asc" | "desc" = "asc";

  useEffect(() => {
    const t = setTimeout(() => setSearchQ(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

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
      if (searchQ) params.set("q", searchQ);
      return `/api/v1/twilio/numbers?${params}`;
    },
    [filtersKey, searchQ],
  );

  const { items, total, hasMore, loading, loadingMore, error, loadMore } =
    useInfinitePage<TwilioNumberItem>({
      getPath,
      deps: [filtersKey, searchQ, sortBy, sortDir, reloadTick],
    });

  const facetLoader = useCallback(
    async (args: {
      column: string;
      filters: ColumnFilters;
      searchQ: string;
      q: string;
    }) => {
      const params = new URLSearchParams({ column: args.column, limit: "200" });
      const encoded = encodeFilters(args.filters);
      if (encoded) params.set("filters", encoded);
      if (args.searchQ) params.set("q", args.searchQ);
      if (args.q) params.set("value_q", args.q);
      return apiFetch<FacetResponse>(`/api/v1/twilio/facets?${params}`);
    },
    [],
  );

  const loadJob = useCallback(async () => {
    const latest = await apiFetch<TwilioSyncJob | null>("/api/v1/twilio/sync/latest");
    setJob(latest);
    return latest;
  }, []);

  useEffect(() => {
    void loadJob().catch(() => undefined);
  }, [loadJob]);

  const syncActive = Boolean(job && ACTIVE_STATUSES.has(job.status));

  useEffect(() => {
    if (!syncActive) return;
    const timer = setInterval(() => {
      void loadJob()
        .then((latest) => {
          if (latest && !ACTIVE_STATUSES.has(latest.status)) {
            setReloadTick((n) => n + 1);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, [syncActive, loadJob]);

  const startSync = async () => {
    setStarting(true);
    setSyncError(null);
    try {
      const started = await apiFetch<TwilioSyncJob>("/api/v1/twilio/sync", { method: "POST" });
      setJob(started);
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Не удалось запустить синхронизацию");
    } finally {
      setStarting(false);
    }
  };

  const exportXlsx = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const params = new URLSearchParams({ sort_by: sortBy, sort_dir: sortDir });
      if (filtersKey) params.set("filters", filtersKey);
      if (searchQ) params.set("q", searchQ);
      const blob = await apiDownload(`/api/v1/twilio/export.xlsx?${params}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "twilio-numbers.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Ошибка экспорта");
    } finally {
      setExporting(false);
    }
  };

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
    setSearchInput("");
    setSearchQ("");
    setOpenColumn(null);
  };

  const hasActiveFilters = Object.keys(filters).length > 0 || searchInput.trim().length > 0;
  const summary = job?.progress?.summary;
  const coverageRows = job?.progress?.rows ?? [];

  return (
    <div className="panel numbers-panel">
      <div className="filters">
        <button type="button" className="secondary" disabled={!hasActiveFilters} onClick={clearAll}>
          Сбросить фильтры
        </button>
        <input
          className="filters-phone-search"
          type="search"
          value={searchInput}
          placeholder="Страна, номер, регион, город"
          aria-label="Поиск номеров Twilio"
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button
          type="button"
          onClick={() => {
            setRegionsOpen(true);
            void loadJob().catch(() => undefined);
          }}
        >
          Загрузка регионов
        </button>
        <button type="button" disabled title="Будет в следующей итерации">
          Загрузка номеров
        </button>
        <button
          type="button"
          className="secondary"
          disabled={exporting || (loading && items.length === 0)}
          onClick={() => void exportXlsx()}
        >
          {exporting ? "Экспорт…" : "Экспорт XLSX"}
        </button>
        {!loading && (
          <span className="filters-meta">
            {items.length > 0
              ? `загружено ${formatCount(items.length)} из ${formatCount(total)}`
              : total === 0
                ? "0 записей"
                : null}
          </span>
        )}
      </div>

      <div className="notice" role="note">
        Выборка, не полный список. Twilio не отдаёт весь инвентарь — в таблице сохранённые номера
        последней загрузки регионов.
      </div>
      {syncError && <div className="state error">{syncError}</div>}
      {exportError && <div className="state error">{exportError}</div>}

      <ActiveFiltersBar
        filters={filters}
        headers={HEADER_MAP}
        numberLocalQ={searchQ}
        searchChipLabel="Поиск"
        onRemoveFacet={removeFacetValue}
        onClearNumberLocalQ={() => {
          setSearchInput("");
          setSearchQ("");
        }}
      />

      {error && <div className="state error">{error}</div>}

      <div className="table-scroll" ref={setScrollRoot}>
        <table>
          <thead>
            <tr>
              {TWILIO_COLUMNS.map((col) => (
                <th key={col.key}>
                  <ColumnFilterDropdown
                    facetLoader={facetLoader}
                    column={col.key}
                    header={col.header}
                    open={openColumn === col.key}
                    selected={filters[col.key] ?? []}
                    filters={filters}
                    numberLocalQ={searchQ}
                    onToggle={() => setOpenColumn((cur) => (cur === col.key ? null : col.key))}
                    onChange={(values) => setColumnFilter(col.key, values)}
                    onClear={() => setColumnFilter(col.key, [])}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                {TWILIO_COLUMNS.map((col) => (
                  <td key={col.key}>{cellText(col.value(row))}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && items.length === 0 && <div className="state">Загрузка…</div>}
        {!loading && !error && items.length === 0 && (
          <div className="state">
            Нет сохранённых номеров. Откройте «Загрузка регионов» и запустите синхронизацию.
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

      {regionsOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Загрузка регионов Twilio"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            zIndex: 40,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1.5rem",
          }}
          onClick={() => setRegionsOpen(false)}
        >
          <div
            className="panel"
            style={{ width: "min(1100px, 100%)", maxHeight: "90vh", overflow: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="filters" style={{ justifyContent: "space-between" }}>
              <strong>Загрузка регионов</strong>
              <button type="button" className="secondary" onClick={() => setRegionsOpen(false)}>
                Закрыть
              </button>
            </div>
            <div className="notice" role="status">
              <div>Статус: {jobStatusLabel(job)}</div>
              <div>Начало: {formatWhen(job?.started_at)}</div>
              <div>Окончание: {formatWhen(job?.finished_at)}</div>
              <div>Запросы: {formatCount(summary?.requests ?? 0)}</div>
              <div>Города: {formatCount(summary?.cities_total ?? 0)}</div>
              <div>Уникальные номера: {formatCount(summary?.numbers_unique ?? 0)}</div>
              <div>Последний успешный cutover: {formatWhen(job?.last_success_at)}</div>
              {job?.error_summary && <div>Ошибка: {job.error_summary}</div>}
            </div>
            <div className="filters">
              <button type="button" disabled={starting || syncActive} onClick={() => void startSync()}>
                {syncActive ? "Синхронизация…" : "Синхронизация"}
              </button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Страна</th>
                    <th>Тип</th>
                    <th>Регионы</th>
                    <th>Города</th>
                    <th>Абонплата</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {coverageRows.map((row) => (
                    <tr key={`${row.country_iso}-${row.number_type}`}>
                      <td>{row.country_name || row.country_iso || "—"}</td>
                      <td>{row.number_type || "—"}</td>
                      <td>{countText(row.region_count, row.number_type)}</td>
                      <td>{countText(row.city_count, row.number_type)}</td>
                      <td>
                        {row.period_price != null && row.period_price !== ""
                          ? `${formatDecimal(String(row.period_price))} ${row.price_unit || ""}`.trim()
                          : "—"}
                      </td>
                      <td>{rowStatusText(row) || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {coverageRows.length === 0 && (
                <div className="state">Нет строк. Нажмите «Синхронизация», чтобы загрузить страны и типы.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
