import { useState } from "react";
import { Check, Clock, Download, Share2, ThumbsDown, ThumbsUp } from "lucide-react";
import { addToWatchLater } from "@api/watchLaterApi";
import { useDownload } from "@/hooks/useDownload";
import { useReactions } from "@/hooks/useReactions";
import { formatCount } from "@/utils/formatters";
import type { VideoDetail } from "@api/types";
import { PlaylistMenu } from "./PlaylistMenu";

const RESOLUTIONS = ["360p", "720p", "1080p"];

interface VideoActionsProps {
    video: VideoDetail;
    videoId: string;
    isSignedIn: boolean;
    onVideoUpdate: (video: VideoDetail) => void;
}

/** Like / dislike / share / watch-later / save / download row under the player. */
export function VideoActions({ video, videoId, isSignedIn, onVideoUpdate }: VideoActionsProps) {
    const [resolution, setResolution] = useState("720p");
    const [watchLaterDone, setWatchLaterDone] = useState(false);

    const { handleDownload } = useDownload({ video, resolution });
    const { handleReaction } = useReactions({
        initialVideo: video,
        initialUserReaction: null,
        onVideoUpdate,
    });

    const handleWatchLater = async () => {
        if (!videoId) return;
        try {
            await addToWatchLater(videoId);
            setWatchLaterDone(true);
        } catch { /* already added or error — ignore */ }
    };

    return (
        <div className="flex items-center gap-2 flex-wrap">
            {/* Like / Dislike pill */}
            <div className="flex items-center rounded-full bg-muted overflow-hidden divide-x divide-border">
                <button
                    onClick={() => handleReaction("like")}
                    className="flex items-center gap-1.5 px-4 py-2 hover:bg-muted/70 transition-colors text-sm font-medium"
                >
                    <ThumbsUp className="h-4 w-4" />
                    <span>{formatCount(video.likesCount ?? 0)}</span>
                </button>
                <button
                    onClick={() => handleReaction("dislike")}
                    className="flex items-center gap-1.5 px-4 py-2 hover:bg-muted/70 transition-colors text-sm font-medium"
                >
                    <ThumbsDown className="h-4 w-4" />
                    <span>{formatCount(video.dislikesCount ?? 0)}</span>
                </button>
            </div>

            <button
                className="flex items-center gap-1.5 rounded-full bg-muted px-4 py-2 text-sm font-medium hover:bg-muted/70 transition-colors"
                onClick={() => navigator.clipboard.writeText(window.location.href)}
            >
                <Share2 className="h-4 w-4" />
                Share
            </button>

            {isSignedIn && (
                <button
                    className="flex items-center gap-1.5 rounded-full bg-muted px-4 py-2 text-sm font-medium hover:bg-muted/70 transition-colors"
                    onClick={handleWatchLater}
                    disabled={watchLaterDone}
                >
                    {watchLaterDone ? <Check className="h-4 w-4 text-emerald-500" /> : <Clock className="h-4 w-4" />}
                    {watchLaterDone ? "Saved" : "Watch Later"}
                </button>
            )}

            {isSignedIn && <PlaylistMenu videoId={videoId} />}

            <div className="flex items-center gap-1 rounded-full bg-muted overflow-hidden">
                <button
                    onClick={() => handleDownload()}
                    className="flex items-center gap-1.5 px-4 py-2 hover:bg-muted/70 transition-colors text-sm font-medium"
                >
                    <Download className="h-4 w-4" />
                    Download
                </button>
                <select
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                    className="bg-transparent pr-2 py-2 text-sm focus:outline-none cursor-pointer"
                    aria-label="Download resolution"
                >
                    {RESOLUTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
            </div>
        </div>
    );
}
