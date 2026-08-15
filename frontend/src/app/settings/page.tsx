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
  | "aurora"
  | "finenumbers"
  | "exolve"
  | "voximplant"
  | "mcn";

type Draft = {
  baseUrl: string;
  apiKey: string;
  email: string;
  password: string;
  numberingLogin: string;
  numberingPassword: string;
  numberingBaseUrl: string;
  accessToken: string;
  credentialsJson: string;
  settings: ProviderSettings | null;
  message: string | null;
  error: string | null;
  saving: boolean;
  testing: boolean;
};

const EMPTY_DRAFT: Draft = {
  baseUrl: "",
  apiKey: "",
  email: "",
  password: "",
  numberingLogin: "",
  numberingPassword: "",
  numberingBaseUrl: "",
  accessToken: "",
  credentialsJson: "",
  settings: null,
  message: null,
  error: null,
  saving: false,
  testing: false,
};

const PROVIDERS: { code: ProviderCode; title: string }[] = [
  { code: "sipout", title: "SipOut" },
  { code: "runexis", title: "Runexis" },
  { code: "uis", title: "UIS" },
  { code: "aurora", title: "Aurora Telecom" },
  { code: "exolve", title: "Exolve" },
  { code: "voximplant", title: "Voximplant" },
  { code: "mcn", title: "MCN Telecom" },
  { code: "finenumbers", title: "Finenumbers" },
];

function draftFromSettings(code: ProviderCode, s: ProviderSettings): Draft {
  const auth = s.auth_settings_masked || {};
  return {
    ...EMPTY_DRAFT,
    baseUrl: s.base_url || "",
    email: typeof auth.email === "string" ? auth.email : "",
    numberingLogin: typeof auth.numbering_login === "string" ? auth.numbering_login : "",
    numberingBaseUrl: typeof auth.numbering_base_url === "string" ? auth.numbering_base_url : "",
    settings: s,
  };
}

export default function SettingsPage() {
  const [drafts, setDrafts] = useState<Record<ProviderCode, Draft>>({
    sipout: { ...EMPTY_DRAFT },
    runexis: { ...EMPTY_DRAFT },
    uis: { ...EMPTY_DRAFT },
    aurora: { ...EMPTY_DRAFT },
    exolve: { ...EMPTY_DRAFT },
    voximplant: { ...EMPTY_DRAFT },
    mcn: { ...EMPTY_DRAFT },
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
      aurora: { ...EMPTY_DRAFT },
      exolve: { ...EMPTY_DRAFT },
      voximplant: { ...EMPTY_DRAFT },
      mcn: { ...EMPTY_DRAFT },
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
    setDraft(code, { saving: true, error: null, message: null });
    let auth_settings: Record<string, string> | undefined;
    if (code === "sipout" || code === "finenumbers") {
      auth_settings = d.apiKey ? { key: d.apiKey } : undefined;
    } else if (code === "exolve" || code === "mcn") {
      auth_settings = d.apiKey ? { api_key: d.apiKey } : undefined;
    } else if (code === "voximplant") {
      auth_settings = d.credentialsJson
        ? { credentials_json: d.credentialsJson }
        : undefined;
    } else if (code === "uis") {
      auth_settings = d.accessToken ? { access_token: d.accessToken } : undefined;
    } else if (code === "aurora") {
      auth_settings = undefined;
    } else {
      const next: Record<string, string> = {};
      if (d.email) next.email = d.email;
      if (d.password) next.password = d.password;
      if (d.numberingLogin) next.numbering_login = d.numberingLogin;
      if (d.numberingPassword) next.numbering_password = d.numberingPassword;
      if (d.numberingBaseUrl) next.numbering_base_url = d.numberingBaseUrl;
      auth_settings = Object.keys(next).length ? next : undefined;
    }
    try {
      const s = await apiFetch<ProviderSettings>(`/api/v1/providers/${code}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          base_url: d.baseUrl || null,
          auth_settings,
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
            Локальный кеш диапазонов используется только для заполнения столбца «Оператор».
            Синхронизация недоступна, пока не загружен минимальный комплект.
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
          const hasToken = Boolean(d.settings?.auth_settings_masked?.token);
          const hasNumberingSession = Boolean(
            d.settings?.auth_settings_masked?.numbering_session_id,
          );
          return (
            <div className="panel" key={code}>
              <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>{title}</h2>
              {d.message && <div className="notice">{d.message}</div>}
              {d.error && <div className="state error">{d.error}</div>}
              <div className="filters" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <label>
                  Base URL{" "}
                  {code === "runexis"
                    ? "(DIDAPI)"
                    : code === "finenumbers"
                      ? "(PSTN)"
                      : code === "uis"
                        ? "(Data API)"
                        : code === "aurora"
                          ? "(CSV directory)"
                          : code === "exolve"
                            ? "(Numbering API)"
                            : code === "voximplant"
                              ? "(Management API)"
                              : code === "mcn"
                                ? "(Витрина)"
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
                            : code === "aurora"
                              ? "http://bill.auroratelecom.ru:8080/bgbilling/numbers/"
                              : code === "exolve"
                                ? "https://api.exolve.ru"
                                : code === "voximplant"
                                  ? "https://api.voximplant.com"
                                  : code === "mcn"
                                    ? "https://shop.mcn.ru"
                                    : undefined
                    }
                  />
                </label>

                {code === "aurora" ? (
                  <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                    Публичные региональные CSV свободных номеров (HTTP): Crimea, Grozny, MSK,
                    Sevastopol, Simferopol, SPb. Файл all_free.csv не используется. Base URL —
                    каталог (или legacy путь к .csv → берётся родительская папка). Auth не
                    требуется. Купленные и справочники не поддерживаются.
                  </div>
                ) : code === "exolve" ? (
                  <>
                    <label>
                      API-ключ
                      <input
                        type="password"
                        placeholder={
                          d.settings?.auth_settings_masked?.api_key
                            ? `текущее: ${String(d.settings.auth_settings_masked.api_key)}`
                            : "API-ключ приложения из ЛК Exolve"
                        }
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      Bearer API-ключ приложения (ЛК Exolve → Приложения → API-ключи). Read-only:
                      GetList (справочник) и GetFree (свободные). Купленные / Lock / Buy не
                      вызываются.
                      {d.settings?.auth_settings_masked?.api_key
                        ? " Ключ сохранён."
                        : " Ключ ещё не задан."}
                    </div>
                  </>
                ) : code === "voximplant" ? (
                  <>
                    <label>
                      Service Account credentials (JSON)
                      <textarea
                        rows={6}
                        placeholder={
                          d.settings?.auth_settings_masked?.private_key
                            ? "credentials сохранены (private_key masked). Вставьте новый JSON, чтобы заменить."
                            : '{"account_id":…,"key_id":"…","private_key":"-----BEGIN PRIVATE KEY-----\\n…"}'
                        }
                        value={d.credentialsJson}
                        onChange={(e) => setDraft(code, { credentialsJson: e.target.value })}
                        style={{ width: "100%", fontFamily: "monospace", fontSize: "0.85rem" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      ЛК Voximplant → Settings → Service accounts → Generate key. Read-only: все
                      свободные RU-номера (Categories → Regions → GetNewPhoneNumbers). Купленные /
                      Attach не вызываются.
                      {d.settings?.auth_settings_masked?.private_key
                        ? " Credentials сохранены."
                        : " Credentials ещё не заданы."}
                    </div>
                  </>
                ) : code === "mcn" ? (
                  <>
                    <label>
                      API-токен (Интеграции)
                      <input
                        type="password"
                        placeholder={
                          d.settings?.auth_settings_masked?.api_key
                            ? `текущее: ${String(d.settings.auth_settings_masked.api_key)}`
                            : "токен из ЛК → Интеграции → Токены"
                        }
                        value={d.apiKey}
                        onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      ЛК MCN → Интеграции → Токены (роль администратора Integrations). Read-only
                      Витрина: countries / regions / cities / numbers (RU). Checkout и NNP не
                      вызываются.
                      {d.settings?.auth_settings_masked?.api_key
                        ? " Токен сохранён."
                        : " Токен ещё не задан."}
                    </div>
                  </>
                ) : code === "sipout" || code === "finenumbers" ? (
                  <label>
                    {code === "finenumbers" ? "API Bearer key" : "API key"}
                    <input
                      type="password"
                      placeholder={
                        d.settings?.auth_settings_masked?.key
                          ? `текущее: ${String(d.settings.auth_settings_masked.key)}`
                          : code === "finenumbers"
                            ? "Bearer token PSTN API"
                            : "ключ SipOut"
                      }
                      value={d.apiKey}
                      onChange={(e) => setDraft(code, { apiKey: e.target.value })}
                      style={{ width: "100%" }}
                    />
                  </label>
                ) : code === "uis" ? (
                  <>
                    <label>
                      Access token
                      <input
                        type="password"
                        placeholder={
                          d.settings?.auth_settings_masked?.access_token
                            ? `текущее: ${String(d.settings.auth_settings_masked.access_token)}`
                            : "API-ключ из ЛК UIS"
                        }
                        value={d.accessToken}
                        onChange={(e) => setDraft(code, { accessToken: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      Auth только через API-ключ (access_token). Read-only: get.available_virtual_numbers /
                      get.virtual_numbers. IP whitelist в ЛК UIS обязателен.
                      {d.settings?.auth_settings_masked?.access_token
                        ? " Access token сохранён."
                        : " Access token ещё не задан."}
                    </div>
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
                        autoComplete="username"
                        placeholder="email для POST api/v1/login"
                        value={d.email}
                        onChange={(e) => setDraft(code, { email: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Пароль
                      <input
                        type="password"
                        autoComplete="current-password"
                        placeholder={
                          d.settings?.auth_settings_masked?.password
                            ? `текущее: ${String(d.settings.auth_settings_masked.password)}`
                            : "пароль DIDAPI"
                        }
                        value={d.password}
                        onChange={(e) => setDraft(code, { password: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      Bearer через login/refresh.
                      {hasToken
                        ? ` Токен сохранён${
                            d.settings?.auth_settings_masked?.token_expire
                              ? `, expire: ${String(d.settings.auth_settings_masked.token_expire)}`
                              : ""
                          }.`
                        : " Токен ещё не получен."}
                    </div>

                    <h3 style={{ margin: "0.75rem 0 0", fontSize: "0.95rem" }}>
                      Numbering API — свободные номера
                    </h3>
                    <label>
                      Numbering Base URL
                      <input
                        value={d.numberingBaseUrl}
                        onChange={(e) => setDraft(code, { numberingBaseUrl: e.target.value })}
                        placeholder="https://did-api.runexis.ru/"
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Numbering login
                      <input
                        value={d.numberingLogin}
                        onChange={(e) => setDraft(code, { numberingLogin: e.target.value })}
                        placeholder="login для JSON-RPC connect"
                        style={{ width: "100%" }}
                      />
                    </label>
                    <label>
                      Numbering password
                      <input
                        type="password"
                        autoComplete="new-password"
                        placeholder={
                          d.settings?.auth_settings_masked?.numbering_password
                            ? `текущее: ${String(d.settings.auth_settings_masked.numbering_password)}`
                            : "пароль Numbering API"
                        }
                        value={d.numberingPassword}
                        onChange={(e) => setDraft(code, { numberingPassword: e.target.value })}
                        style={{ width: "100%" }}
                      />
                    </label>
                    <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                      Отдельные credentials. Только чтение: connect + search_numbers.
                      {hasNumberingSession
                        ? " Session id сохранён."
                        : " Session ещё не получен — Test connection."}
                    </div>
                  </>
                )}

                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button onClick={() => void save(code)} disabled={d.saving}>
                    {d.saving ? "Сохранение…" : "Сохранить"}
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void test(code)}
                    disabled={d.testing}
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
