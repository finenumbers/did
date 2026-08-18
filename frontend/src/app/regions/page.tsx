"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { RegionCityItem } from "@/lib/types/api";

function cellText(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return value;
}

export default function RegionsPage() {
  const [items, setItems] = useState<RegionCityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void apiFetch<RegionCityItem[]>("/api/v1/regions")
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить регионы");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="numbers-page">
      <div className="panel numbers-panel">
        {error && <div className="state error">{error}</div>}
        <div className="table-scroll">
          <table className="regions-table">
            <thead>
              <tr>
                <th>ABC</th>
                <th>Город</th>
                <th>Регион</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row, idx) => (
                <tr key={`${row.city_name}|${row.region_name ?? ""}|${idx}`}>
                  <td>{cellText(row.abc)}</td>
                  <td>{row.city_name}</td>
                  <td>{cellText(row.region_name)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && items.length === 0 && <div className="state">Загрузка…</div>}
          {!loading && !error && items.length === 0 && (
            <div className="state">
              Нет данных. Запустите синхронизацию на странице «Синхронизация».
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
