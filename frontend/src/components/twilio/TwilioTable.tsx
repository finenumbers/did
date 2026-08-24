"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ActiveFiltersBar } from "@/components/numbers/ActiveFiltersBar";
import { ColumnFilterDropdown } from "@/components/numbers/ColumnFilterDropdown";
import { InfiniteScrollSentinel } from "@/components/table/InfiniteScrollSentinel";
import { apiDownload, apiFetch } from "@/lib/api/client";
import { formatCount, formatDecimal } from "@/lib/format";
import { useInfinitePage } from "@/lib/hooks/useInfinitePage";
import { encodeFilters, formatTwilioNumberType } from "@/lib/numbers/filters";
import type {
  ColumnFilters,
  FacetResponse,
  Page,
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
  { key: "number_type", header: "Тип", value: (r) => formatTwilioNumberType(r.number_type) },
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

function optionalCount(value: number | null | undefined): string {
  if (value == null || value === 0) return "—";
  return formatCount(value);
}

function formatLoadDate(value: string | null | undefined): string {
  if (!value) return "Загрузка";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function requestsText(summary: TwilioSyncJob["progress"]["summary"] | undefined): string {
  const done = summary?.requests ?? 0;
  const total = summary?.requests_total;
  if (total == null) return formatCount(done);
  return `${formatCount(done)} / ${formatCount(total)}`;
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
  const [numbersOpen, setNumbersOpen] = useState(false);
  const [coverageRowsDb, setCoverageRowsDb] = useState<TwilioCoverageRow[]>([]);
  const [hasCatalog, setHasCatalog] = useState(false);
  const [numbersJob, setNumbersJob] = useState<TwilioSyncJob | null>(null);
  const [numbersError, setNumbersError] = useState<string | null>(null);
  const [startingNumbers, setStartingNumbers] = useState(false);

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
    if (latest?.has_catalog) setHasCatalog(true);
    return latest;
  }, []);

  const loadCoverage = useCallback(async () => {
    const page = await apiFetch<Page<TwilioCoverageRow>>(
      "/api/v1/twilio/coverage?page=1&page_size=500&sort_by=country_name&sort_dir=asc",
    );
    setCoverageRowsDb(page.items);
    setHasCatalog(page.total > 0);
    return page;
  }, []);

  const loadNumbersJob = useCallback(async () => {
    const latest = await apiFetch<TwilioSyncJob | null>("/api/v1/twilio/numbers/sync/latest");
    setNumbersJob(latest);
    return latest;
  }, []);

  useEffect(() => {
    void loadJob().catch(() => undefined);
    void loadCoverage().catch(() => undefined);
    void loadNumbersJob().catch(() => undefined);
  }, [loadJob, loadCoverage, loadNumbersJob]);

  const syncActive = Boolean(job && ACTIVE_STATUSES.has(job.status));
  const numbersActive = Boolean(numbersJob && ACTIVE_STATUSES.has(numbersJob.status));
  const twilioBusy = syncActive || numbersActive;

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
      void loadCoverage().catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, [syncActive, loadJob, loadCoverage]);

  useEffect(() => {
    if (!numbersActive) return;
    const timer = setInterval(() => {
      void loadNumbersJob()
        .then((latest) => {
          if (latest && !ACTIVE_STATUSES.has(latest.status)) {
            setReloadTick((n) => n + 1);
          }
        })
        .catch(() => undefined);
      void loadCoverage().catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, [numbersActive, loadNumbersJob, loadCoverage]);

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

  const startNumbers = async (row: TwilioCoverageRow) => {
    if (!row.country_iso || !row.number_type) return;
    setStartingNumbers(true);
    setNumbersError(null);
    try {
      const started = await apiFetch<TwilioSyncJob>("/api/v1/twilio/numbers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_iso: row.country_iso, number_type: row.number_type }),
      });
      setNumbersJob(started);
    } catch (e) {
      setNumbersError(e instanceof Error ? e.message : "Не удалось запустить загрузку номеров");
    } finally {
      setStartingNumbers(false);
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
  const numbersSummary = numbersJob?.progress?.summary;
  const numbersUniqueDb = coverageRowsDb.reduce((sum, row) => sum + (row.number_count ?? 0), 0);
  const numbersSummaryView = numbersActive
    ? numbersSummary
    : {
        requests: numbersSummary?.requests ?? 0,
        requests_total: numbersSummary?.requests_total ?? numbersSummary?.requests ?? 0,
        numbers_unique: numbersUniqueDb,
      };
  const numbersTarget = numbersJob?.progress?.target;
  const numbersRows = coverageRowsDb.map((row) => {
    const isRunning =
      numbersActive &&
      row.country_iso === numbersTarget?.country_iso &&
      row.number_type === numbersTarget?.number_type;
    if (!isRunning) return row;
    const live = numbersJob?.progress?.rows?.[0];
    return {
      ...row,
      status: "running",
      detail: live?.detail || row.detail,
      number_count: Math.max(live?.number_count ?? 0, row.number_count ?? 0),
    };
  });

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
        <button
          type="button"
          disabled={!hasCatalog}
          title={hasCatalog ? undefined : "Сначала выполните «Загрузка регионов»"}
          onClick={() => {
            setNumbersOpen(true);
            void loadCoverage().catch(() => undefined);
            void loadNumbersJob().catch(() => undefined);
          }}
        >
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
        последней загрузки регионов и номеров.
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
              <div>Запросы: {requestsText(summary)}</div>
              <div>Города: {formatCount(summary?.cities_total ?? 0)}</div>
              <div>Уникальные номера: {formatCount(summary?.numbers_unique ?? 0)}</div>
              <div>Последний успешный cutover: {formatWhen(job?.last_success_at)}</div>
              {job?.error_summary && <div>Ошибка: {job.error_summary}</div>}
            </div>
            <div className="filters">
              <button type="button" disabled={starting || twilioBusy} onClick={() => void startSync()}>
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
                    <th>Номера</th>
                    <th>Абонплата</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {coverageRows.map((row) => (
                    <tr key={`${row.country_iso}-${row.number_type}`}>
                      <td>{row.country_name || row.country_iso || "—"}</td>
                      <td>{formatTwilioNumberType(row.number_type)}</td>
                      <td>{countText(row.region_count, row.number_type)}</td>
                      <td>{countText(row.city_count, row.number_type)}</td>
                      <td>{optionalCount(row.number_count)}</td>
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

      {numbersOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Загрузка номеров Twilio"
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
          onClick={() => setNumbersOpen(false)}
        >
          <div
            className="panel"
            style={{ width: "min(1200px, 100%)", maxHeight: "90vh", overflow: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="filters" style={{ justifyContent: "space-between" }}>
              <strong>Загрузка номеров</strong>
              <button type="button" className="secondary" onClick={() => setNumbersOpen(false)}>
                Закрыть
              </button>
            </div>
            <div className="notice" role="status">
              <div>Статус: {jobStatusLabel(numbersJob)}</div>
              <div>Начало: {formatWhen(numbersJob?.started_at)}</div>
              <div>Окончание: {formatWhen(numbersJob?.finished_at)}</div>
              <div>Запросы: {requestsText(numbersSummaryView)}</div>
              <div>Уникальные номера: {formatCount(numbersSummaryView?.numbers_unique ?? 0)}</div>
              {numbersJob?.error_summary && <div>Ошибка: {numbersJob.error_summary}</div>}
            </div>
            {numbersError && <div className="state error">{numbersError}</div>}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Страна</th>
                    <th>Тип</th>
                    <th>Регионы</th>
                    <th>Города</th>
                    <th>Номера</th>
                    <th>Абонплата</th>
                    <th>Загрузка</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {numbersRows.map((row) => {
                    const isRunning =
                      numbersActive &&
                      row.country_iso === numbersTarget?.country_iso &&
                      row.number_type === numbersTarget?.number_type;
                    return (
                      <tr key={`${row.country_iso}-${row.number_type}`}>
                        <td>{row.country_name || row.country_iso || "—"}</td>
                        <td>{formatTwilioNumberType(row.number_type)}</td>
                        <td>{countText(row.region_count, row.number_type)}</td>
                        <td>{countText(row.city_count, row.number_type)}</td>
                        <td>{optionalCount(row.number_count)}</td>
                        <td>
                          {row.period_price != null && row.period_price !== ""
                            ? `${formatDecimal(String(row.period_price))} ${row.price_unit || ""}`.trim()
                            : "—"}
                        </td>
                        <td>
                          {isRunning ? (
                            <span className="twilio-load-pending">в процессе</span>
                          ) : row.numbers_loaded ? (
                            <button
                              type="button"
                              className="twilio-load-btn green"
                              disabled={startingNumbers || twilioBusy}
                              onClick={() => void startNumbers(row)}
                            >
                              {formatLoadDate(row.numbers_synced_at)}
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="twilio-load-btn red"
                              disabled={startingNumbers || twilioBusy}
                              onClick={() => void startNumbers(row)}
                            >
                              Загрузка
                            </button>
                          )}
                        </td>
                        <td>{rowStatusText(row) || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {numbersRows.length === 0 && (
                <div className="state">Нет справочника. Сначала выполните «Загрузка регионов».</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
