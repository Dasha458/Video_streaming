import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronUp } from "lucide-react";
import VideoPlayer from "@/components/VideoPlayer";
import { Avatar } from "@/components/common/Avatar";
import { useWatchSession } from "@/hooks/useWatchSession";
import { useFetchCategories } from "@/hooks/useCategories";
import { useVideo } from "@/hooks/useVideos";
import { useAuth } from "@/contexts/AuthContext";
import { useSidebar } from "@/components/ui/sidebar";
import { CommentsSection } from "./CommentsSection";
import { VideoActions } from "./VideoActions";
import { WatchSidebar } from "./WatchSidebar";

function WatchSkeleton() {
    return (
        <div className="flex flex-col lg:flex-row gap-6 p-4 animate-pulse">
            <div className="w-full lg:w-2/3 space-y-4">
                <div className="aspect-video rounded-xl bg-muted" />
                <div className="h-6 bg-muted rounded w-3/4" />
                <div className="h-4 bg-muted rounded w-1/2" />
            </div>
            <div className="w-full lg:w-[360px] space-y-4">
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex gap-2">
                        <div className="rounded-xl bg-muted shrink-0" style={{ width: 168, height: 94 }} />
                        <div className="flex-1 space-y-2 pt-1">
                            <div className="h-3 bg-muted rounded" />
                            <div className="h-3 bg-muted rounded w-2/3" />
                        </div>
                    </div>
                )) }
            </div>
        </div>
    );
}

export default function Watch() {
    const [searchParams] = useSearchParams();
    const videoId = searchParams.get("v") ?? "";

    const { categories, active, setActive } = useFetchCategories();
    const { user } = useAuth();
    const { setOpen } = useSidebar();

    const [showDesc, setShowDesc] = useState(false);

    // Collapse the nav sidebar on the watch page (YouTube-style)
    useEffect(() => {
        setOpen(false);
    }, [setOpen]);

    const { video, videos, error, loading, hasMore, loadMore, metaDataText, setVideo } = useVideo(active);

    // Watch-session heartbeat for creator analytics (watch time / retention).
    const videoElementRef = useRef<HTMLVideoElement>(null);
    useWatchSession(videoId || undefined, videoElementRef);

    if (error) return <p className="text-red-500 p-6">{error}</p>;
    if (loading || !video) return <WatchSkeleton />;

    return (
        <div className="flex flex-col lg:flex-row gap-6 p-4">
            <div className="w-full lg:flex-1 min-w-0">
                <div className="rounded-xl overflow-hidden bg-black">
                    <VideoPlayer ref={videoElementRef} src={video.hlsUrl} />
                </div>

                <h1 className="mt-3 text-lg sm:text-xl font-bold leading-snug">{video.title}</h1>

                <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
                    <Link
                        to={`/channel/${encodeURIComponent(video.channel)}`}
                        className="flex items-center gap-3 hover:opacity-80 transition-opacity"
                    >
                        <Avatar src={video.channel_avatar} name={video.channel} size={40} />
                        <div>
                            <p className="font-semibold text-sm leading-tight hover:underline">{video.channel}</p>
                            <p className="text-xs text-muted-foreground">{metaDataText}</p>
                        </div>
                    </Link>

                    <VideoActions
                        video={video}
                        videoId={videoId}
                        isSignedIn={Boolean(user)}
                        onVideoUpdate={setVideo}
                    />
                </div>

                <div
                    className="mt-3 rounded-xl bg-muted/50 hover:bg-muted/70 transition-colors p-3 cursor-pointer"
                    onClick={() => setShowDesc((v) => !v)}
                >
                    <p className={`text-sm ${showDesc ? "" : "line-clamp-2"} whitespace-pre-wrap`}>
                        {video.description || "No description."}
                    </p>
                    <button className="flex items-center gap-1 text-xs font-medium mt-1 text-muted-foreground">
                        {showDesc
                            ? <><ChevronUp className="h-3 w-3" />Show less</>
                            : <><ChevronDown className="h-3 w-3" />Show more</>}
                    </button>
                </div>

                <CommentsSection videoId={videoId} user={user} />
            </div>

            <WatchSidebar
                categories={categories}
                activeCategory={active}
                onCategoryChange={setActive}
                videos={videos}
                loading={loading}
                hasMore={hasMore}
                loadMore={loadMore}
            />
        </div>
    );
}
