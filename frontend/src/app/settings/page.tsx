"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import { formatCount } from "@/lib/format";
import type {
  ProviderSettings,
  PstnInnCacheStatus,
  SyncSchedule,
} from "@/lib/types/api";

type ProviderCode =
  | "sipout"
  | "runexis"
  | "uis"
  | "novofon"
  | "aurora"
  | "finenumbers"
  | "exolve"
  | "voximplant"
  | "mcn"
  | "didww"
  | "twilio";

type AuroraCsvFile = { url: string; has_status_column: boolean };

type FieldSnapshot = {
  baseUrl: string;
  apiKey: string;
  regApiKey: string;
  regBaseUrl: string;
  email: string;
  password: string;
  numberingLogin: string;
  numberingPassword: string;
  numberingBaseUrl: string;
  accessToken: string;
  userId: string;
  userApiSecret: string;
  credentialsJson: string;
  accountSid: string;
  authToken: string;
};

type Draft = FieldSnapshot & {
  csvFiles: AuroraCsvFile[];
  settings: ProviderSettings | null;
  message: string | null;
  error: string | null;
  saving: boolean;
  testing: boolean;
  secretsWritable: boolean;
  baseline: FieldSnapshot;
};

const EMPTY_FIELDS: FieldSnapshot = {
  baseUrl: "",
  apiKey: "",
  regApiKey: "",
  regBaseUrl: "",
  email: "",
  password: "",
  numberingLogin: "",
  numberingPassword: "",
  numberingBaseUrl: "",
  accessToken: "",
  userId: "",
  userApiSecret: "",
  credentialsJson: "",
  accountSid: "",
  authToken: "",
};

const EMPTY_DRAFT: Draft = {
  ...EMPTY_FIELDS,
  csvFiles: [],
  settings: null,
  message: null,
  error: null,
  saving: false,
  testing: false,
  secretsWritable: false,
  baseline: { ...EMPTY_FIELDS },
};

const PROVIDERS: { code: ProviderCode; title: string }[] = [
  { code: "sipout", title: "SipOut" },
  { code: "runexis", title: "Runexis" },
  { code: "uis", title: "UIS" },
  { code: "novofon", title: "Novofon" },
  { code: "aurora", title: "Aurora Telecom" },
  { code: "exolve", title: "Exolve" },
  { code: "voximplant", title: "Voximplant" },
  { code: "mcn", title: "MCN Telecom" },
  { code: "didww", title: "DIDWW" },
  { code: "twilio", title: "Twilio" },
  { code: "finenumbers", title: "Finenumbers" },
];

function parseAuroraCsvFiles(extra: Record<string, unknown> | undefined): AuroraCsvFile[] {
  const raw = extra?.csv_files;
  if (!Array.isArray(raw)) return [];
  const out: AuroraCsvFile[] = [];
  for (const item of raw) {
    if (typeof item === "string") {
      out.push({ url: item, has_status_column: false });
      continue;
    }
    if (item && typeof item === "object") {
      const row = item as Record<string, unknown>;
      const url = typeof row.url === "string" ? row.url : "";
      if (!url) continue;
      out.push({ url, has_status_column: Boolean(row.has_status_column) });
    }
  }
  return out;
}

function textOf(value: unknown): string {
  if (value === undefined || value === null) return "";
  return String(value);
}

function voxCredentialsJson(auth: Record<string, unknown>): string {
  const accountId = auth.account_id;
  const keyId = auth.key_id;
  const privateKey = auth.private_key;
  const empty =
    (accountId === undefined || accountId === null || accountId === "") &&
    (keyId === undefined || keyId === null || keyId === "") &&
    (privateKey === undefined || privateKey === null || privateKey === "");
  if (empty) return "";
  return JSON.stringify(
    { account_id: accountId, key_id: keyId, private_key: privateKey },
    null,
    2,
  );
}

function fieldsFromSettings(code: ProviderCode, s: ProviderSettings): {
  fields: FieldSnapshot;
  secretsWritable: boolean;
} {
  const open = s.auth_settings;
  const secretsWritable = open !== undefined && open !== null && typeof open === "object";
  const auth = secretsWritable ? open : {};
  const extra = s.extra_settings || {};
  const apiKey =
    code === "sipout" || code === "finenumbers" ? textOf(auth.key) : textOf(auth.api_key);
  return {
    secretsWritable,
    fields: {
      baseUrl: s.base_url || "",
      apiKey,
      regApiKey: textOf(auth.reg_key),
      regBaseUrl: typeof extra.reg_base_url === "string" ? extra.reg_base_url : "",
      email: textOf(auth.email),
      password: textOf(auth.password),
      numberingLogin: textOf(auth.numbering_login),
      numberingPassword: textOf(auth.numbering_password),
      numberingBaseUrl: textOf(auth.numbering_base_url),
      accessToken: textOf(auth.access_token),
      userId: textOf(auth.user_id),
      userApiSecret: textOf(auth.api_secret),
      credentialsJson: code === "voximplant" ? voxCredentialsJson(auth) : "",
      accountSid: textOf(auth.account_sid),
      authToken: textOf(auth.auth_token),
    },
  };
}

function draftFromSettings(code: ProviderCode, s: ProviderSettings): Draft {
  const { fields, secretsWritable } = fieldsFromSettings(code, s);
  return {
    ...EMPTY_DRAFT,
    ...fields,
    secretsWritable,
    baseline: { ...fields },
    csvFiles: code === "aurora" ? parseAuroraCsvFiles(s.extra_settings) : [],
    settings: s,
  };
}

function putChanged(
  target: Record<string, string>,
  key: string,
  value: string,
  loaded: string,
) {
  if (value === loaded) return;
  if (value.trim() === "" && loaded.trim() === "") return;
  target[key] = value.trim() === "" ? "" : value;
}

export default function SettingsPage() {
  const [drafts, setDrafts] = useState<Record<ProviderCode, Draft>>({
    sipout: { ...EMPTY_DRAFT },
    runexis: { ...EMPTY_DRAFT },
    uis: { ...EMPTY_DRAFT },
    novofon: { ...EMPTY_DRAFT },
    aurora: { ...EMPTY_DRAFT },
    exolve: { ...EMPTY_DRAFT },
    voximplant: { ...EMPTY_DRAFT },
    mcn: { ...EMPTY_DRAFT },
    didww: { ...EMPTY_DRAFT },
    twilio: { ...EMPTY_DRAFT },
    finenumbers: { ...EMPTY_DRAFT },
  });
  const [pageError, setPageError] = useState<string | null>(null);
  const [cache, setCache] = useState<PstnInnCacheStatus | null>(null);
  const [cacheMsg, setCacheMsg] = useState<string | null>(null);
  const [cacheErr, setCacheErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [newName, setNewName] = useState("");
  const [newInn, setNewInn] = useState("");
  const [schedule, setSchedule] = useState<SyncSchedule | null>(null);
  const [scheduleSaving, setScheduleSaving] = useState(false);

  const setDraft = (code: ProviderCode, patch: Partial<Draft>) => {
    setDrafts((prev) => ({ ...prev, [code]: { ...prev[code], ...patch } }));
  };

  const loadCache = useCallback(async () => {
    const status = await apiFetch<PstnInnCacheStatus>("/api/v1/settings/pstn-inn-cache");
    setCache(status);
    const st = status.refresh?.status;
    if (st === "success") {
      setCacheMsg("Кеш операторов загружен");
    } else if (st === "failed") {
      setCacheMsg(null);
      setCacheErr(status.refresh?.error || status.refresh?.detail || "Ошибка загрузки кеша");
    } else if (st === "pending" || st === "running") {
      setCacheMsg(status.refresh?.detail || "Загрузка кеша…");
    }
    return status;
  }, []);

  const loadSchedule = useCallback(async () => {
    const s = await apiFetch<SyncSchedule>("/api/v1/settings/sync-schedule");
    setSchedule(s);
    return s;
  }, []);

  const reloadAll = async () => {
    const next: Record<ProviderCode, Draft> = {
      sipout: { ...EMPTY_DRAFT },
      runexis: { ...EMPTY_DRAFT },
      uis: { ...EMPTY_DRAFT },
      novofon: { ...EMPTY_DRAFT },
      aurora: { ...EMPTY_DRAFT },
      exolve: { ...EMPTY_DRAFT },
      voximplant: { ...EMPTY_DRAFT },
      mcn: { ...EMPTY_DRAFT },
      didww: { ...EMPTY_DRAFT },
      twilio: { ...EMPTY_DRAFT },
      finenumbers: { ...EMPTY_DRAFT },
    };
    for (const { code } of PROVIDERS) {
      const s = await apiFetch<ProviderSettings>(`/api/v1/providers/${code}/settings`);
      next[code] = draftFromSettings(code, s);
    }
    setDrafts(next);
    await loadCache();
    await loadSchedule();
  };

  useEffect(() => {
    reloadAll().catch((e) => setPageError(e instanceof Error ? e.message : "Ошибка загрузки"));
  }, []);

  const refreshActive =
    cache?.refresh?.status === "pending" || cache?.refresh?.status === "running";

  useEffect(() => {
    if (!refreshActive) return;
    const t = setInterval(() => {
      void loadCache().catch(() => undefined);
    }, 2000);
    return () => clearInterval(t);
  }, [refreshActive, loadCache]);

  const save = async (code: ProviderCode) => {
    const d = drafts[code];
    if (!d.settings) return;
    setDraft(code, { saving: true, error: null, message: null });
    let auth_settings: Record<string, string> | undefined;
    let extra_settings: Record<string, unknown> | undefined;
    if (code === "aurora") {
      const csv_files = d.csvFiles
        .map((f) => ({
          url: f.url.trim(),
          has_status_column: f.has_status_column,
        }))
        .filter((f) => f.url.length > 0);
      if (csv_files.length === 0) {
        setDraft(code, {
          saving: false,
          error: "Добавьте хотя бы один URL CSV-файла",
          message: null,
        });
        return;
      }
      extra_settings = { csv_files };
    } else if (d.secretsWritable) {
      const next: Record<string, string> = {};
      const b = d.baseline;
      if (code === "finenumbers") {
        putChanged(next, "key", d.apiKey, b.apiKey);
        putChanged(next, "reg_key", d.regApiKey, b.regApiKey);
      } else if (code === "sipout") {
        putChanged(next, "key", d.apiKey, b.apiKey);
      } else if (code === "exolve" || code === "mcn" || code === "didww") {
        putChanged(next, "api_key", d.apiKey, b.apiKey);
      } else if (code === "twilio") {
        putChanged(next, "account_sid", d.accountSid, b.accountSid);
        putChanged(next, "auth_token", d.authToken, b.authToken);
      } else if (code === "voximplant") {
        putChanged(next, "credentials_json", d.credentialsJson, b.credentialsJson);
      } else if (code === "uis") {
        putChanged(next, "access_token", d.accessToken, b.accessToken);
      } else if (code === "novofon") {
        putChanged(next, "user_id", d.userId, b.userId);
        putChanged(next, "access_token", d.accessToken, b.accessToken);
        putChanged(next, "api_key", d.apiKey, b.apiKey);
        putChanged(next, "api_secret", d.userApiSecret, b.userApiSecret);
      } else {
        putChanged(next, "email", d.email, b.email);
        putChanged(next, "password", d.password, b.password);
        putChanged(next, "numbering_login", d.numberingLogin, b.numberingLogin);
        putChanged(next, "numbering_password", d.numberingPassword, b.numberingPassword);
        putChanged(next, "numbering_base_url", d.numberingBaseUrl, b.numberingBaseUrl);
      }
      auth_settings = Object.keys(next).length ? next : undefined;
    }
    if (code === "finenumbers" && d.regBaseUrl !== d.baseline.regBaseUrl) {
      extra_settings = {
        reg_base_url: d.regBaseUrl.trim() === "" ? "" : d.regBaseUrl,
      };
    }
    try {
      const s = await apiFetch<ProviderSettings>(`/api/v1/providers/${code}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          base_url: code === "aurora" ? null : d.baseUrl || null,
          auth_settings,
          extra_settings,
        }),
      });
      setDraft(code, {
        ...draftFromSettings(code, s),
        message: "Настройки сохранены",
        saving: false,
      });
    } catch (e) {
      setDraft(code, {
        saving: false,
        error: e instanceof Error ? e.message : "Ошибка сохранения",
      });
    }
  };

  const test = async (code: ProviderCode) => {
    setDraft(code, { testing: true, error: null, message: null });
    try {
      const r = await apiFetch<{ ok: boolean; message: string }>(
        `/api/v1/providers/${code}/test-connection`,
        { method: "POST" },
      );
      const s = await apiFetch<ProviderSettings>(`/api/v1/providers/${code}/settings`);
      setDraft(code, {
        ...draftFromSettings(code, s),
        message: r.ok ? `OK: ${r.message}` : `FAIL: ${r.message}`,
        testing: false,
      });
    } catch (e) {
      setDraft(code, {
        testing: false,
        error: e instanceof Error ? e.message : "Ошибка теста",
      });
    }
  };

  const startCacheRefresh = async () => {
    setRefreshing(true);
    setCacheErr(null);
    setCacheMsg(null);
    try {
      const status = await apiFetch<PstnInnCacheStatus>("/api/v1/settings/pstn-inn-cache/refresh", {
        method: "POST",
      });
      setCache(status);
      setCacheMsg("Загрузка кеша запущена…");
    } catch (e) {
      setCacheErr(e instanceof Error ? e.message : "Не удалось запустить загрузку кеша");
    } finally {
      setRefreshing(false);
    }
  };

  const addOperator = async () => {
    setCacheErr(null);
    setCacheMsg(null);
    try {
      await apiFetch("/api/v1/settings/pstn-inn-cache/operators", {
        method: "POST",
        body: JSON.stringify({ name: newName, inn: newInn, enabled: true }),
      });
      setNewName("");
      setNewInn("");
      await loadCache();
      setCacheMsg("Оператор добавлен");
    } catch (e) {
      setCacheErr(e instanceof Error ? e.message : "Ошибка добавления");
    }
  };

  const toggleOperator = async (inn: string, enabled: boolean, required: boolean) => {
    if (required) return;
    setCacheErr(null);
    try {
      await apiFetch(`/api/v1/settings/pstn-inn-cache/operators/${inn}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
      await loadCache();
    } catch (e) {
      setCacheErr(e instanceof Error ? e.message : "Ошибка обновления");
    }
  };

  const removeOperator = async (inn: string) => {
    setCacheErr(null);
    try {
      await apiFetch(`/api/v1/settings/pstn-inn-cache/operators/${inn}`, { method: "DELETE" });
      await loadCache();
    } catch (e) {
      setCacheErr(e instanceof Error ? e.message : "Ошибка удаления");
    }
  };

  const saveSchedule = async (enabled: boolean) => {
    setScheduleSaving(true);
    setCacheErr(null);
    try {
      const s = await apiFetch<SyncSchedule>("/api/v1/settings/sync-schedule", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      setSchedule(s);
    } catch (e) {
      setCacheErr(e instanceof Error ? e.message : "Ошибка сохранения расписания");
    } finally {
      setScheduleSaving(false);
    }
  };

  return (
    <>
      {pageError && <div className="state error">{pageError}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="panel">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Кеш операторов (PSTN)</h2>
          <p style={{ color: "var(--muted)", marginTop: 0, fontSize: "0.9rem" }}>
            Локальный кеш диапазонов заполняет столбцы «Оператор», «Город» и «Регион».
            Синхронизация недоступна, пока не загружен минимальный комплект с территорией ГАР.
          </p>
          {cacheMsg && <div className="notice">{cacheMsg}</div>}
          {cacheErr && <div className="state error">{cacheErr}</div>}
          {cache && (
            <>
              <div style={{ marginBottom: "0.75rem" }}>
                Минимальный кеш:{" "}
                <span className={`badge ${cache.min_cache_ready ? "ok" : "fail"}`}>
                  {cache.min_cache_ready ? "готов" : "не готов"}
                </span>
                {!cache.min_cache_ready && cache.missing_required.length > 0 && (
                  <span style={{ color: "var(--muted)", fontSize: "0.85rem", marginLeft: 8 }}>
                    не хватает: {cache.missing_required.join(", ")}
                  </span>
                )}
                {!cache.min_cache_ready && cache.gar_territory_missing && (
                  <span style={{ color: "var(--muted)", fontSize: "0.85rem", marginLeft: 8 }}>
                    нет территории ГАР — нажмите «Загрузить кеш»
                  </span>
                )}
              </div>
              {(cache.refresh?.status === "pending" || cache.refresh?.status === "running") && (
                <div className="notice" style={{ marginBottom: "0.75rem" }}>
                  {cache.refresh.detail || "Загрузка кеша…"}
                </div>
              )}
              {cache.refresh?.status === "failed" && cache.refresh?.error && (
                <div className="state error" style={{ marginBottom: "0.75rem" }}>
                  {cache.refresh.error}
                </div>
              )}
              <table>
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>ИНН</th>
                    <th>Вкл</th>
                    <th>Диапазонов</th>
                    <th>Номеров</th>
                    <th>Обновлён</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {cache.operators.map((op) => (
                    <tr key={op.inn}>
                      <td>
                        {op.name}
                        {op.required ? (
                          <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}> · обяз.</span>
                        ) : null}
                        {op.last_error ? (
                          <div style={{ color: "var(--danger, #b00)", fontSize: "0.8rem" }}>
                            {op.last_error}
                          </div>
                        ) : null}
                      </td>
                      <td>{op.inn}</td>
                      <td>
                        <input
                          type="checkbox"
                          checked={op.enabled}
                          disabled={op.required}
                          onChange={(e) => void toggleOperator(op.inn, e.target.checked, op.required)}
                        />
                      </td>
                      <td>{formatCount(op.ranges_count)}</td>
                      <td>{formatCount(op.numbers_count ?? 0)}</td>
                      <td style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                        {op.last_synced_at
                          ? new Date(op.last_synced_at).toLocaleString()
                          : "—"}
                      </td>
                      <td>
                        {!op.required && (
                          <button className="secondary" onClick={() => void removeOperator(op.inn)}>
                            Удалить
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div
                className="filters"
                style={{ marginTop: "0.75rem", alignItems: "flex-end", flexWrap: "wrap" }}
              >
                <label>
                  Название
                  <input value={newName} onChange={(e) => setNewName(e.target.value)} />
                </label>
                <label>
                  ИНН
                  <input value={newInn} onChange={(e) => setNewInn(e.target.value)} />
                </label>
                <button
                  className="secondary"
                  onClick={() => void addOperator()}
                  disabled={!newName.trim() || !newInn.trim()}
                >
                  Добавить
                </button>
                <button
                  onClick={() => void startCacheRefresh()}
                  disabled={refreshing || refreshActive}
                >
                  {refreshing || refreshActive ? "Загрузка кеша…" : "Загрузить кеш"}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Расписание синхронизации</h2>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={Boolean(schedule?.enabled)}
              disabled={!schedule || scheduleSaving}
              onChange={(e) => void saveSchedule(e.target.checked)}
            />
            Ежедневно не раньше 00:00 (Europe/Moscow): первый запуск в тот же день после
            этого времени (догон, если backend был выключен). Повтор в тот же день не
            делается. Нужен готовый кеш операторов.
          </label>
        </div>

        {PROVIDERS.map(({ code, title }) => {
          const d = drafts[code];
          return (
            <div className="panel" key={code}>
              <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>{title}</h2>
              {d.message && <div className="notice">{d.message}</div>}
              {d.error && <div className="state error">{d.error}</div>}
              <div className="filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
                {code !== "aurora" ? (
                  <label>
                    Base URL{" "}
                    {code === "runexis"
                      ? "(DIDAPI)"
                      : code === "finenumbers"
                        ? "(PSTN)"
                        : code === "uis" || code === "novofon"
                          ? "(Data API)"
                          : code === "exolve"
                            ? "(Numbering API)"
                            : code === "voximplant"
                              ? "(Management API)"
                              : code === "mcn"
                                ? "(Витрина)"
                                : code === "didww"
                                  ? "(API v3)"
                                  : code === "twilio"
                                    ? "(2010-04-01)"
                                    : ""}
                    <input
                      value={d.baseUrl}
                      onChange={(e) => setDraft(code, { baseUrl: e.target.value })}
                      style={{ width: "100%" }}
                      placeholder={
                        code === "runexis"
                          ? "https://didapi.runexis.ru"
                          : code === "finenumbers"
                            ? "https://pstn.finenumbers.com"
                            : code === "uis"
                              ? "https://dataapi.uiscom.ru/v2.0"
                              : code === "novofon"
                                ? "https://dataapi-jsonrpc.novofon.ru/v2.0"
                                : code === "exolve"
                                ? "https://api.exolve.ru"
                                : code === "voximplant"
                                  ? "https://api.voximplant.com"
                                  : code === "mcn"
                                    ? "https://shop.mcn.ru"
                                    : code === "didww"
                                      ? "https://api.didww.com/v3"
                                      : code === "twilio"
                                        ? "https://api.twilio.com/2010-04-01"
                                        : undefined
                      }
                    />
                  </label>
                ) : null}

                {code === "aurora" ? (
                  <>
                    {d.csvFiles.map((file, idx) => (
                      <div
                        key={`aurora-csv-${idx}`}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.35rem",
                          padding: "0.5rem 0",
                          borderBottom: "1px solid var(--line)",
                        }}
                      >
                        <label>
                          URL файла
                          <input
                            value={file.url}
                            onChange={(e) => {
                              const next = d.csvFiles.map((row, i) =>
                                i === idx ? { ...row, url: e.target.value } : row,
                              );
                              setDraft(code, { csvFiles: next });
                            }}
                            style={{ width: "100%" }}
                            placeholder="http://bill.auroratelecom.ru:8080/bgbilling/numbers/Crimea.csv"
                          />
                        </label>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "0.75rem",
                          }}
                        >
                          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            <input
                              type="checkbox"
                              checked={file.has_status_column}
                              onChange={(e) => {
                                const next = d.csvFiles.map((row, i) =>
                                  i === idx
                                    ? { ...row, has_status_column: e.target.checked }
                                    : row,
                                );
                                setDraft(code, { csvFiles: next });
                              }}
                            />
                            6 столбцов (статус)
                          </label>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              setDraft(code, {
                                csvFiles: d.csvFiles.filter((_, i) => i !== idx),
                              });
                            }}
                          >
                            Удалить
                          </button>
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        setDraft(code, {
                          csvFiles: [
                            ...d.csvFiles,
                            { url: "", has_status_column: false },
                          ],
                        })
                      }
                    >
                      Добавить файл
                    </button>
                  </>
                ) : code === "exolve" ? (
                  <>
                    <label>
                      API-ключ
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="API-ключ приложения из ЛК Exolve"
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "voximplant" ? (
                  <>
                    <label>
                      Service Account credentials (JSON)
                      <textarea
                        rows={6}
                        autoComplete="off"
                        spellCheck={false}
                        placeholder='{"account_id":…,"key_id":"…","private_key":"-----BEGIN PRIVATE KEY-----\\n…"}'
                        value={d.credentialsJson}
                        onChange={(e) => setDraft(code, { credentialsJson: e.target.value })}
                        style={{ width: "100%", fontFamily: "monospace", fontSize: "0.85rem" }}
                      />
                    </label>
                  </>
                ) : code === "didww" ? (
                  <>
                    <label>
                      API-ключ (Api-Key)
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="API-ключ из панели DIDWW"
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "twilio" ? (
                  <>
                    <label>
                      Account SID
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        value={d.accountSid}
                        onChange={(e) => setDraft(code, { accountSid: e.target.value })}
                        style={{ width: "100%" }}
                        placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                      />
                    </label>
                    <label>
                      Auth Token
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Auth Token из консоли Twilio"
                        value={d.authToken}
                        onChange={(e) => setDraft(code, { authToken: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "mcn" ? (
                  <>
                    <label>
                      API-токен (Интеграции)
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="токен из ЛК → Интеграции → Токены"
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "sipout" ? (
                  <label>
                    API key
                    <input
                      type="text"
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="ключ SipOut"
                      value={d.apiKey}
                      onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                      style={{ width: "100%" }}
                    />
                  </label>
                ) : code === "finenumbers" ? (
                  <>
                    <label>
                      PSTN API Bearer key
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Bearer token PSTN API (pstn.finenumbers.com)"
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      REG API key
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="reg_… (reg.finenumbers.com, phones:read)"
                        value={d.regApiKey}
                        onChange={(e) => setDraft(code, { regApiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      REG base URL
                      <input
                        type="url"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="https://reg.finenumbers.com"
                        value={d.regBaseUrl}
                        onChange={(e) => setDraft(code, { regBaseUrl: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "uis" ? (
                  <>
                    <label>
                      Access token
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="API-ключ из ЛК UIS"
                        value={d.accessToken}
                        onChange={(e) => setDraft(code, { accessToken: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : code === "novofon" ? (
                  <>
                    <label>
                      Access token
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Единственный ключ с экрана API. Он же access_token Data API"
                        value={d.accessToken}
                        onChange={(e) => setDraft(code, { accessToken: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Key
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Необязательно. В кабинете Новофон 2.0 этого поля нет"
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Secret User API
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Необязательно. Только если в старом кабинете Secret другой"
                        value={d.userApiSecret}
                        onChange={(e) => setDraft(code, { userApiSecret: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      User ID
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        inputMode="numeric"
                        placeholder="Пусто для клиента. Для агента — id из get.customer_users, не app_id"
                        value={d.userId}
                        onChange={(e) => setDraft(code, { userId: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                ) : (
                  <>
                    <h3 style={{ margin: "0.5rem 0 0", fontSize: "0.95rem" }}>
                      DIDAPI — купленные номера
                    </h3>
                    <label>
                      Email
                      <input
                        type="email"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="email для POST api/v1/login"
                        value={d.email}
                        onChange={(e) => setDraft(code, { email: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Пароль
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="пароль DIDAPI"
                        value={d.password}
                        onChange={(e) => setDraft(code, { password: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>

                    <h3 style={{ margin: "0.75rem 0 0", fontSize: "0.95rem" }}>
                      Numbering API — свободные номера
                    </h3>
                    <label>
                      Numbering Base URL
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        value={d.numberingBaseUrl}
                        onChange={(e) => setDraft(code, { numberingBaseUrl: e.target.value })}
                        placeholder="https://did-api.runexis.ru/"
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Numbering login
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        value={d.numberingLogin}
                        onChange={(e) => setDraft(code, { numberingLogin: e.target.value })}
                        placeholder="login для JSON-RPC connect"
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Numbering password
                      <input
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="пароль Numbering API"
                        value={d.numberingPassword}
                        onChange={(e) => setDraft(code, { numberingPassword: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                  </>
                )}

                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button onClick={() => void save(code)} disabled={d.saving || !d.settings}>
                    {d.saving ? "Сохранение…" : "Сохранить"}
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void test(code)}
                    disabled={d.testing || !d.settings}
                  >
                    {d.testing ? "Проверка…" : "Test connection"}
                  </button>
                </div>

                {d.settings?.last_test_status && (
                  <div>
                    Последний тест:{" "}
                    <span
                      className={`badge ${d.settings.last_test_status === "ok" ? "ok" : "fail"}`}
                    >
                      {d.settings.last_test_status}
                    </span>{" "}
                    {d.settings.last_test_message}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
