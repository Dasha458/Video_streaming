import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    addComment as addCommentApi,
    addReply as addReplyApi,
    deleteComment as deleteCommentApi,
    getComments,
    mapCommentFromApi,
    reactToComment,
} from "@api/commentApi";
import type { VideoComment } from "@api/types";

const COMMENTS_PAGE_SIZE = 100;

/**
 * Comment thread for one video: the list plus every mutation the watch page
 * needs. These seven handlers used to live inline in Watch.tsx, each
 * hand-patching a local `comments` array (and each having to special-case
 * "is this a top-level comment or a reply?" on its own).
 */
export function useComments(videoId: string | undefined) {
    const queryClient = useQueryClient();
    const queryKey = ["comments", videoId];

    const { data: comments = [], isLoading } = useQuery({
        queryKey,
        queryFn: async () => {
            const page = await getComments(videoId!, 1, COMMENTS_PAGE_SIZE);
            return page.items.map(mapCommentFromApi);
        },
        enabled: Boolean(videoId),
    });

    const patch = (updater: (prev: VideoComment[]) => VideoComment[]) =>
        queryClient.setQueryData<VideoComment[]>(queryKey, (prev) => updater(prev ?? []));

    /** Applies `update` to a top-level comment, or to a reply inside `parentId`. */
    const patchOne = (
        id: string,
        parentId: string | undefined,
        update: (c: VideoComment) => VideoComment,
    ) =>
        patch((prev) =>
            parentId
                ? prev.map((c) =>
                      c.id === parentId
                          ? { ...c, replies: (c.replies ?? []).map((r) => (r.id === id ? update(r) : r)) }
                          : c,
                  )
                : prev.map((c) => (c.id === id ? update(c) : c)),
        );

    const addComment = useMutation({
        mutationFn: (content: string) => addCommentApi(videoId!, content),
        onSuccess: (raw) =>
            patch((prev) => [{ ...mapCommentFromApi(raw), replies: [] }, ...prev]),
    });

    const addReply = useMutation({
        mutationFn: ({ parentId, content }: { parentId: string; content: string }) =>
            addReplyApi(videoId!, parentId, content).then((raw) => ({ parentId, raw })),
        onSuccess: ({ parentId, raw }) =>
            patch((prev) =>
                prev.map((c) =>
                    c.id === parentId
                        ? { ...c, replies: [...(c.replies ?? []), mapCommentFromApi(raw)] }
                        : c,
                ),
            ),
    });

    const removeComment = useMutation({
        mutationFn: ({ id }: { id: string; parentId?: string }) => deleteCommentApi(id),
        onSuccess: (_, { id, parentId }) =>
            patch((prev) =>
                parentId
                    ? prev.map((c) =>
                          c.id === parentId
                              ? { ...c, replies: (c.replies ?? []).filter((r) => r.id !== id) }
                              : c,
                      )
                    : prev.filter((c) => c.id !== id),
            ),
    });

    const react = useMutation({
        mutationFn: ({ id, reaction }: { id: string; reaction: "like" | "dislike"; parentId?: string }) =>
            reactToComment(id, reaction),
        onSuccess: (data, { id, parentId }) =>
            patchOne(id, parentId, (c) => ({
                ...c,
                likesCount: data.reactions["like"] ?? 0,
                dislikesCount: data.reactions["dislike"] ?? 0,
            })),
    });

    return {
        comments,
        isLoading,
        addComment: (content: string) => addComment.mutateAsync(content),
        isAddingComment: addComment.isPending,
        addReply: (parentId: string, content: string) => addReply.mutateAsync({ parentId, content }),
        isAddingReply: addReply.isPending,
        deleteComment: (id: string, parentId?: string) => removeComment.mutate({ id, parentId }),
        reactToComment: (id: string, reaction: "like" | "dislike", parentId?: string) =>
            react.mutate({ id, reaction, parentId }),
    };
}
