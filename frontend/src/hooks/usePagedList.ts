import { useState, useCallback, useRef, useEffect } from "react";

interface PagedResponse<T> {
    items: T[];
    total: number;
}

interface UsePagedListOptions {
    pageSize?: number;
    autoLoad?: boolean;
}

export function usePagedList<T>(
    fetchFn: (page: number, size: number) => Promise<PagedResponse<T>>,
    { pageSize = 20, autoLoad = true }: UsePagedListOptions = {},
) {
    const [items, setItems] = useState<T[]>([]);
    const [loading, setLoading] = useState(autoLoad);
    const [hasMore, setHasMore] = useState(true);

    const pageRef = useRef(1);
    const hasMoreRef = useRef(true);
    const fetchFnRef = useRef(fetchFn);
    fetchFnRef.current = fetchFn;

    const loadMore = useCallback(async () => {
        if (!hasMoreRef.current) return;
        setLoading(true);
        try {
            const res = await fetchFnRef.current(pageRef.current, pageSize);
            const newItems = res.items ?? [];
            const total = res.total ?? 0;
            setItems((prev) => {
                const merged = [...prev, ...newItems];
                const more = merged.length < total;
                hasMoreRef.current = more;
                setHasMore(more);
                return merged;
            });
            pageRef.current += 1;
        } catch {
            // keep current state on error
        } finally {
            setLoading(false);
        }
    }, [pageSize]);

    useEffect(() => {
        if (autoLoad) loadMore();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return { items, setItems, loading, hasMore, setHasMore, loadMore };
}
