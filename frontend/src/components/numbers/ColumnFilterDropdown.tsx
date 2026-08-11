"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { apiFetch } from "@/lib/api/client";
import { formatCount } from "@/lib/format";
import type { ColumnFilters, FacetResponse } from "@/lib/types/api";
import {
  displayFacetValue,
  encodeFilters,
  toFilterToken,
} from "@/lib/numbers/filters";

type Props = {
  kind: "free" | "purchased";
  column: string;
  header: string;
  open: boolean;
  selected: string[];
  filters: ColumnFilters;
  numberLocalQ: string;
  onToggle: () => void;
  onChange: (values: string[]) => void;
  onClear: () => void;
};

export function ColumnFilterDropdown({
  kind,
  column,
  header,
  open,
  selected,
  filters,
  numberLocalQ,
  onToggle,
  onChange,
  onClear,
}: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<FacetResponse | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(qInput), 200);
    return () => clearTimeout(t);
  }, [qInput]);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setPos(null);
      return;
    }
    const update = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPos({
        top: rect.bottom + 4,
        left: rect.left,
        width: Math.max(rect.width, 260),
      });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setQInput("");
      setQ("");
      return;
    }
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ column, limit: "200" });
        const encoded = encodeFilters(filters);
        if (encoded) params.set("filters", encoded);
        if (numberLocalQ) params.set("number_local_q", numberLocalQ);
        if (q) params.set("q", q);
        const res = await apiFetch<FacetResponse>(
          `/api/v1/numbers/${kind}/facets?${params}`,
        );
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Ошибка загрузки");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, kind, column, filters, numberLocalQ, q]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (ev: MouseEvent) => {
      const t = ev.target as Node;
      if (triggerRef.current?.contains(t)) return;
      if (dropdownRef.current?.contains(t)) return;
      onToggle();
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, onToggle]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const active = selected.length > 0;

  const toggleValue = (rawValue: string) => {
    const token = toFilterToken(rawValue);
    if (selectedSet.has(token)) {
      onChange(selected.filter((v) => v !== token));
    } else {
      onChange([...selected, token]);
    }
  };

  const dropdown =
    open &&
    pos &&
    typeof document !== "undefined" &&
    createPortal(
      <div
        ref={dropdownRef}
        className="col-filter-dropdown"
        style={{ top: pos.top, left: pos.left, width: pos.width, position: "fixed" }}
      >
        <input
          className="col-filter-search"
          placeholder={`Поиск ${header}…`}
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          autoFocus
        />
        <div className="col-filter-list">
          {loading && <div className="col-filter-state">Загрузка…</div>}
          {error && <div className="col-filter-state error">{error}</div>}
          {!loading && !error && data?.items.length === 0 && (
            <div className="col-filter-state">Нет значений</div>
          )}
          {!loading &&
            !error &&
            data?.items.map((item) => {
              const token = toFilterToken(item.value);
              const checked = selectedSet.has(token);
              return (
                <label key={`${token}:${item.count}`} className="col-filter-option">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleValue(item.value)}
                  />
                  <span className="col-filter-option-label">
                    {displayFacetValue(item.value, column)}
                  </span>
                  <span className="col-filter-option-count">
                    ({formatCount(item.count)})
                  </span>
                </label>
              );
            })}
          {data?.truncated && (
            <div className="col-filter-state">Показаны первые значения — уточните поиск</div>
          )}
        </div>
        {active && (
          <button type="button" className="secondary col-filter-clear-btn" onClick={onClear}>
            Очистить «{header}»
          </button>
        )}
      </div>,
      document.body,
    );

  return (
    <div className={`col-header col-header-filter${active ? " active" : ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className="col-filter-trigger"
        onClick={onToggle}
      >
        <span className="col-header-label">
          {active ? `${selected.length} выбрано` : header}
        </span>
        <span className="col-filter-chevron" aria-hidden>
          ▾
        </span>
        {active && (
          <span
            className="col-filter-clear"
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.stopPropagation();
                onClear();
              }
            }}
          >
            ×
          </span>
        )}
      </button>
      {dropdown}
    </div>
  );
}
