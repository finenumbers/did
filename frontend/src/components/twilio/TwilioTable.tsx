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
  TwilioAvailableNumber,
  TwilioAvailableNumbersResponse,
  TwilioCoverageItem,
  TwilioSyncJob,
} from "@/lib/types/api";

type Col = {
  key: string;
  header: string;
  value: (row: TwilioCoverageItem) => string | number | boolean | null | undefined;
};

const TWILIO_COLUMNS: Col[] = [
  { key: "country_name", header: "Страна", value: (r) => r.country_name },
  { key: "country_iso", header: "ISO", value: (r) => r.country_iso },
  { key: "number_type", header: "Тип", value: (r) => r.number_type },
  { key: "period_price", header: "Абонплата", value: (r) => formatDecimal(r.period_price) },
  { key: "price_unit", header: "Валюта", value: (r) => r.price_unit },
  { key: "country_beta", header: "Beta", value: (r) => r.country_beta },
];

const HEADER_MAP = Object.fromEntries(TWILIO_COLUMNS.map((c) => [c.key, c.header]));
const ACTIVE_STATUSES = new Set(["pending", "running"]);

function cellText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  return String(value);
}

function cap(value: boolean | null | undefined): string {
  if (value === true) return "да";
  if (value === false) return "нет";
  return "—";
}

function containsPattern(index: number): string {
  return `*${String(index % 100).padStart(2, "0")}*`;
}

function syncStatusText(job: TwilioSyncJob): string {
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
    const rows = job.counts?.rows;
    const at = job.finished_at ? new Date(job.finished_at).toLocaleString("ru-RU") : "";
    return `Последняя синхронизация: ${
      rows != null ? `${formatCount(rows)} строк` : "успешно"
    }${at ? ` · ${at}` : ""}`;
  }
  return `Статус: ${job.status}`;
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
  const [openRow, setOpenRow] = useState<TwilioCoverageItem | null>(null);
  const [inRegion, setInRegion] = useState("");
  const [inLocality, setInLocality] = useState("");
  const [areaCode, setAreaCode] = useState("");
  const [contains, setContains] = useState("");
  const [sample, setSample] = useState<TwilioAvailableNumber[]>([]);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [sampleNote, setSampleNote] = useState<string | null>(null);
  const [shownNumbers, setShownNumbers] = useState<Set<string>>(new Set());
  const [rotateIndex, setRotateIndex] = useState(0);

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
      return `/api/v1/twilio/coverage?${params}`;
    },
    [filtersKey, searchQ],
  );

  const { items, total, hasMore, loading, loadingMore, error, loadMore } =
    useInfinitePage<TwilioCoverageItem>({
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
      a.download = "twilio-coverage.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Ошибка экспорта");
    } finally {
      setExporting(false);
    }
  };

  const fetchSample = async (
    row: TwilioCoverageItem,
    rotate: boolean,
    overlay?: { inRegion: string; inLocality: string; areaCode: string; contains: string },
  ) => {
    if (!row.country_iso || !row.number_type) return;
    setSampleLoading(true);
    setSampleError(null);
    setSampleNote(null);
    const region = overlay ? overlay.inRegion : inRegion;
    const locality = overlay ? overlay.inLocality : inLocality;
    const npa = overlay ? overlay.areaCode : areaCode;
    const pattern = overlay ? overlay.contains : contains;
    const params = new URLSearchParams({
      country: row.country_iso,
      type: row.number_type,
    });
    if (region.trim()) params.set("in_region", region.trim());
    if (locality.trim()) params.set("in_locality", locality.trim());
    if (npa.trim()) params.set("area_code", npa.trim());
    if (rotate) {
      params.set("contains", containsPattern(rotateIndex));
      setRotateIndex((n) => n + 1);
    } else if (pattern.trim()) {
      params.set("contains", pattern.trim());
    }
    try {
      const data = await apiFetch<TwilioAvailableNumbersResponse>(
        `/api/v1/twilio/available-numbers?${params}`,
      );
      const incoming = data.items.filter((n) => n.phone_number);
      const keys = incoming.map((n) => n.phone_number as string);
      const allKnown = keys.length > 0 && keys.every((n) => shownNumbers.has(n));
      if (rotate && allKnown) {
        setSampleNote("Twilio вернул ту же выборку");
      } else if (incoming.length === 0) {
        setSampleNote("В этой выборке номеров нет");
      }
      setSample(incoming);
      setShownNumbers((prev) => {
        const next = new Set(prev);
        for (const n of keys) next.add(n);
        return next;
      });
    } catch (e) {
      setSampleError(e instanceof Error ? e.message : "Не удалось загрузить номера");
    } finally {
      setSampleLoading(false);
    }
  };

  const openModal = (row: TwilioCoverageItem) => {
    setOpenRow(row);
    setInRegion("");
    setInLocality("");
    setAreaCode("");
    setContains("");
    setSample([]);
    setSampleError(null);
    setSampleNote(null);
    setShownNumbers(new Set());
    setRotateIndex(0);
    void fetchSample(row, false, {
      inRegion: "",
      inLocality: "",
      areaCode: "",
      contains: "",
    });
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
          placeholder="Страна, ISO, тип"
          aria-label="Поиск покрытия Twilio"
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button type="button" disabled={starting || syncActive} onClick={() => void startSync()}>
          {syncActive ? "Синхронизация…" : "Синхронизировать Twilio"}
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
              <tr
                key={row.id}
                onClick={() => openModal(row)}
                style={{ cursor: "pointer" }}
              >
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
            Нет данных. Укажите Account SID и Auth Token Twilio в «Настройках» и нажмите
            «Синхронизировать Twilio», либо сбросьте фильтры.
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

      {openRow && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Выборка номеров Twilio"
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
          onClick={() => setOpenRow(null)}
        >
          <div
            className="panel"
            style={{ width: "min(960px, 100%)", maxHeight: "90vh", overflow: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="filters" style={{ justifyContent: "space-between" }}>
              <strong>
                {openRow.country_name} ({openRow.country_iso}) · {openRow.number_type}
                {openRow.period_price != null
                  ? ` · ${formatDecimal(openRow.period_price)} ${openRow.price_unit || ""}`
                  : ""}
              </strong>
              <button type="button" className="secondary" onClick={() => setOpenRow(null)}>
                Закрыть
              </button>
            </div>
            <div className="filters">
              <input
                placeholder="Регион (US/CA, InRegion)"
                value={inRegion}
                onChange={(e) => setInRegion(e.target.value)}
              />
              <input
                placeholder="Город (InLocality)"
                value={inLocality}
                onChange={(e) => setInLocality(e.target.value)}
              />
              <input
                placeholder="Area code (US/CA)"
                value={areaCode}
                onChange={(e) => setAreaCode(e.target.value)}
              />
              <input
                placeholder="Contains"
                value={contains}
                onChange={(e) => setContains(e.target.value)}
              />
              <button
                type="button"
                disabled={sampleLoading}
                onClick={() => {
                  setShownNumbers(new Set());
                  setRotateIndex(0);
                  void fetchSample(openRow, false);
                }}
              >
                Найти
              </button>
              <button
                type="button"
                className="secondary"
                disabled={sampleLoading}
                onClick={() => void fetchSample(openRow, true)}
              >
                Другие номера
              </button>
            </div>
            {sampleLoading && <div className="state">Загрузка выборки…</div>}
            {sampleError && <div className="state error">{sampleError}</div>}
            {sampleNote && <div className="notice">{sampleNote}</div>}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Номер</th>
                    <th>Voice</th>
                    <th>SMS</th>
                    <th>MMS</th>
                    <th>Fax</th>
                    <th>Адрес</th>
                    <th>Регион</th>
                    <th>Город</th>
                  </tr>
                </thead>
                <tbody>
                  {sample.map((n) => (
                    <tr key={n.phone_number || n.friendly_name || Math.random()}>
                      <td>{n.phone_number || n.friendly_name || "—"}</td>
                      <td>{cap(n.voice)}</td>
                      <td>{cap(n.sms)}</td>
                      <td>{cap(n.mms)}</td>
                      <td>{cap(n.fax)}</td>
                      <td>{n.address_requirements || "—"}</td>
                      <td>{n.region || "—"}</td>
                      <td>{n.locality || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
