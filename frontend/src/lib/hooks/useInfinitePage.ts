"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { Page } from "@/lib/types/api";

export const INFINITE_PAGE_SIZE = 100;

type UseInfinitePageOptions = {
  /** Return null to skip fetching (e.g. nothing selected). */
  getPath: (page: number, pageSize: number) => string | null;
  /** When these change, list resets and page 1 is loaded again. */
  deps: ReadonlyArray<unknown>;
  enabled?: boolean;
};

export function useInfinitePage<T>({
  getPath,
  deps,
  enabled = true,
}: UseInfinitePageOptions) {
  const [items, setItems] = useState<T[]>([]);
  const [page, setPage] = useState(0);
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
    setPage(data.page);
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
        setPage(0);
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
          setPage(0);
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
      setPage(0);
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
    setItems([]);
    setPage(0);
    setHasMore(false);
    void fetchPage(1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset keyed by depsKey
  }, [depsKey, enabled, fetchPage]);

  const loadMore = useCallback(() => {
    if (!enabled || !hasMoreRef.current || loadingRef.current) return;
    void fetchPage(pageRef.current + 1, true);
  }, [enabled, fetchPage]);

  const reload = useCallback(() => {
    if (!enabled) return;
    pageRef.current = 0;
    hasMoreRef.current = false;
    setItems([]);
    setPage(0);
    setHasMore(false);
    void fetchPage(1, false);
  }, [enabled, fetchPage]);

  /** Re-fetch already loaded pages without clearing the list first. */
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const lastPage = Math.max(pageRef.current, 1);
    const rid = ++requestId.current;
    loadingRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const collected: T[] = [];
      let totalCount = 0;
      let totalPages = 1;
      let loadedPage = 0;

      for (let p = 1; p <= lastPage; p += 1) {
        const path = getPathRef.current(p, INFINITE_PAGE_SIZE);
        if (!path) break;
        const data = await apiFetch<Page<T>>(path);
        if (rid !== requestId.current) return;
        collected.push(...data.items);
        totalCount = data.total;
        totalPages = data.total_pages;
        loadedPage = data.page;
        if (data.page >= data.total_pages) break;
      }

      if (rid !== requestId.current) return;
      setItems(collected);
      setPage(loadedPage);
      pageRef.current = loadedPage;
      setTotal(totalCount);
      const more = loadedPage < totalPages;
      setHasMore(more);
      hasMoreRef.current = more;
    } catch (e) {
      if (rid !== requestId.current) return;
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      if (rid === requestId.current) {
        loadingRef.current = false;
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [enabled]);

  return {
    items,
    page,
    total,
    hasMore,
    loading,
    loadingMore,
    error,
    loadMore,
    reload,
    refresh,
    pageSize: INFINITE_PAGE_SIZE,
  };
}
