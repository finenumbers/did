"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { RegionCityItem, RegionsLoadResult } from "@/lib/types/api";

function cellText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export default function RegionsPage() {
  const [items, setItems] = useState<RegionCityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async ({ asInitial = false } = {}) => {
    if (asInitial) setLoading(true);
    setError(null);
    try {
      const rows = await apiFetch<RegionCityItem[]>("/api/v1/regions");
      setItems(rows);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить регионы");
    } finally {
      if (asInitial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList({ asInitial: true });
  }, [loadList]);

  async function loadFromCatalog() {
    setReloading(true);
    setError(null);
    try {
      await apiFetch<RegionsLoadResult>("/api/v1/regions/load", { method: "POST" });
      await loadList();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные");
    } finally {
      setReloading(false);
    }
  }

  return (
    <div className="numbers-page">
      <div className="panel numbers-panel">
        <div className="regions-toolbar">
          <button type="button" disabled={reloading} onClick={() => void loadFromCatalog()}>
            {reloading ? "Загрузка…" : "Загрузить данные"}
          </button>
        </div>
        {error && <div className="state error">{error}</div>}
        <div className="table-scroll">
          <table className="regions-table">
            <thead>
              <tr>
                <th>Разрядность номера</th>
                <th>Город</th>
                <th>Регион</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row, idx) => (
                <tr key={`${row.city_name}|${row.region_name ?? ""}|${idx}`}>
                  <td>{cellText(row.digit_capacity)}</td>
                  <td>{row.city_name}</td>
                  <td>{cellText(row.region_name)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && items.length === 0 && <div className="state">Загрузка…</div>}
          {!loading && !reloading && !error && items.length === 0 && (
            <div className="state">Нет данных. Нажмите «Загрузить данные».</div>
          )}
        </div>
      </div>
    </div>
  );
}
