"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { Page } from "@/lib/types/api";

const INFINITE_PAGE_SIZE = 100;

type UseInfinitePageOptions = {
  /** Return null to skip fetching (e.g. nothing selected). */
  getPath: (page: number, pageSize: number) => string | null;
  /** When these change, list resets and page 1 is loaded again. */
  deps: ReadonlyArray<unknown>;
  enabled?: boolean;
  /** Keep current rows on screen until page 1 arrives (Twilio list refresh). */
  keepPreviousOnReset?: boolean;
};

export function useInfinitePage<T>({
  getPath,
  deps,
  enabled = true,
  keepPreviousOnReset = false,
}: UseInfinitePageOptions) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadingRef = useRef(false);
  const requestId = useRef(0);
  const pageRef = useRef(0);
  const hasMoreRef = useRef(false);
  const getPathRef = useRef(getPath);
  getPathRef.current = getPath;

  const applyPageResult = useCallback((data: Page<T>, append: boolean) => {
    setItems((prev) => (append ? [...prev, ...data.items] : data.items));
    pageRef.current = data.page;
    setTotal(data.total);
    const more = data.page < data.total_pages;
    setHasMore(more);
    hasMoreRef.current = more;
  }, []);

  const fetchPage = useCallback(
    async (nextPage: number, append: boolean) => {
      const path = getPathRef.current(nextPage, INFINITE_PAGE_SIZE);
      if (!path) {
        setItems([]);
        pageRef.current = 0;
        setTotal(0);
        setHasMore(false);
        hasMoreRef.current = false;
        return;
      }
      if (append && loadingRef.current) return;

      const rid = ++requestId.current;
      loadingRef.current = true;
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);

      try {
        const data = await apiFetch<Page<T>>(path);
        if (rid !== requestId.current) return;
        applyPageResult(data, append);
      } catch (e) {
        if (rid !== requestId.current) return;
        setError(e instanceof Error ? e.message : "Ошибка загрузки");
        if (!append) {
          setItems([]);
          pageRef.current = 0;
          setTotal(0);
          setHasMore(false);
          hasMoreRef.current = false;
        }
      } finally {
        if (rid === requestId.current) {
          loadingRef.current = false;
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [applyPageResult],
  );

  const depsKey = JSON.stringify(deps);

  useEffect(() => {
    if (!enabled) {
      requestId.current += 1;
      loadingRef.current = false;
      setItems([]);
      pageRef.current = 0;
      setTotal(0);
      setHasMore(false);
      hasMoreRef.current = false;
      setError(null);
      setLoading(false);
      setLoadingMore(false);
      return;
    }
    pageRef.current = 0;
    hasMoreRef.current = false;
    if (!keepPreviousOnReset) setItems([]);
    setHasMore(false);
    void fetchPage(1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset keyed by depsKey
  }, [depsKey, enabled, fetchPage, keepPreviousOnReset]);

  const loadMore = useCallback(() => {
    if (!enabled || !hasMoreRef.current || loadingRef.current) return;
    void fetchPage(pageRef.current + 1, true);
  }, [enabled, fetchPage]);

  return {
    items,
    total,
    hasMore,
    loading,
    loadingMore,
    error,
    loadMore,
    pageSize: INFINITE_PAGE_SIZE,
  };
}
