"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiDownload, apiFetch, apiUpload } from "@/lib/api/client";
import { formatPrice } from "@/lib/format";
import type { MaskTypeItem, MaskTypesLoadResult } from "@/lib/types/api";

function cellText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function priceText(value: string | number | null | undefined): string {
  return formatPrice(value) ?? "—";
}

export default function MasksPage() {
  const [items, setItems] = useState<MaskTypeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadList = useCallback(async ({ asInitial = false } = {}) => {
    if (asInitial) setLoading(true);
    setError(null);
    try {
      const rows = await apiFetch<MaskTypeItem[]>("/api/v1/mask-types");
      setItems(rows);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить маски и типы");
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
      const blob = await apiDownload("/api/v1/mask-types/export.xlsx");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "masks.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось скачать XLSX");
    } finally {
      setExporting(false);
    }
  }

  async function importXlsx(file: File) {
    const ok = window.confirm(
      "Обновить справочник из файла? Новые комбинации добавятся, строки не удаляются.",
    );
    if (!ok) return;
    setImporting(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      await apiUpload<MaskTypesLoadResult>("/api/v1/mask-types/import.xlsx", body);
      await loadList();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не удалось импортировать XLSX");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const busy = exporting || importing;

  return (
    <div className="numbers-page">
      <div className="panel numbers-panel">
        <div className="regions-toolbar">
          <button
            type="button"
            className="secondary"
            disabled={busy || loading}
            onClick={() => void exportXlsx()}
          >
            {exporting ? "Экспорт…" : "Экспорт XLSX"}
          </button>
          <button
            type="button"
            disabled={busy || loading}
            onClick={() => fileInputRef.current?.click()}
          >
            {importing ? "Импорт…" : "Импорт XLSX"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importXlsx(file);
            }}
          />
        </div>
        {error && <div className="state error">{error}</div>}
        <div className="table-scroll">
          <table className="masks-table">
            <thead>
              <tr>
                <th>Разрядность</th>
                <th>Категория</th>
                <th>ABC</th>
                <th>Маска</th>
                <th>Тип</th>
                <th>Премиум</th>
                <th>Покупка</th>
                <th>Абонплата</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>{cellText(row.digit_capacity)}</td>
                  <td>{cellText(row.category)}</td>
                  <td>{cellText(row.abc)}</td>
                  <td>{row.mask}</td>
                  <td>{cellText(row.type_label)}</td>
                  <td>{priceText(row.premium)}</td>
                  <td>{priceText(row.purchase)}</td>
                  <td>{priceText(row.period)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && items.length === 0 && <div className="state">Загрузка…</div>}
          {!loading && !importing && !error && items.length === 0 && (
            <div className="state">Нет данных.</div>
          )}
        </div>
      </div>
    </div>
  );
}
