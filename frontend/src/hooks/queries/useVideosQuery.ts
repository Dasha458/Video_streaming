import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getVideo, getVideos, getVideoPreviewsByCategory } from "@api/videoApi";
import { timeAgo } from "@/utils/timeAgo";
import type { VideoDetail, VideoPreviewWithTime } from "@api/types";

export const VIDEOS_PAGE_SIZE = 12;

interface VideosQueryOptions {
    /** Category pill on Home/Watch. "All" (or omitted) means no filter. */
    category?: string;
    /** Restricts the list to one channel (Channel page). */
    channelName?: string;
    pageSize?: number;
    /** Drops this id from the results -- the video already being watched. */
    excludeId?: string;
    enabled?: boolean;
}

const withTimeAgo = (videos: Awaited<ReturnType<typeof getVideos>>): VideoPreviewWithTime[] =>
    videos.map((v) => ({
        ...v,
        timeAgo: timeAgo(v.createdAt || new Date().toISOString()),
    }));

/**
 * Paginated video list, shared by Home, Channel and the Watch sidebar.
 *
 * Replaces four separate hand-rolled implementations of the same
 * page/hasMore/loading/dedup state machine.
 */
export function useVideosQuery({
    category,
    channelName,
    pageSize = VIDEOS_PAGE_SIZE,
    excludeId,
    enabled = true,
}: VideosQueryOptions = {}) {
    const byCategory = Boolean(category && category !== "All");

    const query = useInfiniteQuery({
        queryKey: ["videos", { category: byCategory ? category : "All", channelName, pageSize }],
        queryFn: async ({ pageParam }) => {
            const page = byCategory
                ? await getVideoPreviewsByCategory(category!, pageParam, pageSize)
                : await getVideos({ page: pageParam, size: pageSize, channel_name: channelName });
            return withTimeAgo(page);
        },
        initialPageParam: 1,
        // The list endpoints return a plain array, so a short page is the
        // only available end-of-list signal.
        getNextPageParam: (lastPage, allPages) =>
            lastPage.length < pageSize ? undefined : allPages.length + 1,
        enabled,
    });

    const videos = (query.data?.pages.flat() ?? []).filter((v) => v.id !== excludeId);

    return {
        videos,
        error: query.error,
        isLoading: query.isLoading,
        isFetchingNextPage: query.isFetchingNextPage,
        hasMore: query.hasNextPage,
        loadMore: () => {
            if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
        },
    };
}

/** Single video for the watch page. */
export function useVideoQuery(videoId: string | undefined) {
    const query = useQuery({
        queryKey: ["video", videoId],
        queryFn: async () => {
            const data = await getVideo(videoId!);
            const createdAt = data.created_at || new Date().toISOString();
            return {
                id: data.id || "",
                title: data.title || "",
                name: data.name,
                previewUrl: data.thumbnail_url || data.preview_url || "",
                thumbnail_url: data.thumbnail_url,
                createdAt,
                publishedAt: createdAt,
                channel_avatar: data.channel_avatar || "",
                hlsUrl: data.master_hls_url || "",
                channel: data.channel_name || "Unknown Channel",
                channel_name: data.channel_name,
                views: data.views_count ?? 0,
                privacy: data.privacy || "Private",
                likesCount: data.likes_count ?? 0,
                dislikesCount: data.dislikes_count ?? 0,
                dislikeCount: data.dislikes_count ?? 0,
                userReaction: null,
                description: data.description || "No description provided for this video.",
                timeAgo: timeAgo(createdAt),
            } satisfies VideoDetail;
        },
        enabled: Boolean(videoId),
    });

    return {
        video: query.data ?? null,
        error: query.error ? "Video not found" : null,
        isLoading: query.isLoading,
    };
}
