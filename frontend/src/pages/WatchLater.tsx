import { Link } from "react-router-dom";
import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import { Button } from "@/components/ui/button";
import { Clock } from "lucide-react";
import { getWatchLater, clearWatchLater, removeFromWatchLater } from "@api/watchLaterApi";
import { usePagedListQuery } from "@/hooks/queries/usePagedListQuery";

export default function WatchLater() {
    const {
        items: videos,
        isLoading: loading,
        hasMore,
        loadMore,
        refresh,
    } = usePagedListQuery("watch-later", getWatchLater);

    const handleRemove = async (videoId: string) => {
        try {
            await removeFromWatchLater(videoId);
            await refresh();
        } catch { /* ignore */ }
    };

    const handleClear = async () => {
        try {
            await clearWatchLater();
            await refresh();
        } catch { /* ignore */ }
    };

    return (
        <div className="px-4 py-4">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Watch later</h1>
                {videos.length > 0 && (
                    <Button variant="outline" size="sm" onClick={handleClear}>Clear all</Button>
                )}
            </div>

            {loading && videos.length === 0 ? (
                <div className="grid gap-x-4 gap-y-8 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 pb-10">
                    {Array.from({ length: 12 }).map((_, i) => <VideoCard key={i} loading />)}
                </div>
            ) : videos.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <Clock className="h-16 w-16 text-muted-foreground mb-4" />
                    <h2 className="text-lg font-semibold mb-1">No saved videos</h2>
                    <p className="text-sm text-muted-foreground">Videos you save will appear here.</p>
                </div>
            ) : (
                <div className="grid gap-x-4 gap-y-8 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 pb-10">
                    <InfiniteScroll loadMore={loadMore} hasMore={Boolean(hasMore)}>
                        {videos.map((video) => (
                            <div key={video.id} className="relative w-full">
                                <Link to={`/watch?v=${video.id}`} className="w-full block">
                                    <VideoCard
                                        id={video.id}
                                        title={video.title}
                                        thumbnail={video.previewUrl || ""}
                                        channel_avatar={video.channel_avatar || ""}
                                        channel_name={video.channel}
                                    />
                                </Link>
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                                    onClick={() => handleRemove(video.id)}
                                >
                                    Remove
                                </Button>
                            </div>
                        ))}
                    </InfiniteScroll>
                </div>
            )}
        </div>
    );
}
