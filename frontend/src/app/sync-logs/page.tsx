"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { Page, SyncJob } from "@/lib/types/api";

export default function SyncLogsPage() {
  const [provider, setProvider] = useState("sipout");
  const [jobs, setJobs] = useState<Page<SyncJob> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SyncJob | null>(null);
  const [logs, setLogs] = useState<Page<{ id: string; level: string; message: string; created_at: string }> | null>(null);

  const load = () => {
    setError(null);
    apiFetch<Page<SyncJob>>(`/api/v1/providers/${provider}/sync/jobs?page=1&page_size=50`)
      .then(setJobs)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [provider]);

  useEffect(() => {
    if (!selected) return;
    apiFetch<Page<{ id: string; level: string; message: string; created_at: string }>>(
      `/api/v1/sync/jobs/${selected.id}/logs?page=1&page_size=100`,
    )
      .then(setLogs)
      .catch(() => setLogs(null));
  }, [selected]);

  return (
    <>
      <h1>Логи синхронизации</h1>
      <div className="filters">
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="sipout">sipout</option>
          <option value="runexis">runexis</option>
        </select>
        <button className="secondary" onClick={load}>
          Обновить
        </button>
      </div>
      {error && <div className="state error">{error}</div>}
      <div className="grid-2">
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Провайдер</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Started</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {(jobs?.items || []).map((j) => (
                <tr key={j.id} onClick={() => setSelected(j)} style={{ cursor: "pointer" }}>
                  <td>{j.provider_code}</td>
                  <td>{j.job_type}</td>
                  <td>
                    <span
                      className={`badge ${
                        j.status === "success" ? "ok" : j.status === "failed" ? "fail" : "warn"
                      }`}
                    >
                      {j.status}
                    </span>
                  </td>
                  <td>{j.started_at ? new Date(j.started_at).toLocaleString() : "—"}</td>
                  <td>{j.error_summary || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!jobs?.items?.length && !error && <div className="state">Нет jobs</div>}
        </div>
        <div className="panel">
          <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>
            {selected ? `Job ${selected.id.slice(0, 8)}…` : "Выберите job"}
          </h2>
          {selected && (
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.8rem" }}>
              {JSON.stringify(selected.stats, null, 2)}
            </pre>
          )}
          <table>
            <thead>
              <tr>
                <th>Level</th>
                <th>Message</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {(logs?.items || []).map((l) => (
                <tr key={l.id}>
                  <td>{l.level}</td>
                  <td>{l.message}</td>
                  <td>{new Date(l.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
