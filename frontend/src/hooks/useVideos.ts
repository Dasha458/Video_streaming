import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useVideoQuery, useVideosQuery } from "@/hooks/queries/useVideosQuery";
import type { VideoDetail } from "@api/types";

/** Formats raw view counts the way YouTube does: 1.2K / 3.4M. */
export function formatViews(views: number | undefined): string {
    if (views === undefined) return "";
    if (views < 1000) return `${views}`;
    if (views < 1_000_000) return `${(views / 1000).toFixed(1).replace(/\.0$/, "")}K`;
    return `${(views / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

/**
 * Everything the watch page needs: the video itself plus the "up next" list.
 *
 * Both are React Query-backed now. The hook used to expose its raw state
 * setters (setVideos/setPage/setLoading/setHasMore), which let callers
 * corrupt its internals; it now exposes actions only. `setVideo` is kept
 * as a narrow local override so optimistic like/dislike updates can patch
 * the cached video without a refetch.
 */
export function useVideo(activeCategory: string = "All") {
    const [searchParams] = useSearchParams();
    const videoId = searchParams.get("v") ?? undefined;
    const queryClient = useQueryClient();

    const { video: fetchedVideo, error, isLoading } = useVideoQuery(videoId);
    const list = useVideosQuery({ category: activeCategory, excludeId: videoId });

    // Local optimistic patch layered over the cached video.
    const [override, setOverride] = useState<VideoDetail | null>(null);
    const video = override ?? fetchedVideo;

    const setVideo = useCallback(
        (next: VideoDetail | ((prev: VideoDetail | null) => VideoDetail | null) | null) => {
            setOverride((prev) => {
                const base = prev ?? fetchedVideo;
                const resolved = typeof next === "function" ? next(base) : next;
                if (resolved && videoId) {
                    queryClient.setQueryData(["video", videoId], resolved);
                }
                return resolved;
            });
        },
        [fetchedVideo, queryClient, videoId],
    );

    const metaDataText = useMemo(() => {
        if (!video) return "";
        return `${formatViews(video.views)} views${video.timeAgo ? " · " + video.timeAgo : ""}`;
    }, [video]);

    return {
        video,
        videos: list.videos,
        error,
        loading: isLoading,
        hasMore: Boolean(list.hasMore),
        loadMore: list.loadMore,
        isFetchingMore: list.isFetchingNextPage,
        formatViews,
        metaDataText,
        setVideo,
    };
}
