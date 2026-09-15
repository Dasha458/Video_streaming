/**
 * The mappers in lib/api are the boundary between the backend's snake_case
 * payloads and the frontend's types. A silent field rename on either side
 * shows up here first.
 */
import { describe, expect, it } from "vitest";
import { AxiosError, type AxiosResponse } from "axios";
import { mapToDetail, mapToPreview } from "../src/lib/api/videoApi";
import { mapCommentFromApi } from "../src/lib/api/commentApi";
import { getApiErrorMessage } from "../src/utils/apiError";

describe("mapToPreview (backend VideoPreview -> frontend VideoPreview)", () => {
    const raw = {
        id: "v1",
        title: "Hello",
        thumbnail: "/t.jpg",
        channel_avatar: "/a.jpg",
        channel_name: "Chan",
        views_count: 42,
        likes_count: 5,
        dislikes_count: 1,
        privacy: "public",
        status: "Ready",
        created_at: "2025-01-01T00:00:00Z",
    };

    it("maps every backend field onto the frontend shape", () => {
        const v = mapToPreview(raw);
        expect(v).toMatchObject({
            id: "v1",
            title: "Hello",
            name: "Hello",
            previewUrl: "/t.jpg",
            thumbnail_url: "/t.jpg",
            channel: "Chan",
            channel_name: "Chan",
            channel_avatar: "/a.jpg",
            views: 42,
            likesCount: 5,
            dislikesCount: 1,
            privacy: "public",
            status: "Ready",
            createdAt: "2025-01-01T00:00:00Z",
            publishedAt: "2025-01-01T00:00:00Z",
        });
    });

    it("falls back to a placeholder thumbnail and safe defaults", () => {
        const v = mapToPreview({ ...raw, thumbnail: "", title: "", channel_name: "", channel_avatar: "" });
        expect(v.previewUrl).toBe("/placeholder.jpg");
        expect(v.title).toBe("Untitled");
        expect(v.channel).toBe("Unknown Channel");
        expect(v.channel_avatar).toBe("");
    });
});

describe("mapToDetail (backend VideoPlayback -> frontend Video)", () => {
    const raw = {
        id: "v1",
        name: "Playback title",
        description: "desc",
        privacy: "public",
        created_at: "2025-01-01T00:00:00Z",
        resolutions: ["360p", "720p"],
        thumbnail_url: "/t.jpg",
        avatar_url: "/a.jpg",
        channel_name: "Chan",
        likes_count: 3,
        dislikes_count: 0,
        views_count: 10,
        master_hls_url: "http://x/master.m3u8",
    };

    it("uses backend `name` as both title and name, and avatar_url as channel_avatar", () => {
        const v = mapToDetail(raw);
        expect(v.title).toBe("Playback title");
        expect(v.name).toBe("Playback title");
        expect(v.channel_avatar).toBe("/a.jpg");
        expect(v.master_hls_url).toBe("http://x/master.m3u8");
        expect(v.description).toBe("desc");
    });

    it("capitalises privacy the way the UI expects", () => {
        expect(mapToDetail(raw).privacy).toBe("Public");
        expect(mapToDetail({ ...raw, privacy: "private" }).privacy).toBe("Private");
    });

    it("tolerates null optional fields from the backend", () => {
        const v = mapToDetail({ ...raw, description: null, thumbnail_url: null, avatar_url: null, master_hls_url: null });
        expect(v.description).toBeUndefined();
        expect(v.thumbnail_url).toBe("/placeholder.jpg");
        expect(v.channel_avatar).toBe("");
        expect(v.master_hls_url).toBe("");
    });
});

describe("mapCommentFromApi (backend CommentRead -> VideoComment)", () => {
    const raw = {
        id: "c1",
        user_id: "u1",
        content: "top",
        created_at: "2025-01-01T00:00:00Z",
        likes_count: 2,
        dislikes_count: 0,
        user_name: "alice",
        user_avatar: null,
        replies: [
            {
                id: "c2",
                user_id: "u2",
                content: "reply",
                created_at: "2025-01-02T00:00:00Z",
                likes_count: 0,
                dislikes_count: 1,
                parent_id: "c1",
                user_name: "bob",
                user_avatar: "/b.jpg",
            },
        ],
    };

    it("maps snake_case to camelCase and recurses into replies", () => {
        const c = mapCommentFromApi(raw);
        expect(c).toMatchObject({
            id: "c1",
            userId: "u1",
            content: "top",
            createdAt: "2025-01-01T00:00:00Z",
            likesCount: 2,
            dislikesCount: 0,
            user_name: "alice",
        });
        expect(c.user_avatar).toBeUndefined();
        expect(c.replies).toHaveLength(1);
        expect(c.replies?.[0]).toMatchObject({ id: "c2", userId: "u2", user_avatar: "/b.jpg" });
    });

    it("omits `replies` entirely when the backend sends none", () => {
        const { replies: _r, ...noReplies } = raw;
        void _r;
        expect(mapCommentFromApi(noReplies)).not.toHaveProperty("replies");
    });
});

describe("getApiErrorMessage", () => {
    const axiosErr = (data: unknown) =>
        new AxiosError("boom", "500", undefined, undefined, { data } as AxiosResponse);

    it("prefers the unified {message} envelope the backend now returns", () => {
        expect(getApiErrorMessage(axiosErr({ code: "X", message: "Nope" }))).toBe("Nope");
    });

    it("still reads the legacy {detail} shape", () => {
        expect(getApiErrorMessage(axiosErr({ detail: "Old" }))).toBe("Old");
    });

    it("falls back for non-axios errors and empty bodies", () => {
        expect(getApiErrorMessage(new Error("x"))).toBe("Something went wrong");
        expect(getApiErrorMessage(axiosErr(undefined), "custom")).toBe("custom");
    });
});
