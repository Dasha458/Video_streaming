import { Link } from "react-router-dom";
import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import { ThumbsUp } from "lucide-react";
import { getLikedVideos } from "@api/likedApi";
import { usePagedList } from "@/hooks/usePagedList";

export default function Liked() {
    const { items: videos, loading, hasMore, loadMore } = usePagedList(getLikedVideos);

    return (
        <div className="px-4 py-4">
            <h1 className="text-2xl font-bold mb-6">Liked videos</h1>

            {loading && videos.length === 0 ? (
                <div className="grid gap-x-4 gap-y-8 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 pb-10">
                    {Array.from({ length: 12 }).map((_, i) => <VideoCard key={i} loading />)}
                </div>
            ) : videos.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <ThumbsUp className="h-16 w-16 text-muted-foreground mb-4" />
                    <h2 className="text-lg font-semibold mb-1">No liked videos</h2>
                    <p className="text-sm text-muted-foreground">Videos you like will appear here.</p>
                </div>
            ) : (
                <div className="grid gap-x-4 gap-y-8 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 pb-10">
                    <InfiniteScroll loadMore={loadMore} hasMore={hasMore}>
                        {videos.map((video) => (
                            <Link key={video.id} to={`/watch?v=${video.id}`} className="w-full">
                                <VideoCard
                                    id={video.id}
                                    title={video.title}
                                    thumbnail={video.previewUrl || ""}
                                    channel_avatar={video.channel_avatar || ""}
                                    channel_name={video.channel}
                                />
                            </Link>
                        ))}
                    </InfiniteScroll>
                </div>
            )}
        </div>
    );
}
