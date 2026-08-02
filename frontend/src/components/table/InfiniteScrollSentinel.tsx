"use client";

import { useEffect, useRef } from "react";
import { formatCount } from "@/lib/format";

type Props = {
  root: HTMLElement | null;
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  loadedCount: number;
  total: number;
};

export function InfiniteScrollSentinel({
  root,
  hasMore,
  loading,
  onLoadMore,
  loadedCount,
  total,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !hasMore || !root) return;

    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !loading) {
          onLoadMore();
        }
      },
      { root, rootMargin: "160px", threshold: 0 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [root, hasMore, loading, onLoadMore]);

  return (
    <div ref={ref} className="infinite-sentinel">
      {loading
        ? "Загрузка…"
        : hasMore
          ? "Прокрутите ниже для загрузки ещё"
          : loadedCount > 0
            ? `Показано ${formatCount(loadedCount)} из ${formatCount(total)}`
            : null}
    </div>
  );
}
