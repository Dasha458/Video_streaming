import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/common/Avatar";
import { useComments } from "@/hooks/useComments";
import { CommentItem } from "./CommentItem";

interface CommentsSectionProps {
    videoId: string;
    user: { id: string; username: string } | null;
}

export function CommentsSection({ videoId, user }: CommentsSectionProps) {
    const {
        comments,
        addComment,
        isAddingComment,
        addReply,
        isAddingReply,
        deleteComment,
        reactToComment,
    } = useComments(videoId);

    const [commentText, setCommentText] = useState("");

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        const text = commentText.trim();
        if (!text) return;
        await addComment(text);
        setCommentText("");
    };

    return (
        <div className="mt-6">
            <h2 className="font-semibold text-base mb-4">{comments.length} Comments</h2>

            {user ? (
                <form onSubmit={submit} className="flex gap-3 mb-6">
                    <Avatar name={user.username} size={36} />
                    <div className="flex-1">
                        <input
                            value={commentText}
                            onChange={(e) => setCommentText(e.target.value)}
                            placeholder="Add a comment…"
                            className="w-full border-b border-border bg-transparent pb-1 text-sm focus:outline-none focus:border-foreground transition-colors placeholder:text-muted-foreground"
                        />
                        {commentText && (
                            <div className="flex justify-end gap-2 mt-2">
                                <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={() => setCommentText("")}>
                                    Cancel
                                </Button>
                                <Button type="submit" size="sm" className="rounded-full" disabled={isAddingComment || !commentText.trim()}>
                                    {isAddingComment ? "Posting…" : "Comment"}
                                </Button>
                            </div>
                        )}
                    </div>
                </form>
            ) : (
                <p className="text-sm text-muted-foreground mb-4">
                    <Link to="/login" className="text-blue-500 hover:underline">Sign in</Link> to leave a comment.
                </p>
            )}

            <div className="space-y-4">
                {comments.map((comment) => (
                    <CommentItem
                        key={comment.id}
                        comment={comment}
                        user={user}
                        onReact={reactToComment}
                        onDelete={deleteComment}
                        onReply={addReply}
                        isReplying={isAddingReply}
                    />
                ))}
                {comments.length === 0 && (
                    <p className="text-sm text-muted-foreground">No comments yet. Be the first!</p>
                )}
            </div>
        </div>
    );
}
