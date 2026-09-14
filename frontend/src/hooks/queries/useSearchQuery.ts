import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getHints, search, SEARCH_PAGE_SIZE } from "@api/searchApi";
import type { SearchFilters } from "@api/types";

/**
 * Paginated search results.
 *
 * Real paging only became possible once the backend gained an `offset`
 * parameter -- before that, "load more" re-requested the same top-N matches
 * every time.
 */
export function useSearchResultsQuery(
    query: string,
    filters: SearchFilters | undefined,
    enabled = true,
) {
    const hasCriteria = Boolean(query?.trim()) || Boolean(filters);

    const infinite = useInfiniteQuery({
        queryKey: ["search", query, filters],
        queryFn: ({ pageParam }) => search(query, filters, { offset: pageParam }),
        initialPageParam: 0,
        getNextPageParam: (lastPage) => {
            const consumed = lastPage.offset + lastPage.items.length;
            return consumed < lastPage.total ? consumed : undefined;
        },
        enabled: enabled && hasCriteria,
    });

    return {
        videos: infinite.data?.pages.flatMap((p) => p.items) ?? [],
        total: infinite.data?.pages[0]?.total ?? 0,
        isLoading: infinite.isLoading,
        isFetchingNextPage: infinite.isFetchingNextPage,
        hasMore: infinite.hasNextPage,
        error: infinite.error,
        loadMore: () => {
            if (infinite.hasNextPage && !infinite.isFetchingNextPage) {
                void infinite.fetchNextPage();
            }
        },
    };
}

/** Autocomplete suggestions for the search box. */
export function useSearchHints(query: string) {
    const trimmed = query.trim();

    const { data } = useQuery({
        queryKey: ["search-hints", trimmed],
        queryFn: () => getHints(trimmed),
        enabled: trimmed.length > 0,
        // Suggestions for a given prefix barely change; keep them cached so
        // backspacing through a word doesn't re-request everything.
        staleTime: 5 * 60_000,
    });

    return data ?? [];
}

export { SEARCH_PAGE_SIZE };
