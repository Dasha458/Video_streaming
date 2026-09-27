import {
    useInfiniteQuery,
    useMutation,
    useQueryClient,
    type InfiniteData,
} from "@tanstack/react-query";
import { toast } from "@/components/ui/toast/use-toast";
import { getApiErrorMessage } from "@/utils/apiError";
import {
    addComment as addCommentApi,
    addReply as addReplyApi,
    deleteComment as deleteCommentApi,
    getComments,
    mapCommentFromApi,
    reactToComment,
} from "@api/commentApi";
import type { VideoComment } from "@api/types";

const COMMENTS_PAGE_SIZE = 20;

/**
 * Comment thread for one video: the list plus every mutation the watch page
 * needs. These seven handlers used to live inline in Watch.tsx, each
 * hand-patching a local `comments` array (and each having to special-case
 * "is this a top-level comment or a reply?" on its own).
 */
export function useComments(videoId: string | undefined) {
    const queryClient = useQueryClient();
    const queryKey = ["comments", videoId];

    // Paged, not capped. This used to ask for a single page of 100 with no
    // way to go further, so the 101st comment on a video simply did not
    // exist as far as the page was concerned -- and nothing said so.
    const {
        data,
        isLoading,
        fetchNextPage,
        hasNextPage,
        isFetchingNextPage,
    } = useInfiniteQuery({
        queryKey,
        initialPageParam: 1,
        queryFn: async ({ pageParam }) => {
            const page = await getComments(videoId!, pageParam, COMMENTS_PAGE_SIZE);
            return {
                items: page.items.map(mapCommentFromApi),
                total: page.total,
            };
        },
        getNextPageParam: (last, all) => {
            const loaded = all.reduce((n, p) => n + p.items.length, 0);
            return loaded < last.total ? all.length + 1 : undefined;
        },
        enabled: Boolean(videoId),
    });

    const comments: VideoComment[] = data?.pages.flatMap((p) => p.items) ?? [];
    const total = data?.pages[0]?.total ?? comments.length;

    type Page = { items: VideoComment[]; total: number };

    /** Applies `updater` to every loaded page; used by the id-targeted edits. */
    const patch = (updater: (prev: VideoComment[]) => VideoComment[]) =>
        queryClient.setQueryData<InfiniteData<Page>>(queryKey, (prev) =>
            prev
                ? {
                      ...prev,
                      pages: prev.pages.map((p) => ({ ...p, items: updater(p.items) })),
                  }
                : prev,
        );

    /** A brand-new top-level comment goes to the head of the first page. */
    const prepend = (comment: VideoComment) =>
        queryClient.setQueryData<InfiniteData<Page>>(queryKey, (prev) =>
            prev
                ? {
                      ...prev,
                      pages: prev.pages.map((p, i) =>
                          i === 0
                              ? { items: [comment, ...p.items], total: p.total + 1 }
                              : p,
                      ),
                  }
                : prev,
        );

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
        onSuccess: (raw) => prepend({ ...mapCommentFromApi(raw), replies: [] }),
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
        onError: (err) =>
            toast({
                title: getApiErrorMessage(err, "Could not delete the comment"),
                variant: "destructive",
            }),
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
        onError: (err) =>
            toast({
                title: getApiErrorMessage(err, "Could not save the reaction"),
                variant: "destructive",
            }),
        onSuccess: (data, { id, parentId }) =>
            patchOne(id, parentId, (c) => ({
                ...c,
                likesCount: data.reactions["like"] ?? 0,
                dislikesCount: data.reactions["dislike"] ?? 0,
            })),
    });

    return {
        comments,
        total,
        isLoading,
        hasMore: Boolean(hasNextPage),
        loadMore: () => void fetchNextPage(),
        isLoadingMore: isFetchingNextPage,
        addComment: (content: string) => addComment.mutateAsync(content),
        isAddingComment: addComment.isPending,
        addReply: (parentId: string, content: string) => addReply.mutateAsync({ parentId, content }),
        isAddingReply: addReply.isPending,
        deleteComment: (id: string, parentId?: string) => removeComment.mutate({ id, parentId }),
        reactToComment: (id: string, reaction: "like" | "dislike", parentId?: string) =>
            react.mutate({ id, reaction, parentId }),
    };
}
