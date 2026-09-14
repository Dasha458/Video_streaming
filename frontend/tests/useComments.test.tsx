import { act, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHookWithProviders } from "./utils";
import { useComments } from "../src/hooks/useComments";

vi.mock("@api/commentApi", async () => {
    const actual = await vi.importActual<typeof import("../src/lib/api/commentApi")>(
        "../src/lib/api/commentApi",
    );
    return {
        ...actual, // keep the real mapCommentFromApi
        getComments: vi.fn(),
        addComment: vi.fn(),
        addReply: vi.fn(),
        deleteComment: vi.fn(),
        reactToComment: vi.fn(),
    };
});

import { addComment, addReply, deleteComment, getComments, reactToComment } from "@api/commentApi";

const rawComment = (id: string, overrides: Record<string, unknown> = {}) => ({
    id,
    user_id: "u1",
    content: `body ${id}`,
    created_at: "2025-01-01T00:00:00Z",
    likes_count: 0,
    dislikes_count: 0,
    user_name: "alice",
    user_avatar: null,
    replies: [],
    ...overrides,
});

describe("useComments", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(getComments).mockResolvedValue({
            items: [rawComment("c1"), rawComment("c2")],
            page: 1,
            size: 100,
            total: 2,
        });
    });

    it("loads and maps the thread for a video", async () => {
        const { result } = renderHookWithProviders(() => useComments("vid"));

        await waitFor(() => expect(result.current.comments).toHaveLength(2));
        expect(getComments).toHaveBeenCalledWith("vid", 1, 100);
        expect(result.current.comments[0]).toMatchObject({ id: "c1", userId: "u1", content: "body c1" });
    });

    it("does not fetch without a video id", () => {
        renderHookWithProviders(() => useComments(undefined));
        expect(getComments).not.toHaveBeenCalled();
    });

    it("prepends a new top-level comment", async () => {
        vi.mocked(addComment).mockResolvedValue(rawComment("c3", { content: "new" }));
        const { result } = renderHookWithProviders(() => useComments("vid"));
        await waitFor(() => expect(result.current.comments).toHaveLength(2));

        await act(() => result.current.addComment("new"));

        expect(addComment).toHaveBeenCalledWith("vid", "new");
        await waitFor(() =>
            expect(result.current.comments.map((c) => c.id)).toEqual(["c3", "c1", "c2"]),
        );
        expect(result.current.comments[0].replies).toEqual([]);
    });

    it("appends a reply under its parent only", async () => {
        vi.mocked(addReply).mockResolvedValue(rawComment("r1", { content: "re", parent_id: "c1" }));
        const { result } = renderHookWithProviders(() => useComments("vid"));
        await waitFor(() => expect(result.current.comments).toHaveLength(2));

        await act(() => result.current.addReply("c1", "re"));

        expect(addReply).toHaveBeenCalledWith("vid", "c1", "re");
        await waitFor(() =>
            expect(result.current.comments[0].replies?.map((r) => r.id)).toEqual(["r1"]),
        );
        expect(result.current.comments[1].replies).toEqual([]);
    });

    it("removes a top-level comment, or just one reply when parentId is given", async () => {
        vi.mocked(getComments).mockResolvedValue({
            items: [rawComment("c1", { replies: [rawComment("r1"), rawComment("r2")] }), rawComment("c2")],
            page: 1,
            size: 100,
            total: 2,
        });
        vi.mocked(deleteComment).mockResolvedValue(undefined);
        const { result } = renderHookWithProviders(() => useComments("vid"));
        await waitFor(() => expect(result.current.comments).toHaveLength(2));

        act(() => result.current.deleteComment("r1", "c1"));
        await waitFor(() => expect(result.current.comments[0].replies?.map((r) => r.id)).toEqual(["r2"]));
        expect(result.current.comments).toHaveLength(2);

        act(() => result.current.deleteComment("c2"));
        await waitFor(() => expect(result.current.comments.map((c) => c.id)).toEqual(["c1"]));
    });

    it("updates like/dislike counts from the reaction response, for replies too", async () => {
        vi.mocked(getComments).mockResolvedValue({
            items: [rawComment("c1", { replies: [rawComment("r1")] })],
            page: 1,
            size: 100,
            total: 1,
        });
        vi.mocked(reactToComment).mockResolvedValue({ reactions: { like: 7, dislike: 2 } });
        const { result } = renderHookWithProviders(() => useComments("vid"));
        await waitFor(() => expect(result.current.comments).toHaveLength(1));

        act(() => result.current.reactToComment("r1", "like", "c1"));
        await waitFor(() => {
            expect(result.current.comments[0].replies?.[0]).toMatchObject({ likesCount: 7, dislikesCount: 2 });
        });
        // Parent untouched.
        expect(result.current.comments[0]).toMatchObject({ likesCount: 0, dislikesCount: 0 });
    });
});
