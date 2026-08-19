"use client";

import { useCallback, useEffect, useState } from "react";
import { DirectoryExplorer } from "@/components/directory/DirectoryExplorer";
import { ApiError, apiDownload, apiFetch, apiUpload } from "@/lib/api/client";
import type { DirectoryColumn } from "@/lib/directory/filters";
import type { RegionCityItem, RegionsLoadResult } from "@/lib/types/api";

function cellText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

const COLUMNS: DirectoryColumn<RegionCityItem>[] = [
  {
    key: "abc",
    header: "ABC",
    text: (r) => r.abc,
    facet: (r) => r.abc,
  },
  {
    key: "digit_capacity",
    header: "Разрядность",
    text: (r) => String(r.digit_capacity),
    facet: (r) => String(r.digit_capacity),
  },
  {
    key: "city_name",
    header: "Город",
    text: (r) => r.city_name,
    facet: (r) => r.city_name,
    highlight: true,
  },
  {
    key: "region_name",
    header: "Регион",
    text: (r) => cellText(r.region_name),
    facet: (r) => r.region_name || "",
  },
];

function citySearch(row: RegionCityItem): string {
  return row.city_name;
}

export default function RegionsPage() {
  const [items, setItems] = useState<RegionCityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
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

  async function exportXlsx() {
    setExporting(true);
    setError(null);
    try {
      const blob = await apiDownload("/api/v1/regions/export.xlsx");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "regions.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось скачать XLSX");
    } finally {
      setExporting(false);
    }
  }

  async function importXlsx(file: File) {
    const ok = window.confirm("Заменить все данные в Регионах?");
    if (!ok) return;
    setImporting(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      await apiUpload<RegionsLoadResult>("/api/v1/regions/import.xlsx", body);
      await loadList();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось импортировать XLSX");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="numbers-page">
      <div className="panel numbers-panel">
        <DirectoryExplorer
          items={items}
          columns={COLUMNS}
          searchPlaceholder="Город"
          searchChipLabel="Город"
          searchValue={citySearch}
          tableClassName="regions-table"
          loading={loading}
          error={error}
          exporting={exporting}
          importing={importing}
          emptyText="Нет данных. Нажмите «Импорт XLSX»."
          onExport={() => void exportXlsx()}
          onImport={(file) => void importXlsx(file)}
        />
      </div>
    </div>
  );
}
