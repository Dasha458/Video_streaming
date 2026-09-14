import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

interface PagedResponse<T> {
    items: T[];
    total: number;
}

type PagedFetcher<T> = (page: number, size: number) => Promise<PagedResponse<T>>;

interface UsePagedListQueryOptions {
    pageSize?: number;
}

/**
 * Infinite list over any `{ items, total }` endpoint (history, liked,
 * watch later). Replaces the hand-rolled usePagedList, whose page/hasMore
 * bookkeeping lived in refs so that callers had to be handed setItems /
 * setHasMore just to drop a row after deleting it.
 */
export function usePagedListQuery<T>(
    key: string,
    fetchFn: PagedFetcher<T>,
    { pageSize = 20 }: UsePagedListQueryOptions = {},
) {
    const queryClient = useQueryClient();
    const queryKey = [key, { pageSize }];

    const query = useInfiniteQuery({
        queryKey,
        queryFn: ({ pageParam }) => fetchFn(pageParam, pageSize),
        initialPageParam: 1,
        getNextPageParam: (lastPage, allPages) => {
            const loaded = allPages.reduce((n, page) => n + page.items.length, 0);
            return loaded < (lastPage.total ?? 0) ? allPages.length + 1 : undefined;
        },
    });

    const items = query.data?.pages.flatMap((p) => p.items) ?? [];

    return {
        items,
        isLoading: query.isLoading,
        isFetchingNextPage: query.isFetchingNextPage,
        hasMore: query.hasNextPage,
        error: query.error,
        loadMore: () => {
            if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
        },
        /** Re-fetch after a mutation (removing one row, clearing the list). */
        refresh: () => queryClient.invalidateQueries({ queryKey }),
    };
}
