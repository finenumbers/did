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

function countText(value: number | null | undefined): string {
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

function sameCoverageRow(
  row: { country_iso?: string | null; number_type?: string | null },
  target?: { country_iso?: string | null; number_type?: string | null } | null,
): boolean {
  return (
    (row.country_iso || "").trim().toUpperCase() === (target?.country_iso || "").trim().toUpperCase() &&
    (row.number_type || "").trim() === (target?.number_type || "").trim() &&
    Boolean(target?.country_iso && target?.number_type)
  );
}

function rowStatusText(row: TwilioCoverageRow, jobActive: boolean): string {
  if (row.status === "running") return row.detail || "0 / 1";
  if (row.status === "failed") return row.detail || "ошибка";
  if (!jobActive) return row.detail || "";
  if (row.status === "success") return row.detail || "готово";
  return "ожидание";
}

function requestsText(summary: TwilioSyncJob["progress"]["summary"] | undefined): string {
  const done = summary?.requests ?? 0;
  const total = summary?.requests_total;
  if (total == null) return formatCount(done);
  return `${formatCount(done)} / ${formatCount(total)}`;
}

function laterJob(a: TwilioSyncJob | null, b: TwilioSyncJob | null): TwilioSyncJob | null {
  if (!a) return b;
  if (!b) return a;
  const aAt = a.started_at || a.created_at || "";
  const bAt = b.started_at || b.created_at || "";
  return aAt >= bAt ? a : b;
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
  const [syncOpen, setSyncOpen] = useState(false);
  const [coverageRowsDb, setCoverageRowsDb] = useState<TwilioCoverageRow[]>([]);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [hasCatalog, setHasCatalog] = useState(false);
  const [numbersJob, setNumbersJob] = useState<TwilioSyncJob | null>(null);
  const [numbersError, setNumbersError] = useState<string | null>(null);
  const [startingNumbers, setStartingNumbers] = useState(false);
  const [wipeConfirm, setWipeConfirm] = useState(false);
  const [wiping, setWiping] = useState(false);

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
      keepPreviousOnReset: true,
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
    setCoverageLoading(true);
    try {
      const page = await apiFetch<Page<TwilioCoverageRow>>(
        "/api/v1/twilio/coverage?page=1&page_size=2000&sort_by=country_name&sort_dir=asc",
      );
      setCoverageRowsDb(page.items);
      setHasCatalog(page.total > 0);
      return page;
    } finally {
      setCoverageLoading(false);
    }
  }, []);

  const loadNumbersJob = useCallback(async () => {
    const latest = await apiFetch<TwilioSyncJob | null>("/api/v1/twilio/numbers/sync/latest");
    setNumbersJob(latest);
    return latest;
  }, []);

  useEffect(() => {
    void loadJob().catch(() => undefined);
    void loadNumbersJob().catch(() => undefined);
  }, [loadJob, loadNumbersJob]);

  useEffect(() => {
    if (!syncOpen) return;
    void loadCoverage().catch(() => undefined);
  }, [syncOpen, loadCoverage]);

  const syncActive = Boolean(job && ACTIVE_STATUSES.has(job.status));
  const numbersActive = Boolean(numbersJob && ACTIVE_STATUSES.has(numbersJob.status));
  const twilioBusy = syncActive || numbersActive;
  const displayJob = syncActive ? job : numbersActive ? numbersJob : laterJob(job, numbersJob);

  useEffect(() => {
    if (!twilioBusy) return;
    const timer = setInterval(() => {
      void loadJob()
        .then((latest) => {
          if (latest && !ACTIVE_STATUSES.has(latest.status)) {
            setReloadTick((n) => n + 1);
          }
        })
        .catch(() => undefined);
      void loadNumbersJob()
        .then((latest) => {
          if (latest && !ACTIVE_STATUSES.has(latest.status)) {
            setReloadTick((n) => n + 1);
          }
        })
        .catch(() => undefined);
      if (syncOpen) void loadCoverage().catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, [twilioBusy, syncOpen, loadJob, loadNumbersJob, loadCoverage]);

  const startCountries = async () => {
    setStarting(true);
    setSyncError(null);
    setWipeConfirm(false);
    try {
      const started = await apiFetch<TwilioSyncJob>("/api/v1/twilio/sync", { method: "POST" });
      setJob(started);
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Не удалось запустить загрузку стран");
    } finally {
      setStarting(false);
    }
  };

  const startNumbers = async (row?: TwilioCoverageRow) => {
    setStartingNumbers(true);
    setNumbersError(null);
    setWipeConfirm(false);
    try {
      const started = await apiFetch<TwilioSyncJob>("/api/v1/twilio/numbers/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          row?.country_iso && row.number_type
            ? { country_iso: row.country_iso, number_type: row.number_type }
            : {},
        ),
      });
      setNumbersJob(started);
    } catch (e) {
      setNumbersError(e instanceof Error ? e.message : "Не удалось запустить загрузку номеров");
    } finally {
      setStartingNumbers(false);
    }
  };

  const wipeData = async () => {
    setWiping(true);
    setSyncError(null);
    try {
      await apiFetch("/api/v1/twilio/wipe", { method: "POST" });
      setCoverageRowsDb([]);
      setHasCatalog(false);
      setJob(null);
      setNumbersJob(null);
      setWipeConfirm(false);
      setReloadTick((n) => n + 1);
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Не удалось стереть данные");
    } finally {
      setWiping(false);
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
  const summary = displayJob?.progress?.summary;
  const numbersTarget = numbersJob?.progress?.target;
  const tableRows = (
    syncActive ? (job?.progress?.rows ?? []) : coverageRowsDb
  ).map((row) => {
    const isRunning = numbersActive && sameCoverageRow(row, numbersTarget);
    if (!isRunning) return row;
    const live = numbersJob?.progress?.rows?.[0];
    return {
      ...row,
      status: "running",
      detail: live?.detail || row.detail,
      number_count: live?.number_count ?? row.number_count,
      region_count: live?.region_count ?? row.region_count,
      city_count: live?.city_count ?? row.city_count,
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
            setSyncOpen(true);
            setWipeConfirm(false);
            void loadJob().catch(() => undefined);
            void loadNumbersJob().catch(() => undefined);
          }}
        >
          Синхронизация
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

      {syncError && !syncOpen && <div className="state error">{syncError}</div>}
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
            Нет сохранённых номеров. Откройте «Синхронизация» и нажмите «Загрузка стран».
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

      {syncOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Синхронизация Twilio"
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
          onClick={() => setSyncOpen(false)}
        >
          <div
            className="panel"
            style={{ width: "min(1200px, 100%)", maxHeight: "90vh", overflow: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="filters" style={{ justifyContent: "space-between" }}>
              <strong>Синхронизация</strong>
              <div className="filters" style={{ marginBottom: 0 }}>
                <button type="button" disabled={starting || twilioBusy} onClick={() => void startCountries()}>
                  {syncActive ? "Загрузка стран…" : "Загрузка стран"}
                </button>
                <button
                  type="button"
                  disabled={startingNumbers || twilioBusy || !hasCatalog}
                  title={hasCatalog ? undefined : "Сначала выполните «Загрузка стран»"}
                  onClick={() => void startNumbers()}
                >
                  {numbersActive ? "Загрузка номеров…" : "Загрузка номеров"}
                </button>
                {wipeConfirm ? (
                  <>
                    <button type="button" className="secondary" disabled={wiping} onClick={() => setWipeConfirm(false)}>
                      Отмена
                    </button>
                    <button type="button" disabled={wiping || twilioBusy} onClick={() => void wipeData()}>
                      {wiping ? "Удаление…" : "Подтвердить удаление"}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="secondary"
                    disabled={wiping || twilioBusy}
                    onClick={() => setWipeConfirm(true)}
                  >
                    Стереть данные
                  </button>
                )}
                <button type="button" className="secondary" onClick={() => setSyncOpen(false)}>
                  Закрыть
                </button>
              </div>
            </div>
            <div className="notice" role="status">
              <div>Статус: {jobStatusLabel(displayJob)}</div>
              <div>Начало: {formatWhen(displayJob?.started_at)}</div>
              <div>Окончание: {formatWhen(displayJob?.finished_at)}</div>
              <div>Запросы: {requestsText(summary)}</div>
              <div>Города: {formatCount(summary?.cities_total ?? 0)}</div>
              <div>Уникальные номера: {formatCount(summary?.numbers_unique ?? 0)}</div>
              {displayJob?.error_summary && <div>Ошибка: {displayJob.error_summary}</div>}
            </div>
            {syncError && <div className="state error">{syncError}</div>}
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
                  {tableRows.map((row) => {
                    const isRunning = numbersActive && sameCoverageRow(row, numbersTarget);
                    return (
                      <tr key={`${row.country_iso}-${row.number_type}`}>
                        <td>{row.country_name || row.country_iso || "—"}</td>
                        <td>{formatTwilioNumberType(row.number_type)}</td>
                        <td>{countText(row.region_count)}</td>
                        <td>{countText(row.city_count)}</td>
                        <td>{countText(row.number_count)}</td>
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
                              disabled={startingNumbers || twilioBusy || !hasCatalog}
                              onClick={() => void startNumbers(row)}
                            >
                              Загрузка
                            </button>
                          )}
                        </td>
                        <td>{rowStatusText(row, twilioBusy) || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {coverageLoading && tableRows.length === 0 && <div className="state">Загрузка…</div>}
              {!coverageLoading && tableRows.length === 0 && (
                <div className="state">Нет строк. Нажмите «Загрузка стран», чтобы загрузить справочник.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
