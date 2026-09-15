import { Link } from "react-router-dom";
import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import type { VideoPreviewWithTime } from "@api/types";

interface WatchSidebarProps {
    categories: string[];
    activeCategory: string;
    onCategoryChange: (category: string) => void;
    videos: VideoPreviewWithTime[];
    loading: boolean;
    hasMore: boolean;
    loadMore: () => void;
}

/** Category pills + the "up next" list beside the player. */
export function WatchSidebar({
    categories,
    activeCategory,
    onCategoryChange,
    videos,
    loading,
    hasMore,
    loadMore,
}: WatchSidebarProps) {
    return (
        <div className="w-full lg:w-[360px] xl:w-[400px] shrink-0">
            <div className="flex gap-2 overflow-x-auto no-scrollbar pb-3 mb-3">
                {categories.map((cat) => (
                    <button
                        key={cat}
                        onClick={() => onCategoryChange(cat)}
                        className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors shrink-0
                            ${activeCategory === cat ? "bg-foreground text-background" : "bg-muted hover:bg-muted/80"}`}
                    >
                        {cat}
                    </button>
                ))}
            </div>

            <InfiniteScroll loadMore={loadMore} hasMore={hasMore}>
                <div className="flex flex-col gap-4">
                    {videos.map((v) => (
                        <Link key={v.id} to={`/watch?v=${v.id}`} className="block">
                            <VideoCard
                                id={v.id}
                                title={v.title}
                                thumbnail={v.previewUrl || v.thumbnail_url}
                                channel_avatar={v.channel_avatar}
                                channel_name={v.channel_name}
                                views={v.views}
                                timeAgo={v.timeAgo}
                                horizontal
                            />
                        </Link>
                    ))}
                    {loading && Array.from({ length: 5 }).map((_, i) => <VideoCard key={i} loading horizontal />)}
                </div>
            </InfiniteScroll>
        </div>
    );
}
