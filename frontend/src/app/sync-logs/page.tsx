"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiDownload, apiFetch } from "@/lib/api/client";
import type { SyncRun, SyncStage } from "@/lib/types/api";

type DroppedExportMeta = {
  available?: boolean;
  unmapped?: number;
  duplicates?: number;
};

type InventorySummaryRow = {
  provider: string;
  kind: string;
  label: string;
  previous: number;
  current: number;
  delta: number;
  refused_wipe?: boolean;
  limited?: boolean;
};

type CatalogChecksum = {
  sum_free?: number;
  sum_purchased?: number;
  sum_total?: number;
  enrich_rows_scanned?: number | null;
  enrich_matches_catalog?: boolean | null;
};

/** Thousands with regular spaces: 31771 → "31 771". */
function formatCount(value: number | string): string {
  const n = typeof value === "number" ? value : Number(String(value).replace(/\s/g, ""));
  if (!Number.isFinite(n)) return String(value);
  const sign = n < 0 ? "-" : "";
  const abs = Math.trunc(Math.abs(n));
  return sign + String(abs).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function formatDelta(delta: number): string {
  if (delta > 0) return `+${formatCount(delta)}`;
  if (delta < 0) return formatCount(delta);
  return "0";
}

function formatPlainNumbers(text: string): string {
  return text.replace(/\d+/g, (m) => formatCount(m));
}

function renderStageDetail(s: SyncStage): ReactNode {
  const parts: string[] = [];
  if (s.detail) parts.push(s.detail);
  if (s.substage && s.substage !== s.detail) parts.push(s.substage);
  const cur = s.progress?.current;
  const tot = s.progress?.total;
  const running = s.status === "running";
  // Keep raw integers here — formatCount runs once in the token pass below.
  // Pre-formatting would insert spaces, then /\d+/ would split "100 000" into
  // "100" + "000" → "100 0".
  // Only while running: finished stages already have a full final detail and
  // must not append a second shortened counter line.
  if (running && cur != null && tot != null) {
    const alreadyInDetail =
      s.detail?.includes(`${cur}/${tot}`) ||
      s.detail?.includes(`${cur} / ${tot}`) ||
      s.substage?.includes(`${cur}/${tot}`) ||
      s.substage?.includes(`${cur} / ${tot}`);
    if (!alreadyInDetail) {
      parts.push(
        `${cur} / ${tot}${s.progress?.unit ? ` ${s.progress.unit}` : ""}`,
      );
    }
  } else if (running && cur != null) {
    const alreadyInDetail =
      s.detail?.includes(String(cur)) || s.substage?.includes(String(cur));
    if (!alreadyInDetail) {
      parts.push(String(cur));
    }
  }
  const raw = parts.filter(Boolean).join(" · ");
  if (!raw) return "—";

  // Tokenize known metrics / «Записано» so we can style them; format other digits once.
  // Highlight upserted / unmapped_dropped / duplicates_dropped only when value ≠ 0.
  const tokenRe =
    /(upserted=\d+|unmapped_dropped=\d+|duplicates_dropped=\d+|Записано\s+\d+|\d+)/g;
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = tokenRe.exec(raw)) !== null) {
    if (match.index > last) {
      nodes.push(raw.slice(last, match.index));
    }
    const tok = match[0];
    if (tok.startsWith("upserted=")) {
      const n = Number(tok.split("=")[1]);
      const label = `upserted=${formatCount(n)}`;
      nodes.push(
        n !== 0 ? (
          <span
            key={key++}
            style={{ color: "#2e7d32", fontWeight: 700, textDecoration: "underline" }}
          >
            {label}
          </span>
        ) : (
          <span key={key++}>{label}</span>
        ),
      );
    } else if (tok.startsWith("unmapped_dropped=")) {
      const n = Number(tok.split("=")[1]);
      const label = `unmapped_dropped=${formatCount(n)}`;
      nodes.push(
        n !== 0 ? (
          <span key={key++} style={{ color: "#c62828", fontWeight: 700 }}>
            {label}
          </span>
        ) : (
          <span key={key++}>{label}</span>
        ),
      );
    } else if (tok.startsWith("duplicates_dropped=")) {
      const n = Number(tok.split("=")[1]);
      const label = `duplicates_dropped=${formatCount(n)}`;
      nodes.push(
        n !== 0 ? (
          <span key={key++} style={{ color: "#1565c0", fontWeight: 700 }}>
            {label}
          </span>
        ) : (
          <span key={key++}>{label}</span>
        ),
      );
    } else if (tok.startsWith("Записано")) {
      const n = Number(tok.replace(/\D+/g, ""));
      nodes.push(
        <span key={key++} style={{ color: "#2e7d32", fontWeight: 700 }}>
          {`Записано ${formatCount(n)}`}
        </span>,
      );
    } else {
      nodes.push(<span key={key++}>{formatCount(tok)}</span>);
    }
    last = match.index + tok.length;
  }
  if (last < raw.length) {
    nodes.push(formatPlainNumbers(raw.slice(last)));
  }
  return <>{nodes}</>;
}

type SyncLogRow = {
  id: string;
  level: string;
  message: string;
  created_at: string;
};

function statusBadgeClass(status: string): string {
  if (status === "success" || status === "done") return "ok";
  if (status === "failed") return "fail";
  if (status === "running" || status === "pending" || status === "partial") return "warn";
  return "";
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "ожидание",
    running: "выполняется",
    done: "готово",
    success: "успех",
    failed: "ошибка",
    partial: "частично",
    skipped: "пропуск",
  };
  return map[status] || status;
}

function groupStages(stages: SyncStage[]): { group: string; stages: SyncStage[] }[] {
  const order: string[] = [];
  const map = new Map<string, SyncStage[]>();
  for (const stage of stages) {
    if (!map.has(stage.group)) {
      map.set(stage.group, []);
      order.push(stage.group);
    }
    map.get(stage.group)!.push(stage);
  }
  return order.map((group) => ({ group, stages: map.get(group)! }));
}

export default function SyncPage() {
  const [run, setRun] = useState<SyncRun | null>(null);
  const [logs, setLogs] = useState<SyncLogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheReady, setCacheReady] = useState<boolean | null>(null);
  const [cacheHint, setCacheHint] = useState<string | null>(null);
  const [downloadingDropped, setDownloadingDropped] = useState(false);
  const [downloadingDebugLog, setDownloadingDebugLog] = useState(false);

  const isActive = run?.status === "pending" || run?.status === "running";
  const canStart = cacheReady === true && !starting && !isActive;
  const droppedExport = (run?.stats?.dropped_export || null) as DroppedExportMeta | null;
  const inventorySummary = (run?.stats?.inventory_summary || []) as InventorySummaryRow[];
  const catalogChecksum = (run?.stats?.catalog_checksum || null) as CatalogChecksum | null;
  const inventorySplit = Boolean(run?.stats?.inventory_split);
  const inventorySplitProviders = Array.isArray(run?.stats?.inventory_split_providers)
    ? (run?.stats?.inventory_split_providers as string[])
    : [];
  const canDownloadDropped =
    !isActive && Boolean(droppedExport?.available) && !downloadingDropped;
  const canDownloadDebugLog = Boolean(run) && !downloadingDebugLog;

  const loadLatest = useCallback(async () => {
    try {
      const latest = await apiFetch<SyncRun | null>("/api/v1/sync/latest");
      setRun(latest);
      setError(null);
      return latest;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLogs = useCallback(async (runId: string) => {
    try {
      const page = await apiFetch<{ items: SyncLogRow[] }>(
        `/api/v1/sync/runs/${runId}/logs?page=1&page_size=100`,
      );
      setLogs(page.items || []);
    } catch (e) {
      setLogs([]);
      setError(e instanceof Error ? e.message : "Не удалось загрузить логи");
    }
  }, []);

  const loadCacheGate = useCallback(async () => {
    try {
      const status = await apiFetch<{
        min_cache_ready: boolean;
        missing_required: string[];
      }>("/api/v1/settings/pstn-inn-cache");
      setCacheReady(status.min_cache_ready);
      setCacheHint(
        status.min_cache_ready
          ? null
          : `Сначала загрузите кеш операторов в Настройках${
              status.missing_required?.length
                ? ` (не готово: ${status.missing_required.join(", ")})`
                : ""
            }`,
      );
    } catch {
      setCacheReady(false);
      setCacheHint("Не удалось проверить кеш операторов");
    }
  }, []);

  useEffect(() => {
    void loadLatest().then((latest) => {
      if (latest) void loadLogs(latest.id);
    });
    void loadCacheGate();
  }, [loadLatest, loadLogs, loadCacheGate]);

  useEffect(() => {
    if (!isActive || !run) return;
    const t = setInterval(() => {
      void loadLatest().then((latest) => {
        if (latest) void loadLogs(latest.id);
      });
    }, 2000);
    return () => clearInterval(t);
  }, [isActive, run?.id, loadLatest, loadLogs]);

  const downloadDroppedXlsx = async () => {
    setDownloadingDropped(true);
    setError(null);
    try {
      const blob = await apiDownload("/api/v1/sync/dropped.xlsx");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "sync-dropped-latest.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось скачать отчёт");
    } finally {
      setDownloadingDropped(false);
    }
  };

  const downloadDebugLog = async () => {
    setDownloadingDebugLog(true);
    setError(null);
    try {
      const blob = await apiDownload("/api/v1/sync/debug.log");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "sync-latest.log";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось скачать лог");
    } finally {
      setDownloadingDebugLog(false);
    }
  };

  const startSync = async () => {
    setStarting(true);
    setError(null);
    try {
      const started = await apiFetch<SyncRun>("/api/v1/sync/start", { method: "POST" });
      setRun(started);
      setLogs([]);
      void loadLogs(started.id);
    } catch (e) {
      if (e instanceof ApiError && e.code === "SYNC_ALREADY_RUNNING") {
        setError(e.message);
        await loadLatest();
      } else if (e instanceof ApiError && e.code === "PSTN_INN_CACHE_NOT_READY") {
        setError(e.message);
        await loadCacheGate();
      } else if (e instanceof ApiError && e.code === "PSTN_INN_CACHE_REFRESH_RUNNING") {
        setError("Идёт загрузка кеша операторов — дождитесь окончания в Настройках");
        await loadCacheGate();
      } else {
        setError(e instanceof Error ? e.message : "Не удалось запустить синхронизацию");
      }
    } finally {
      setStarting(false);
    }
  };

  const groups = useMemo(
    () => groupStages(run?.progress?.stages || []),
    [run?.progress?.stages],
  );

  return (
    <>
      <div className="filters">
        <button onClick={startSync} disabled={!canStart} title={cacheHint || undefined}>
          {starting ? "Запуск…" : isActive ? "Синхронизация…" : "Синхронизация"}
        </button>
        <button
          className="secondary"
          onClick={() => {
            void loadLatest().then((r) => r && loadLogs(r.id));
            void loadCacheGate();
          }}
        >
          Обновить
        </button>
        <button
          className="secondary"
          disabled={!canDownloadDropped}
          title={
            canDownloadDropped
              ? `unmapped=${formatCount(droppedExport?.unmapped ?? 0)}, duplicates=${formatCount(droppedExport?.duplicates ?? 0)}`
              : "Отчёт появится после завершения синхронизации"
          }
          onClick={() => void downloadDroppedXlsx()}
        >
          {downloadingDropped ? "Скачивание…" : "Скачать отброшенные (XLSX)"}
        </button>
        <button
          className="secondary"
          disabled={!canDownloadDebugLog}
          title={
            canDownloadDebugLog
              ? "Детальный лог текущей/последней синхронизации (можно скачать во время выполнения)"
              : "Лог появится после запуска синхронизации"
          }
          onClick={() => void downloadDebugLog()}
        >
          {downloadingDebugLog ? "Скачивание…" : "Скачать лог"}
        </button>
        {cacheReady === false && (
          <span className="filters-meta" style={{ color: "var(--muted)" }}>
            {cacheHint}{" "}
            <a href="/settings" style={{ color: "inherit", textDecoration: "underline" }}>
              Настройки
            </a>
          </span>
        )}
        {run && (
          <span className="filters-meta">
            Последний запуск:{" "}
            <span className={`badge ${statusBadgeClass(run.status)}`}>
              {statusLabel(run.status)}
            </span>
            {run.started_at ? ` · ${new Date(run.started_at).toLocaleString()}` : ""}
          </span>
        )}
      </div>

      {error && <div className="state error">{error}</div>}
      {loading && <div className="state">Загрузка…</div>}

      {!loading && !run && !error && cacheReady && (
        <div className="state">
          Запусков ещё не было. Нажмите «Синхронизация», чтобы загрузить все источники.
        </div>
      )}

      {run && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {inventorySplit && (
            <div className="state error" role="alert">
              Разрыв каталога (inventory split): free уже обновлён, purchased нет
              {inventorySplitProviders.length
                ? ` — ${inventorySplitProviders.join(", ")}`
                : ""}
              . Перезапустите синхронизацию или проверьте purchased у этих провайдеров.
            </div>
          )}
          <div className="panel">
            <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Этапы</h2>
            {run.error_summary && (
              <div className="state error" style={{ marginBottom: "0.75rem" }}>
                {run.error_summary}
              </div>
            )}
            {groups.map(({ group, stages }) => (
              <div key={group} className="sync-stages-group" style={{ marginBottom: "1rem" }}>
                <div
                  style={{
                    fontWeight: 600,
                    marginBottom: "0.4rem",
                    color: "var(--muted)",
                    fontSize: "0.85rem",
                  }}
                >
                  {group}
                </div>
                <table className="sync-stages-table">
                  <thead>
                    <tr>
                      <th>Этап</th>
                      <th>Статус</th>
                      <th>Детали</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stages.map((s) => (
                      <tr
                        key={s.id}
                        className={
                          run.progress.current_stage_id === s.id && s.status === "running"
                            ? "row-selected"
                            : undefined
                        }
                      >
                        <td>{s.label}</td>
                        <td>
                          <span className={`badge ${statusBadgeClass(s.status)}`}>
                            {statusLabel(s.status)}
                          </span>
                        </td>
                        <td className="sync-stage-detail">
                          {renderStageDetail(s)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {inventorySummary.length > 0 && (
            <div className="panel">
              <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Результат по источникам</h2>
              <p style={{ marginTop: 0, color: "var(--muted)", fontSize: "0.85rem" }}>
                Сколько номеров было в каталоге до синхронизации и сколько стало после полной
                перезагрузки (объём может вырасти или уменьшиться).
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Источник</th>
                      <th>Было</th>
                      <th>Стало</th>
                      <th>Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventorySummary.map((row) => (
                      <tr key={`${row.provider}-${row.kind}`}>
                        <td>
                          {row.label}
                          {row.refused_wipe ? (
                            <span className="badge fail" style={{ marginLeft: "0.5rem" }}>
                              отказ wipe
                            </span>
                          ) : null}
                          {row.limited ? (
                            <span className="badge warn" style={{ marginLeft: "0.5rem" }}>
                              limited
                            </span>
                          ) : null}
                        </td>
                        <td>{formatCount(Number(row.previous || 0))}</td>
                        <td>{formatCount(Number(row.current || 0))}</td>
                        <td>{formatDelta(Number(row.delta || 0))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {catalogChecksum ? (
                <p style={{ marginBottom: 0, marginTop: "0.75rem", fontSize: "0.85rem", color: "var(--muted)" }}>
                  Контрольная сумма: свободные{" "}
                  {formatCount(Number(catalogChecksum.sum_free || 0))} + купленные{" "}
                  {formatCount(Number(catalogChecksum.sum_purchased || 0))} ={" "}
                  {formatCount(Number(catalogChecksum.sum_total || 0))}
                  {catalogChecksum.enrich_rows_scanned != null
                    ? `; PSTN rows_scanned=${formatCount(Number(catalogChecksum.enrich_rows_scanned))}${
                        catalogChecksum.enrich_matches_catalog === true
                          ? " ✓"
                          : catalogChecksum.enrich_matches_catalog === false
                            ? " ≠"
                            : ""
                      }`
                    : ""}
                </p>
              ) : null}
            </div>
          )}

          <div className="panel">
            <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Лог</h2>
            {logs.length === 0 ? (
              <div className="state">Нет записей</div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Level</th>
                      <th>Message</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((l) => (
                      <tr key={l.id}>
                        <td>{l.level}</td>
                        <td>{l.message}</td>
                        <td>{new Date(l.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
