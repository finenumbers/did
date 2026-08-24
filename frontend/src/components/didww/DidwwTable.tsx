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
  DidwwGroupItem,
  DidwwSyncJob,
  FacetResponse,
} from "@/lib/types/api";

type Col = {
  key: string;
  header: string;
  value: (row: DidwwGroupItem) => string | number | boolean | null | undefined;
};

const DIDWW_FEATURE_FLAGS = [
  "voice_in",
  "voice_out",
  "t38",
  "sms_in",
  "p2p",
  "a2p",
  "emergency",
  "cnam_out",
] as const;

function hasDidwwFeature(features: string | null | undefined, flag: string): boolean {
  if (!features) return false;
  return features.split(",").some((part) => part.trim() === flag);
}

/** DIDWW coverage columns — deliberately separate from the RU catalog column set. */
const DIDWW_COLUMNS: Col[] = [
  { key: "country_name", header: "Страна", value: (r) => r.country_name },
  { key: "country_iso", header: "ISO", value: (r) => r.country_iso },
  { key: "country_prefix", header: "Код страны", value: (r) => r.country_prefix },
  { key: "region_name", header: "Регион", value: (r) => r.region_name },
  { key: "city_name", header: "Город", value: (r) => r.city_name },
  { key: "area_prefix", header: "Префикс", value: (r) => r.area_prefix },
  { key: "did_type", header: "Тип", value: (r) => r.did_type },
  { key: "buy_price", header: "Покупка", value: (r) => formatDecimal(r.buy_price) },
  { key: "period_price", header: "Абонплата", value: (r) => formatDecimal(r.period_price) },
  { key: "channels_included", header: "Каналы", value: (r) => r.channels_included },
  { key: "stock_count", header: "В наличии", value: (r) => r.stock_count },
  { key: "number_select", header: "Выбор номера", value: (r) => r.number_select },
  ...DIDWW_FEATURE_FLAGS.map((flag) => ({
    key: flag,
    header: flag,
    value: (r: DidwwGroupItem) => hasDidwwFeature(r.features, flag),
  })),
  { key: "needs_registration", header: "Регистрация", value: (r) => r.needs_registration },
  { key: "is_metered", header: "Поминутно", value: (r) => r.is_metered },
];

const HEADER_MAP = Object.fromEntries(DIDWW_COLUMNS.map((c) => [c.key, c.header]));

const ACTIVE_STATUSES = new Set(["pending", "running"]);

function cellText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

function syncStatusText(job: DidwwSyncJob): string {
  const stages = job.stages || [];
  const running = stages.find((s) => s.status === "running");
  if (ACTIVE_STATUSES.has(job.status)) {
    return running
      ? `Синхронизация: ${running.label}${running.detail ? ` — ${running.detail}` : ""}`
      : "Синхронизация запущена…";
  }
  if (job.status === "failed") {
    return `Ошибка синхронизации: ${job.error_summary || "неизвестная ошибка"}`;
  }
  if (job.status === "success") {
    const groups = job.counts?.groups;
    const at = job.finished_at ? new Date(job.finished_at).toLocaleString("ru-RU") : "";
    return `Последняя синхронизация: ${
      groups != null ? `${formatCount(groups)} групп` : "успешно"
    }${at ? ` · ${at}` : ""}`;
  }
  return `Статус: ${job.status}`;
}

export function DidwwTable() {
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [openColumn, setOpenColumn] = useState<string | null>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);
  const [job, setJob] = useState<DidwwSyncJob | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

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
      return `/api/v1/didww/groups?${params}`;
    },
    [filtersKey, searchQ, sortBy, sortDir],
  );

  const { items, total, hasMore, loading, loadingMore, error, loadMore } =
    useInfinitePage<DidwwGroupItem>({
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
      return apiFetch<FacetResponse>(`/api/v1/didww/facets?${params}`);
    },
    [],
  );

  const loadJob = useCallback(async () => {
    const latest = await apiFetch<DidwwSyncJob | null>("/api/v1/didww/sync/latest");
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
      const started = await apiFetch<DidwwSyncJob>("/api/v1/didww/sync", { method: "POST" });
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
      const blob = await apiDownload(`/api/v1/didww/export.xlsx?${params}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "didww-coverage.xlsx";
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

  const hasActiveFilters =
    Object.keys(filters).length > 0 || searchInput.trim().length > 0;

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
          value={searchInput}
          placeholder="Страна, регион, город, префикс"
          aria-label="Поиск покрытия DIDWW"
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button
          type="button"
          disabled={starting || syncActive}
          onClick={() => void startSync()}
        >
          {syncActive ? "Синхронизация…" : "Синхронизировать DIDWW"}
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

      {job && (
        <div className={job.status === "failed" ? "state error" : "notice"} role="status">
          {syncStatusText(job)}
        </div>
      )}
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
              {DIDWW_COLUMNS.map((col) => (
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
            {items.map((row) => (
              <tr key={row.id}>
                {DIDWW_COLUMNS.map((col) => (
                  <td key={col.key}>{cellText(col.value(row))}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && items.length === 0 && <div className="state">Загрузка…</div>}
        {!loading && !error && items.length === 0 && (
          <div className="state">
            Нет данных. Укажите API-ключ DIDWW в «Настройках» и нажмите «Синхронизировать
            DIDWW», либо сбросьте фильтры.
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
