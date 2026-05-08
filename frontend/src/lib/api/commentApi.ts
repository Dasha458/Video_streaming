import type { Comment, CommentPage, VideoComment } from "./types";
import apiClient from "./clientApi";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const mapCommentFromApi = (c: any): VideoComment => ({
    id: String(c.id),
    userId: String(c.user_id ?? c.userId ?? ""),
    content: c.content,
    createdAt: c.created_at ?? c.createdAt ?? "",
    videoId: c.video_id ?? c.videoId ?? "",
    likesCount: c.likes_count ?? c.likesCount ?? 0,
    dislikesCount: c.dislikes_count ?? c.dislikesCount ?? 0,
    user_name: c.user_name,
    user_avatar: c.user_avatar,
    ...(Array.isArray(c.replies) ? { replies: c.replies.map(mapCommentFromApi) } : {}),
});

export const getComments = async (
    videoId: string,
    page: number = 1,
    size: number = 20,
): Promise<CommentPage> => {
    const res = await apiClient.get<CommentPage>(`/api/comments/${videoId}`, {
        params: { page, size },
    });
    return res.data;
};

export const addComment = async (videoId: string, content: string): Promise<Comment> => {
    const res = await apiClient.post<Comment>(`/api/comments/${videoId}`, { content });
    return res.data;
};

export const deleteComment = async (commentId: string): Promise<void> => {
    await apiClient.delete(`/api/comments/${commentId}`);
};

export const addReply = async (
    videoId: string,
    commentId: string,
    content: string,
): Promise<Comment> => {
    const res = await apiClient.post<Comment>(`/api/comments/${videoId}`, {
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
