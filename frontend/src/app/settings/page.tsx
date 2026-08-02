"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch, isCapabilityLimited } from "@/lib/api/client";
import type { ProviderOut, ProviderSettings, SyncJob } from "@/lib/types/api";

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [selected, setSelected] = useState("sipout");
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [mode, setMode] = useState("full");
  const [dryRun, setDryRun] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = async (code: string) => {
    const [plist, s] = await Promise.all([
      apiFetch<ProviderOut[]>("/api/v1/providers"),
      apiFetch<ProviderSettings>(`/api/v1/providers/${code}/settings`),
    ]);
    setProviders(plist);
    setSettings(s);
    setBaseUrl(s.base_url || "");
  };

  useEffect(() => {
    reload(selected).catch((e) => setError(e.message));
  }, [selected]);

  const save = async () => {
    setError(null);
    setMessage(null);
    const auth_settings =
      selected === "sipout" ? { key: token || undefined } : { token: token || undefined };
    try {
      const s = await apiFetch<ProviderSettings>(`/api/v1/providers/${selected}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          base_url: baseUrl || null,
          auth_settings: token ? auth_settings : undefined,
        }),
      });
      setSettings(s);
      setToken("");
      setMessage("Настройки сохранены");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    }
  };

  const test = async () => {
    setError(null);
    setMessage(null);
    try {
      const r = await apiFetch<{ ok: boolean; message: string }>(
        `/api/v1/providers/${selected}/test-connection`,
        { method: "POST" },
      );
      setMessage(r.ok ? `OK: ${r.message}` : `FAIL: ${r.message}`);
      await reload(selected);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка теста");
    }
  };

  const startSync = async () => {
    setError(null);
    setMessage(null);
    try {
      const job = await apiFetch<SyncJob>(`/api/v1/providers/${selected}/sync`, {
        method: "POST",
        body: JSON.stringify({ mode, dry_run: dryRun }),
      });
      setMessage(`Sync job ${job.id}: ${job.status}`);
    } catch (e) {
      if (isCapabilityLimited(e)) {
        setError((e as ApiError).message);
      } else {
        setError(e instanceof Error ? e.message : "Ошибка sync");
      }
    }
  };

  const caps = providers.find((p) => p.code === selected)?.capabilities;

  return (
    <>
      <h1>Настройки</h1>
      <div className="notice">
        Интеграции провайдеров основаны на uploaded documentation contracts:
        <code> docs/providers/*-contract.md</code> и raw HTML в{" "}
        <code>docs/providers/*/raw/</code>. Неподтверждённые поля помечаются в UI как
        example-confirmed / unresolved.
      </div>

      <div className="filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="sipout">SipOut</option>
          <option value="runexis">Runexis</option>
        </select>
      </div>

      {message && <div className="notice">{message}</div>}
      {error && <div className="state error">{error}</div>}

      <div className="grid-2">
        <div className="panel">
          <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Подключение</h2>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
            {settings?.docs_notice}
          </p>
          <div className="filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <label>
              Base URL
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} style={{ width: "100%" }} />
            </label>
            <label>
              {selected === "sipout" ? "API key" : "Bearer token"}
              <input
                type="password"
                placeholder={
                  settings
                    ? `текущее: ${JSON.stringify(settings.auth_settings_masked)}`
                    : "секрет"
                }
                value={token}
                onChange={(e) => setToken(e.target.value)}
                style={{ width: "100%" }}
              />
            </label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button onClick={save}>Сохранить</button>
              <button className="secondary" onClick={test}>
                Test connection
              </button>
            </div>
            {settings?.last_test_status && (
              <div>
                Последний тест:{" "}
                <span className={`badge ${settings.last_test_status === "ok" ? "ok" : "fail"}`}>
                  {settings.last_test_status}
                </span>{" "}
                {settings.last_test_message}
              </div>
            )}
          </div>
          <div style={{ marginTop: "1rem", fontSize: "0.85rem", color: "var(--muted)" }}>
            Capabilities:{" "}
            {caps
              ? Object.entries(caps)
                  .map(([k, v]) => `${k}:${v.supported ? "yes" : "limited"}`)
                  .join(" · ")
              : "—"}
          </div>
        </div>

        <div className="panel">
          <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Синхронизация</h2>
          <div className="filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="full">full</option>
              <option value="free_only">free_only</option>
              <option value="purchased_only">purchased_only</option>
              <option value="dictionaries_only">dictionaries_only</option>
            </select>
            <label>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
              />{" "}
              dry-run
            </label>
            <button onClick={startSync}>Запустить sync</button>
          </div>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Runexis free_only / purchased_only вернут ошибку capability limited. full для
            Runexis выполнит dictionaries и зафиксирует limitations.
          </p>
        </div>
      </div>
    </>
  );
}
