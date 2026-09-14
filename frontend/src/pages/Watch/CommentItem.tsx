import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/common/Avatar";
import { timeAgo } from "@/utils/timeAgo";
import type { VideoComment } from "@api/types";

interface CommentActions {
    onReact: (id: string, reaction: "like" | "dislike", parentId?: string) => void;
    onDelete: (id: string, parentId?: string) => void;
}

interface CurrentUser {
    id: string;
    username: string;
}

interface CommentItemProps extends CommentActions {
    comment: VideoComment;
    user: CurrentUser | null;
    onReply: (parentId: string, content: string) => Promise<unknown>;
    isReplying: boolean;
}

/** A reply: same shape as a comment, minus its own reply box. */
function Reply({
    reply,
    parentId,
    user,
    onReact,
    onDelete,
}: CommentActions & { reply: VideoComment; parentId: string; user: CurrentUser | null }) {
    const name = reply.user_name || reply.userId;
    const isOwn = user && user.id === reply.userId;

    return (
        <div className="flex gap-2 pl-2">
            <Avatar src={reply.user_avatar} name={name} size={28} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-semibold">{name}</span>
                    <span className="text-xs text-muted-foreground">{timeAgo(reply.createdAt)}</span>
                </div>
                <p className="text-sm">{reply.content}</p>
                <div className="flex items-center gap-3 mt-1">
                    <button
                        onClick={() => onReact(reply.id, "like", parentId)}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <ThumbsUp className="h-3 w-3" /><span>{reply.likesCount}</span>
                    </button>
                    <button
                        onClick={() => onReact(reply.id, "dislike", parentId)}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <ThumbsDown className="h-3 w-3" /><span>{reply.dislikesCount}</span>
                    </button>
                    {isOwn && (
                        <button
                            onClick={() => onDelete(reply.id, parentId)}
                            className="text-xs text-red-400 hover:text-red-600 transition-colors"
                        >
                            Delete
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

export function CommentItem({
    comment,
    user,
    onReact,
    onDelete,
    onReply,
    isReplying,
}: CommentItemProps) {
    const [replyOpen, setReplyOpen] = useState(false);
    const [replyText, setReplyText] = useState("");

    const replies = comment.replies ?? [];
    const displayName = comment.user_name || comment.userId;
    const isOwn = user && user.id === comment.userId;

    const submitReply = async (e: React.FormEvent) => {
        e.preventDefault();
        const text = replyText.trim();
        if (!text) return;
        await onReply(comment.id, text);
        setReplyText("");
        setReplyOpen(false);
    };

    return (
        <div className="flex gap-3">
            <Avatar src={comment.user_avatar} name={displayName} size={36} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-semibold">{displayName}</span>
                    <span className="text-xs text-muted-foreground">{timeAgo(comment.createdAt)}</span>
                </div>
                <p className="text-sm">{comment.content}</p>

                <div className="flex items-center gap-3 mt-1">
                    <button
                        onClick={() => onReact(comment.id, "like")}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <ThumbsUp className="h-3.5 w-3.5" /><span>{comment.likesCount}</span>
                    </button>
                    <button
                        onClick={() => onReact(comment.id, "dislike")}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <ThumbsDown className="h-3.5 w-3.5" /><span>{comment.dislikesCount}</span>
                    </button>
                    {user && (
                        <button
                            onClick={() => { setReplyOpen((v) => !v); setReplyText(""); }}
                            className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            Reply
                        </button>
                    )}
                    {isOwn && (
                        <button
                            onClick={() => onDelete(comment.id)}
                            className="text-xs text-red-400 hover:text-red-600 transition-colors"
                        >
                            Delete
                        </button>
                    )}
                </div>

                {replyOpen && (
                    <form onSubmit={submitReply} className="flex gap-2 mt-3">
                        <Avatar name={user?.username} size={28} />
                        <div className="flex-1">
                            <input
                                value={replyText}
                                onChange={(e) => setReplyText(e.target.value)}
                                placeholder={`Reply to ${displayName}…`}
                                className="w-full border-b border-border bg-transparent pb-1 text-sm focus:outline-none focus:border-foreground transition-colors placeholder:text-muted-foreground"
                            />
                            <div className="flex justify-end gap-2 mt-2">
                                <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={() => setReplyOpen(false)}>
                                    Cancel
                                </Button>
                                <Button type="submit" size="sm" className="rounded-full" disabled={isReplying || !replyText.trim()}>
                                    {isReplying ? "…" : "Reply"}
                                </Button>
                            </div>
                        </div>
                    </form>
                )}

                {replies.length > 0 && (
                    <div className="mt-3 space-y-3">
                        {replies.map((reply) => (
                            <Reply
                                key={reply.id}
                                reply={reply}
                                parentId={comment.id}
                                user={user}
                                onReact={onReact}
                                onDelete={onDelete}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
