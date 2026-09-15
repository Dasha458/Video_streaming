import { useQuery } from "@tanstack/react-query";
import { getRealtime, type Period, type RealtimeData } from "@/lib/api/analyticsApi";

/**
 * One period-scoped Studio metric.
 *
 * Every Studio tab repeated the same `useState(null) + useState(loading) +
 * useEffect(() => { setLoading(true); fetch(period).then(setData).finally(...) },
 * [period])` block. This is that block, once, with caching so switching
 * back to a tab you already opened doesn't refetch it.
 */
export function useStudioData<T>(
    key: string,
    fetcher: (period: Period) => Promise<T>,
    period: Period,
) {
    const { data, isLoading, error } = useQuery({
        queryKey: ["studio", key, period],
        queryFn: () => fetcher(period),
    });

    return { data: data ?? null, loading: isLoading, error };
}

/** Real-time tab: no period, refreshed every 30s. */
export function useRealtimeData() {
    const { data, isLoading, error } = useQuery<RealtimeData>({
        queryKey: ["studio", "realtime"],
        queryFn: getRealtime,
        refetchInterval: 30_000,
        // Default behaviour, spelled out because it matters here: the old
        // setInterval kept polling in a hidden tab.
        refetchIntervalInBackground: false,
    });

    return { data: data ?? null, loading: isLoading, error };
}
