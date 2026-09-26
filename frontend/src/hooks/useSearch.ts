import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { SearchFilters, VideoPreviewWithTime } from "@api/types";
import { useSearchHints, useSearchResultsQuery } from "@/hooks/queries/useSearchQuery";

export interface UseSearchReturn {
    videos: VideoPreviewWithTime[];
    loading: boolean;
    hasMore: boolean;
    total: number;

    searchQuery: string;
    setSearchQuery: React.Dispatch<React.SetStateAction<string>>;
    searchFilters: SearchFilters | undefined;
    setSearchFilters: React.Dispatch<React.SetStateAction<SearchFilters | undefined>>;

    runSearch: (query: string, filters?: SearchFilters) => void;
    loadMoreSearchResults: () => void;

    /** Autocomplete suggestions for the current (debounced) query. */
    hints: string[];
}

/** Debounces a value so typing doesn't fire a request per keystroke. */
function useDebouncedValue<T>(value: T, delay = 300): T {
    const [debounced, setDebounced] = useState(value);
    useEffect(() => {
        const id = setTimeout(() => setDebounced(value), delay);
        return () => clearTimeout(id);
    }, [value, delay]);
    return debounced;
}

function filtersFromParams(params: URLSearchParams): SearchFilters | undefined {
    const category = params.get("category") || undefined;
    const minViews = params.get("min_views") ? Number(params.get("min_views")) : undefined;
    const maxViews = params.get("max_views") ? Number(params.get("max_views")) : undefined;
    const includeDescription = params.get("has_description") === "true";

    if (!category && !minViews && !maxViews && !includeDescription) {
        return undefined;
    }
    return { category, minViews, maxViews, includeDescription };
}

interface UseSearchOptions {
    /** Only the results page actually runs the search query. */
    enabled?: boolean;
}

export function useSearch({ enabled = false }: UseSearchOptions = {}): UseSearchReturn {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();

    const urlQuery = searchParams.get("q") || "";
    const urlFilters = useMemo(() => filtersFromParams(searchParams), [searchParams]);

    const [searchQuery, setSearchQuery] = useState(urlQuery);
    const [searchFilters, setSearchFilters] = useState<SearchFilters | undefined>(urlFilters);

    // The URL is the source of truth for what's being searched; keep the
    // local input in step when it changes (back/forward, or a new search).
    useEffect(() => setSearchQuery(urlQuery), [urlQuery]);
    useEffect(() => setSearchFilters(urlFilters), [urlFilters]);

    const results = useSearchResultsQuery(urlQuery, urlFilters, enabled);
    const hints = useSearchHints(useDebouncedValue(searchQuery));

    const runSearch = useCallback(
        (query: string, filters?: SearchFilters) => {
            const urlParams = new URLSearchParams();
            if (query) urlParams.set("q", query);

            if (filters) {
                if (filters.category && filters.category !== "All")
                    urlParams.set("category", filters.category);
                if (filters.minViews) urlParams.set("min_views", filters.minViews.toString());
                if (filters.maxViews) urlParams.set("max_views", filters.maxViews.toString());
                if (filters.includeDescription) urlParams.set("has_description", "true");
            }

            navigate(`/search-results?${urlParams.toString()}`);
        },
        [navigate],
    );

    return {
        videos: results.videos,
        loading: results.isLoading || results.isFetchingNextPage,
        hasMore: Boolean(results.hasMore),
        total: results.total,

        searchQuery,
        setSearchQuery,
        searchFilters,
        setSearchFilters,

        runSearch,
        loadMoreSearchResults: results.loadMore,

        hints,
    };
}
