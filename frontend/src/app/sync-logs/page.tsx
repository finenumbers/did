"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

function formatDelta(delta: number): string {
  if (delta > 0) return `+${delta.toLocaleString()}`;
  if (delta < 0) return delta.toLocaleString();
  return "0";
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

  const stageDetail = (s: SyncStage): string => {
    const parts: string[] = [];
    if (s.detail) parts.push(s.detail);
    if (s.substage && s.substage !== s.detail) parts.push(s.substage);
    const cur = s.progress?.current;
    const tot = s.progress?.total;
    if (cur != null && tot != null) {
      parts.push(`${cur} / ${tot}${s.progress?.unit ? ` ${s.progress.unit}` : ""}`);
    } else if (cur != null) {
      parts.push(String(cur));
    }
    return parts.filter(Boolean).join(" · ") || "—";
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
              ? `unmapped=${droppedExport?.unmapped ?? 0}, duplicates=${droppedExport?.duplicates ?? 0}`
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
          <div className="panel">
            <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Этапы</h2>
            {run.error_summary && (
              <div className="state error" style={{ marginBottom: "0.75rem" }}>
                {run.error_summary}
              </div>
            )}
            {groups.map(({ group, stages }) => (
              <div key={group} style={{ marginBottom: "1rem" }}>
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
                <table>
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
                        <td style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                          {stageDetail(s)}
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
                        <td>{Number(row.previous || 0).toLocaleString()}</td>
                        <td>{Number(row.current || 0).toLocaleString()}</td>
                        <td>{formatDelta(Number(row.delta || 0))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
