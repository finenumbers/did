"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { RegionCityItem, RegionsLoadResult } from "@/lib/types/api";

function cellText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export default function RegionsPage() {
  const [items, setItems] = useState<RegionCityItem[]>([]);
  const [savedCapacity, setSavedCapacity] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyRows = useCallback((rows: RegionCityItem[]) => {
    setItems(rows);
    setSavedCapacity(Object.fromEntries(rows.map((row) => [row.id, row.digit_capacity])));
  }, []);

  const loadList = useCallback(
    async ({ asInitial = false } = {}) => {
      if (asInitial) setLoading(true);
      setError(null);
      try {
        const rows = await apiFetch<RegionCityItem[]>("/api/v1/regions");
        applyRows(rows);
      } catch (err: unknown) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить регионы");
      } finally {
        if (asInitial) setLoading(false);
      }
    },
    [applyRows],
  );

  useEffect(() => {
    void loadList({ asInitial: true });
  }, [loadList]);

  const dirtyItems = useMemo(
    () => items.filter((row) => row.digit_capacity !== savedCapacity[row.id]),
    [items, savedCapacity],
  );

  async function loadFromCatalog() {
    if (dirtyItems.length > 0) {
      const ok = window.confirm("Есть несохранённые правки разрядности. Загрузить данные?");
      if (!ok) return;
    }
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

  async function saveCapacities() {
    if (dirtyItems.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch<RegionsLoadResult>("/api/v1/regions/save", {
        method: "POST",
        body: JSON.stringify({
          items: dirtyItems.map((row) => ({ id: row.id, digit_capacity: row.digit_capacity })),
        }),
      });
      await loadList();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить данные");
    } finally {
      setSaving(false);
    }
  }

  function onCapacityChange(id: string, raw: string) {
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 5 || n > 7) return;
    setItems((prev) => prev.map((row) => (row.id === id ? { ...row, digit_capacity: n } : row)));
  }

  const busy = reloading || saving;

  return (
    <div className="numbers-page">
      <div className="panel numbers-panel">
        <div className="regions-toolbar">
          <button type="button" className="secondary" disabled={busy || dirtyItems.length === 0} onClick={() => void saveCapacities()}>
            {saving ? "Сохранение…" : "Сохранить данные"}
          </button>
          <button type="button" disabled={busy} onClick={() => void loadFromCatalog()}>
            {reloading ? "Загрузка…" : "Загрузить данные"}
          </button>
        </div>
        {error && <div className="state error">{error}</div>}
        <div className="table-scroll">
          <table className="regions-table">
            <thead>
              <tr>
                <th>Разрядность</th>
                <th>Город</th>
                <th>Регион</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>
                    <input
                      className="regions-capacity-input"
                      type="number"
                      min={5}
                      max={7}
                      step={1}
                      value={row.digit_capacity}
                      disabled={busy}
                      onChange={(e) => onCapacityChange(row.id, e.target.value)}
                    />
                  </td>
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
