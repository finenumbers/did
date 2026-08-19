"use client";

import { useState } from "react";
import { DirectoryExplorer } from "@/components/directory/DirectoryExplorer";
import { ApiError, apiDownload, apiUpload } from "@/lib/api/client";
import type { DirectoryColumn } from "@/lib/directory/filters";
import { formatPrice } from "@/lib/format";
import { encodeFilters } from "@/lib/numbers/filters";
import type { ColumnFilters, MaskTypeItem, MaskTypesLoadResult } from "@/lib/types/api";

function cellText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function priceText(value: string | number | null | undefined): string {
  return formatPrice(value) ?? "—";
}

function priceFacet(value: string | number | null | undefined): string {
  return formatPrice(value) ?? "";
}

const COLUMNS: DirectoryColumn<MaskTypeItem>[] = [
  {
    key: "digit_capacity",
    header: "Разрядность",
    text: (r) => cellText(r.digit_capacity),
    facet: (r) => r.digit_capacity || "",
  },
  {
    key: "category",
    header: "Категория",
    text: (r) => cellText(r.category),
    facet: (r) => r.category || "",
  },
  {
    key: "abc",
    header: "ABC",
    text: (r) => cellText(r.abc),
    facet: (r) => r.abc || "",
  },
  {
    key: "mask",
    header: "Маска",
    text: (r) => r.mask,
    facet: (r) => r.mask,
    highlight: true,
    cellClassName: "col-number-local",
  },
  {
    key: "type_label",
    header: "Тип",
    text: (r) => cellText(r.type_label),
    facet: (r) => r.type_label || "",
  },
  {
    key: "premium",
    header: "Премиум",
    text: (r) => priceText(r.premium),
    facet: (r) => priceFacet(r.premium),
  },
  {
    key: "purchase",
    header: "Покупка",
    text: (r) => priceText(r.purchase),
    facet: (r) => priceFacet(r.purchase),
  },
];

function maskSearch(row: MaskTypeItem): string {
  return row.mask;
}

function maskRowClass(row: MaskTypeItem): string | undefined {
  if (row.category === "Мобильный") return "masks-row-mobile";
  if (row.category === "Бесплатный вызов") return "masks-row-tollfree";
  if (row.category === "Городской" && row.premium != null && row.premium !== "") {
    return "masks-row-premium";
  }
  return undefined;
}

function maskListPath(
  page: number,
  pageSize: number,
  query: { searchQ: string; filters: ColumnFilters },
): string {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const encoded = encodeFilters(query.filters);
  if (encoded) params.set("filters", encoded);
  const q = query.searchQ.trim();
  if (q) params.set("mask_q", q);
  return `/api/v1/mask-types?${params}`;
}

function maskFacetsPath(args: {
  column: string;
  filters: ColumnFilters;
  searchQ: string;
  q: string;
}): string {
  const params = new URLSearchParams({ column: args.column, limit: "200" });
  const encoded = encodeFilters(args.filters);
  if (encoded) params.set("filters", encoded);
  const mq = args.searchQ.trim();
  if (mq) params.set("mask_q", mq);
  if (args.q) params.set("q", args.q);
  return `/api/v1/mask-types/facets?${params}`;
}

export default function MasksPage() {
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

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
      "Обновить справочник из файла? Для семёрок минимум три категории (Городской, Мобильный, Бесплатный вызов) с пустым ABC — их нельзя удалить. Для 5 и 6 категория всегда Городской, из файла не берётся. Пустые тип и цены затирают эту строку. Лишние строки с ABC, которых нет в файле, удаляются. Маски, которых нет в файле, не меняются.",
    );
    if (!ok) return;
    setImporting(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      await apiUpload<MaskTypesLoadResult>("/api/v1/mask-types/import.xlsx", body);
      setReloadToken((n) => n + 1);
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
          items={[]}
          columns={COLUMNS}
          searchPlaceholder="Маска"
          searchChipLabel="Маска"
          searchValue={maskSearch}
          tableClassName="masks-table"
          loading={false}
          error={error}
          exporting={exporting}
          importing={importing}
          emptyText="Нет данных."
          onExport={() => void exportXlsx()}
          onImport={(file) => void importXlsx(file)}
          rowClassName={maskRowClass}
          getServerPath={maskListPath}
          getServerFacets={maskFacetsPath}
          reloadToken={reloadToken}
        />
      </div>
    </div>
  );
}
