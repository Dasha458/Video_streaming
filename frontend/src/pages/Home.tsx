import React, { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import categoriesApi from "@api/categoriesApi";
import type { Category } from "@api/types";
import { formatCategoryName } from "@/utils/formatters";
import { useVideosQuery, VIDEOS_PAGE_SIZE } from "@/hooks/queries/useVideosQuery";

export default function Home() {
    const [categories, setCategories] = useState<Category[]>([]);
    const [activeCategory, setActiveCategory] = useState<string>("All");
    const pillsRef = useRef<HTMLDivElement>(null);

    const { videos, isLoading, isFetchingNextPage, hasMore, loadMore, error } = useVideosQuery({
        category: activeCategory,
    });

    useEffect(() => {
        categoriesApi
            .getCategories()
            .then((data) => setCategories([{ id: "all", name: "All" }, ...data]))
            .catch(console.error);
    }, []);

    /* drag-scroll pills */
    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        const el = e.currentTarget;
        const startX = e.pageX - el.offsetLeft;
        const scrollLeft = el.scrollLeft;
        const onMove = (ev: MouseEvent) => { el.scrollLeft = scrollLeft - (ev.pageX - el.offsetLeft - startX) * 1.2; };
        const onUp = () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    };

    return (
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6">
            {/* Category pills — NOT sticky, scrolls with page */}
            <div
                ref={pillsRef}
                className="flex gap-3 overflow-x-auto no-scrollbar py-3 cursor-grab active:cursor-grabbing select-none"
                onMouseDown={handleMouseDown}
            >
                {categories.map((cat) => (
                    <button
                        key={cat.id}
                        onClick={() => setActiveCategory(cat.name)}
                        className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors shrink-0
                            ${activeCategory === cat.name
                                ? "bg-foreground text-background"
                                : "bg-muted hover:bg-muted/80 text-foreground"
                            }`}
                    >
                        {cat.name === "All" ? "All" : formatCategoryName(cat.name)}
                    </button>
                ))}
            </div>

            {/* Video grid — YouTube-style: max 4 cols on xl, wider cards */}
            <div className="grid gap-x-4 gap-y-10 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 pb-10">
                {videos.length === 0 && error ? (
                    <div className="col-span-full flex flex-col items-center justify-center py-20 gap-2 text-muted-foreground">
                        <p className="text-base font-medium text-foreground">Couldn't load videos</p>
                        <p className="text-sm">Check your connection and try again.</p>
                    </div>
                ) : videos.length === 0 && isLoading ? (
                    Array.from({ length: VIDEOS_PAGE_SIZE }).map((_, i) => <VideoCard key={i} loading />)
                ) : (
                    <InfiniteScroll loadMore={loadMore} hasMore={Boolean(hasMore)}>
                        {videos.map((video) => (
                            <Link key={video.id} to={`/watch?v=${video.id}`}>
                                <VideoCard
                                    id={video.id}
                                    title={video.title || "Untitled"}
                                    thumbnail={video.previewUrl || "/placeholder.jpg"}
                                    channel_avatar={video.channel_avatar}
                                    channel_name={video.channel_name || video.channel}
                                    views={video.views}
                                    timeAgo={video.timeAgo}
                                />
                            </Link>
                        ))}
                        {isFetchingNextPage && (
                            <>
                                {Array.from({ length: 4 }).map((_, i) => <VideoCard key={`sk-${i}`} loading />)}
                            </>
                        )}
                    </InfiniteScroll>
                )}
            </div>
        </div>
    );
}
