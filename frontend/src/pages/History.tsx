import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import { Link } from "react-router-dom";
import { getUserHistory, clearUserHistory, removeVideoFromHistory } from "@api/historyApi";
import { Button } from "@/components/ui/button";
import { usePagedListQuery } from "@/hooks/queries/usePagedListQuery";

export default function History() {
    const {
        items: videos,
        isLoading: loading,
        hasMore,
        loadMore,
        refresh,
    } = usePagedListQuery("history", getUserHistory);

    const handleRemoveVideo = async (videoId: string) => {
        try {
            await removeVideoFromHistory(videoId);
            await refresh();
        } catch { /* ignore */ }
    };

    const handleClearHistory = async () => {
        try {
            await clearUserHistory();
            await refresh();
        } catch { /* ignore */ }
    };

    return (
        <div className="px-4 py-4">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">History</h1>
                {videos.length > 0 && (
                    <Button variant="destructive" onClick={handleClearHistory}>Clear History</Button>
                )}
            </div>

            <div className="grid gap-x-4 gap-y-8 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 pb-10">
                {loading && videos.length === 0
                    ? Array.from({ length: 12 }).map((_, i) => <VideoCard key={i} loading />)
                    : (
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
                                        variant="destructive"
                                        className="absolute top-2 right-2"
                                        onClick={() => handleRemoveVideo(video.id)}
                                    >
                                        Remove
                                    </Button>
                                </div>
                            ))}
                        </InfiniteScroll>
                    )}
            </div>
        </div>
    );
}
