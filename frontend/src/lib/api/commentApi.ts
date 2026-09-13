import type { VideoComment } from "./types";
import apiClient from "./clientApi";

/** Shape of backend src/schemas/comments.py's CommentRead -- always
 * snake_case, including recursively for `replies` (never a pre-mapped
 * camelCase object, so no camelCase fallback is needed here). Note there
 * is no video_id field -- comments are only ever fetched scoped to a
 * video, so the backend doesn't echo it back. */
interface RawComment {
    id: string;
    user_id: string;
    content: string;
    created_at: string;
    likes_count: number;
    dislikes_count: number;
    parent_id?: string | null;
    user_name: string;
    user_avatar?: string | null;
    replies?: RawComment[];
}

export const mapCommentFromApi = (c: RawComment): VideoComment => ({
    id: String(c.id),
    userId: String(c.user_id),
    content: c.content,
    createdAt: c.created_at,
    likesCount: c.likes_count,
    dislikesCount: c.dislikes_count,
    user_name: c.user_name,
    user_avatar: c.user_avatar ?? undefined,
    ...(Array.isArray(c.replies) ? { replies: c.replies.map(mapCommentFromApi) } : {}),
});

interface RawCommentPage {
    items: RawComment[];
    page: number;
    size: number;
    total: number;
}

export const getComments = async (
    videoId: string,
    page: number = 1,
    size: number = 20,
): Promise<RawCommentPage> => {
    const res = await apiClient.get<RawCommentPage>(`/api/comments/${videoId}`, {
        params: { page, size },
    });
    return res.data;
};

export const addComment = async (videoId: string, content: string): Promise<RawComment> => {
    const res = await apiClient.post<RawComment>(`/api/comments/${videoId}`, { content });
    return res.data;
};

export const deleteComment = async (commentId: string): Promise<void> => {
    await apiClient.delete(`/api/comments/${commentId}`);
};

export const addReply = async (
    videoId: string,
    commentId: string,
    content: string,
): Promise<RawComment> => {
    const res = await apiClient.post<RawComment>(`/api/comments/${videoId}`, {
        content,
        parent_id: commentId,
    });
    return res.data;
};

export const reactToComment = async (
    commentId: string,
    reactionName: "like" | "dislike",
): Promise<{ reactions: Record<string, number> }> => {
    const res = await apiClient.post(`/api/comments/${commentId}/reaction`, {
        reaction_name: reactionName,
    });
    return res.data;
};

export default { getComments, addComment, deleteComment, addReply, reactToComment };
