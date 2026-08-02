"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { NumberItem, Page } from "@/lib/types/api";
import { CertaintyCell, CertaintyLegend } from "@/components/numbers/CertaintyCell";

export function NumbersTable({ kind }: { kind: "free" | "purchased" }) {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [provider, setProvider] = useState("");
  const [data, setData] = useState<Page<NumberItem> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: "50",
      sort_by: "last_seen_at",
      sort_dir: "desc",
    });
    if (q) params.set("q", q);
    if (provider) params.append("provider", provider);
    setLoading(true);
    setError(null);
    apiFetch<Page<NumberItem>>(`/api/v1/numbers/${kind}?${params}`)
      .then(setData)
      .catch((e) => setError(e.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [kind, page, q, provider]);

  return (
    <div className="panel">
      <div className="filters">
        <input
          placeholder="Поиск номера"
          value={q}
          onChange={(e) => {
            setPage(1);
            setQ(e.target.value);
          }}
        />
        <select
          value={provider}
          onChange={(e) => {
            setPage(1);
            setProvider(e.target.value);
          }}
        >
          <option value="">Все провайдеры</option>
          <option value="sipout">sipout</option>
          <option value="runexis">runexis</option>
        </select>
      </div>

      {loading && <div className="state">Загрузка…</div>}
      {error && <div className="state error">{error}</div>}
      {!loading && !error && data && data.items.length === 0 && (
        <div className="state">
          Нет данных. Запустите sync в Настройках.
          {kind === "free" || kind === "purchased"
            ? " Для Runexis free/purchased sync ограничен документацией."
            : ""}
        </div>
      )}

      {!loading && data && data.items.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>Провайдер</th>
                <th>Номер</th>
                <th>Статус</th>
                <th>Регион</th>
                <th>Город</th>
                {kind === "free" ? <th>Цена</th> : <th>Тариф</th>}
                <th>SMS</th>
                <th>Обновлено</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => {
                const fv = row.field_verification || {};
                return (
                  <tr key={row.id}>
                    <td>{row.provider_code}</td>
                    <td>
                      <CertaintyCell value={row.msisdn || row.provider_number_key} verification={fv.msisdn} />
                    </td>
                    <td>
                      <CertaintyCell value={row.status_raw} verification={fv.status_raw} />
                    </td>
                    <td>
                      <CertaintyCell value={row.region_name} verification={fv.region_name} />
                    </td>
                    <td>
                      <CertaintyCell value={row.city_name} verification={fv.city_name} />
                    </td>
                    <td>
                      {kind === "free" ? (
                        <CertaintyCell value={row.price_amount} verification={fv.price_amount} />
                      ) : (
                        <CertaintyCell value={row.tariff_name} verification={fv.tariff_name || "unresolved"} />
                      )}
                    </td>
                    <td>
                      <CertaintyCell value={row.has_sms} verification={fv.has_sms} />
                    </td>
                    <td>{new Date(row.last_seen_at).toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="pagination">
            <button className="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Назад
            </button>
            <span>
              стр. {data.page} / {data.total_pages} · всего {data.total}
            </span>
            <button
              className="secondary"
              disabled={page >= data.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Вперёд
            </button>
          </div>
          <CertaintyLegend />
        </>
      )}
    </div>
  );
}
