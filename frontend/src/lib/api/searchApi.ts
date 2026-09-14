import clientApi from "@api/clientApi";
import type {
  SearchFilters,
  VideoPreview,
  VideoPreviewWithTime,
  SearchHintsResponse,
} from "@api/types";
import { timeAgo } from "@/utils/timeAgo";

export const SEARCH_PAGE_SIZE = 9;

/** Raw POST /api/search/video response (backend VideoSearchResponse). */
interface RawSearchResponse {
  results: RawSearchResult[];
  total: number;
  offset: number;
  limit: number;
}

/** Backend VideoResult -- note it uses `name`, not `title`. */
interface RawSearchResult {
  id: string;
  name: string;
  description?: string | null;
  category?: unknown;
  views?: number;
  thumbnail_url?: string | null;
  channel_name?: string | null;
  channel_id?: string | null;
  created_at?: string | null;
  score?: number | null;
}

export interface SearchPage {
  items: VideoPreviewWithTime[];
  total: number;
  offset: number;
  limit: number;
}

const toPreview = (item: RawSearchResult): VideoPreviewWithTime => {
  const created = item.created_at || new Date().toISOString();
  return {
    id: item.id,
    title: item.name || "Untitled Video",
    name: item.name,
    previewUrl: item.thumbnail_url || "/placeholder.jpg",
    thumbnail_url: item.thumbnail_url || "/placeholder.jpg",
    channel: item.channel_name || "Unknown Channel",
    channel_name: item.channel_name || "Unknown Channel",
    channel_avatar: "",
    views: item.views ?? 0,
    likesCount: 0,
    dislikesCount: 0,
    privacy: "public",
    createdAt: created,
    publishedAt: created,
    timeAgo: timeAgo(created),
  } satisfies VideoPreview & { timeAgo: string };
};

/**
 * Single source of truth for the search request. useSearch.ts used to carry
 * its own byte-for-byte copy of this, so a backend change had to be made in
 * two places or they silently diverged.
 */
export const search = async (
  query: string,
  filters?: SearchFilters,
  { offset = 0, limit = SEARCH_PAGE_SIZE }: { offset?: number; limit?: number } = {},
): Promise<SearchPage> => {
  const body = {
    query,
    limit,
    offset,
    category: filters?.category === "All" ? undefined : filters?.category,
    min_views: filters?.minViews,
    max_views: filters?.maxViews,
    smart_search: filters?.smartSearch ?? false,
    has_description: filters?.includeDescription ?? false,
  };

  const { data } = await clientApi.post<RawSearchResponse>(`/api/search/video`, body);

  return {
    items: (data.results || []).map(toPreview),
    total: data.total ?? 0,
    offset: data.offset ?? offset,
    limit: data.limit ?? limit,
  };
};

export const getHints = async (query: string): Promise<string[]> => {
  if (!query || query.trim().length < 1) return [];
  const { data } = await clientApi.get<SearchHintsResponse>(
    `/api/search/video_hints`,
    { params: { query } },
  );
  return data.hints || [];
};

export default {
  search,
  getHints,
};
