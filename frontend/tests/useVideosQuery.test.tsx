import { act, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHookWithProviders } from "./utils";
import { useVideosQuery, VIDEOS_PAGE_SIZE } from "../src/hooks/queries/useVideosQuery";
import type { VideoPreview } from "../src/lib/api/types";

vi.mock("@api/videoApi", () => ({
    default: {},
    getVideos: vi.fn(),
    getVideoPreviewsByCategory: vi.fn(),
    getVideo: vi.fn(),
}));

import { getVideos, getVideoPreviewsByCategory } from "@api/videoApi";

const video = (i: number): VideoPreview => ({
    id: `v${i}`,
    title: `t${i}`,
    previewUrl: "",
    channel_avatar: "",
    channel: "c",
    createdAt: "2025-01-01T00:00:00Z",
    publishedAt: "2025-01-01T00:00:00Z",
    views: 0,
    likesCount: 0,
    dislikesCount: 0,
    privacy: "public",
});

const fullPage = (from: number) => Array.from({ length: VIDEOS_PAGE_SIZE }, (_, i) => video(from + i));

describe("useVideosQuery", () => {
    beforeEach(() => vi.clearAllMocks());

    it("fetches page 1 and flags more pages when the page is full", async () => {
        vi.mocked(getVideos).mockResolvedValue(fullPage(0));
        const { result } = renderHookWithProviders(() => useVideosQuery());

        await waitFor(() => expect(result.current.isLoading).toBe(false));

        expect(getVideos).toHaveBeenCalledWith({ page: 1, size: VIDEOS_PAGE_SIZE, channel_name: undefined });
        expect(result.current.videos).toHaveLength(VIDEOS_PAGE_SIZE);
        expect(result.current.hasMore).toBe(true);
        expect(result.current.videos[0].timeAgo).toBeTruthy();
    });

    it("stops paginating after a short page", async () => {
        vi.mocked(getVideos).mockResolvedValue([video(0), video(1)]);
        const { result } = renderHookWithProviders(() => useVideosQuery());

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.hasMore).toBe(false);

        act(() => result.current.loadMore());
        expect(getVideos).toHaveBeenCalledTimes(1);
    });

    it("appends the next page on loadMore", async () => {
        vi.mocked(getVideos)
            .mockResolvedValueOnce(fullPage(0))
            .mockResolvedValueOnce([video(100)]);
        const { result } = renderHookWithProviders(() => useVideosQuery());
        await waitFor(() => expect(result.current.hasMore).toBe(true));

        act(() => result.current.loadMore());

        await waitFor(() => expect(result.current.videos).toHaveLength(VIDEOS_PAGE_SIZE + 1));
        expect(getVideos).toHaveBeenLastCalledWith({ page: 2, size: VIDEOS_PAGE_SIZE, channel_name: undefined });
        expect(result.current.hasMore).toBe(false);
    });

    it("uses the category endpoint for a non-'All' category", async () => {
        vi.mocked(getVideoPreviewsByCategory).mockResolvedValue([video(0)]);
        const { result } = renderHookWithProviders(() => useVideosQuery({ category: "gaming" }));

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(getVideoPreviewsByCategory).toHaveBeenCalledWith("gaming", 1, VIDEOS_PAGE_SIZE);
        expect(getVideos).not.toHaveBeenCalled();
    });

    it("treats 'All' as no category filter", async () => {
        vi.mocked(getVideos).mockResolvedValue([]);
        renderHookWithProviders(() => useVideosQuery({ category: "All" }));

        await waitFor(() => expect(getVideos).toHaveBeenCalled());
        expect(getVideoPreviewsByCategory).not.toHaveBeenCalled();
    });

    it("drops the currently-watched video via excludeId", async () => {
        vi.mocked(getVideos).mockResolvedValue([video(0), video(1), video(2)]);
        const { result } = renderHookWithProviders(() => useVideosQuery({ excludeId: "v1" }));

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.videos.map((v) => v.id)).toEqual(["v0", "v2"]);
    });

    it("surfaces a failed request as `error`", async () => {
        vi.mocked(getVideos).mockRejectedValue(new Error("down"));
        const { result } = renderHookWithProviders(() => useVideosQuery());

        await waitFor(() => expect(result.current.error).toBeTruthy());
        expect(result.current.videos).toEqual([]);
    });
});
