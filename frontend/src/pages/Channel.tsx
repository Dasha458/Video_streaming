import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { Bell, Play, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import VideoCard from "@/components/VideoCard";
import InfiniteScroll from "@/components/infinite-scroll";
import type { ChannelInfo, VideoPreview } from "@api/types";
import channelApi from "@api/channelApi";
import videoApi from "@api/videoApi";
import { useAuth } from "@/contexts/AuthContext";
import { timeAgo } from "@/utils/timeAgo";

type Tab = "videos" | "about";

// ── Avatar with gradient fallback ──────────────────────────────────────────
function ChannelAvatar({ src, name, size }: { src?: string | null; name?: string; size: number }) {
    const initial = (name ?? "?").charAt(0).toUpperCase();
    if (src) {
        return (
            <img
                src={src}
                alt={name}
                width={size}
                height={size}
                className="rounded-full object-cover border-4 border-background"
                style={{ width: size, height: size }}
            />
        );
    }
    return (
        <div
            className="rounded-full border-4 border-background flex items-center justify-center font-bold text-white shrink-0"
            style={{
                width: size,
                height: size,
                fontSize: size * 0.38,
                background: "linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary)/0.6))",
            }}
        >
            {initial}
        </div>
    );
}

function formatSubs(n?: number) {
    if (!n) return "0 subscribers";
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M subscribers`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K subscribers`;
    return `${n} subscriber${n !== 1 ? "s" : ""}`;
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function Channel() {
    const { channel_name } = useParams<{ channel_name: string }>();
    const { user } = useAuth();

    const [channel, setChannel] = useState<ChannelInfo | null>(null);
    const [channelLoading, setChannelLoading] = useState(true);

    const [videos, setVideos] = useState<VideoPreview[]>([]);
    const [page, setPage] = useState(1);
    const [hasMore, setHasMore] = useState(true);
    const [videosLoading, setVideosLoading] = useState(false);

    const [subscribed, setSubscribed] = useState(false);
    const [subLoading, setSubLoading] = useState(false);

    const [activeTab, setActiveTab] = useState<Tab>("videos");

    // Load channel info
    useEffect(() => {
        if (!channel_name) return;
        setChannelLoading(true);
        setChannel(null);
        setVideos([]);
        setPage(1);
        setHasMore(true);
        setActiveTab("videos");

        channelApi
            .getChannelInfo(channel_name)
            .then((info) => {
                setChannel(info);
                setSubscribed(!!(info as any).isSubscribed);
            })
            .catch(console.error)
            .finally(() => setChannelLoading(false));
    }, [channel_name]);

    // Load videos with infinite scroll
    const loadMore = useCallback(async () => {
        if (videosLoading || !channel_name) return;
        setVideosLoading(true);
        try {
            const data = await videoApi.getVideos({ page, channel_name });
            if (!data || data.length === 0) { setHasMore(false); return; }
            setVideos((prev) => [...prev, ...data]);
            setPage((p) => p + 1);
        } catch (e) {
            console.error(e);
        } finally {
            setVideosLoading(false);
        }
    }, [page, videosLoading, channel_name]);

    useEffect(() => {
        if (channel_name) loadMore();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [channel_name]);

    // Subscribe / unsubscribe with optimistic counter update
    const handleSubscribe = async () => {
        if (!channel_name || !user) return;
        setSubLoading(true);
        const wasSubscribed = subscribed;
        try {
            if (subscribed) {
                await channelApi.unsubscribeFromChannel(channel_name);
                setSubscribed(false);
                setChannel((prev) =>
                    prev ? { ...prev, subscribersCount: Math.max(0, (prev.subscribersCount ?? 0) - 1) } : prev
                );
            } else {
                await channelApi.subscribeToChannel(channel_name);
                setSubscribed(true);
                setChannel((prev) =>
                    prev ? { ...prev, subscribersCount: (prev.subscribersCount ?? 0) + 1 } : prev
                );
            }
        } catch (e) {
            console.error(e);
            setSubscribed(wasSubscribed);
        } finally {
            setSubLoading(false);
        }
    };

    // Skeleton while loading
    if (channelLoading) {
        return (
            <div className="min-h-screen animate-pulse">
                <div className="w-full h-40 sm:h-52 bg-muted" />
                <div className="max-w-[1200px] mx-auto px-4 sm:px-6">
                    <div className="flex items-end gap-4 py-4 border-b border-border">
                        <Skeleton className="w-24 h-24 rounded-full -mt-12 shrink-0" />
                        <div className="flex-1 space-y-2 pb-2">
                            <Skeleton className="h-6 w-48" />
                            <Skeleton className="h-4 w-32" />
                        </div>
                        <Skeleton className="h-9 w-28 rounded-full" />
                    </div>
                </div>
            </div>
        );
    }

    if (!channel) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-muted-foreground">
                <p className="text-lg font-semibold">Channel not found</p>
                <Link to="/" className="text-sm underline">Go home</Link>
            </div>
        );
    }

    const isOwner = !!(channel as any).isOwner;
    const avatarSrc = channel.channel_avatar || (channel as any).avatar_path || null;
    const bannerSrc = channel.channelBanner || (channel as any).background_path || null;
    const bio = channel.bio || (channel as any).description || null;
    const subCount = channel.subscribersCount ?? (channel as any).subscribers_count ?? 0;
    const videoCount = channel.videosCount ?? 0;
    const joinedAt = channel.createdAt || (channel as any).created_at || null;

    const TABS: { id: Tab; label: string }[] = [
        { id: "videos", label: videoCount > 0 ? `Videos (${videoCount})` : "Videos" },
        { id: "about", label: "About" },
    ];

    return (
        <div className="min-h-screen">
            {/* Banner */}
            <div className="w-full h-36 sm:h-48 md:h-52 overflow-hidden bg-gradient-to-br from-primary/20 via-muted to-muted/60">
                {bannerSrc && (
                    <img src={bannerSrc} alt="Channel banner" className="w-full h-full object-cover" />
                )}
            </div>

            <div className="max-w-[1200px] mx-auto px-4 sm:px-6">
                {/* Channel header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4 py-4 border-b border-border">
                    <div className="-mt-12 sm:-mt-14 shrink-0">
                        <ChannelAvatar src={avatarSrc} name={channel.name} size={96} />
                    </div>

                    <div className="flex flex-1 flex-col sm:flex-row sm:items-center sm:justify-between gap-3 min-w-0">
                        <div className="min-w-0">
                            <h1 className="text-2xl sm:text-3xl font-bold truncate">{channel.name}</h1>
                            <p className="text-sm text-muted-foreground mt-0.5">
                                @{channel.name.toLowerCase().replace(/\s+/g, "")}
                                {" · "}{formatSubs(subCount)}
                                {videoCount > 0 && ` · ${videoCount} video${videoCount !== 1 ? "s" : ""}`}
                            </p>
                            {bio && (
                                <p className="text-sm text-muted-foreground mt-1 line-clamp-1 max-w-xl">{bio}</p>
                            )}
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-2 shrink-0">
                            {isOwner ? (
                                <>
                                    <Button asChild variant="outline" className="rounded-full gap-1.5">
                                        <Link to="/upload">
                                            <Upload className="h-4 w-4" />
                                            Upload
                                        </Link>
                                    </Button>
                                    <Button asChild variant="outline" className="rounded-full gap-1.5">
                                        <Link to="/studio">
                                            <Play className="h-4 w-4" />
                                            Studio
                                        </Link>
                                    </Button>
                                </>
                            ) : user ? (
                                <div className="flex items-center gap-1.5">
                                    <Button
                                        className={`rounded-full px-5 ${subscribed ? "bg-muted text-foreground hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400" : ""}`}
                                        variant={subscribed ? "outline" : "default"}
                                        onClick={handleSubscribe}
                                        disabled={subLoading}
                                    >
                                        {subLoading ? "…" : subscribed ? "Subscribed" : "Subscribe"}
                                    </Button>
                                    {subscribed && (
                                        <Button
                                            size="icon"
                                            variant="outline"
                                            className="rounded-full"
                                            title="Manage notifications"
                                        >
                                            <Bell className="h-4 w-4" />
                                        </Button>
                                    )}
                                </div>
                            ) : (
                                <Button asChild className="rounded-full px-5">
                                    <Link to="/login">Subscribe</Link>
                                </Button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Tab bar */}
                <div className="flex border-b border-border mt-0 -mb-px">
                    {TABS.map((t) => (
                        <button
                            key={t.id}
                            onClick={() => setActiveTab(t.id)}
                            className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
                                activeTab === t.id
                                    ? "border-foreground text-foreground"
                                    : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* Videos tab */}
                {activeTab === "videos" && (
                    <div className="mt-6">
                        {videos.length === 0 && !videosLoading ? (
                            <div className="flex flex-col items-center justify-center py-20 gap-3 text-muted-foreground">
                                <Play className="h-12 w-12 opacity-20" />
                                <p className="text-base">No videos yet.</p>
                                {isOwner && (
                                    <Button asChild className="mt-2 rounded-full">
                                        <Link to="/upload">Upload your first video</Link>
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <InfiniteScroll loadMore={loadMore} hasMore={hasMore}>
                                <div className="grid gap-x-4 gap-y-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                                    {videos.map((v) => (
                                        <Link key={v.id} to={`/watch?v=${v.id}`}>
                                            <VideoCard
                                                id={v.id}
                                                title={v.title || (v as any).name || "Untitled"}
                                                thumbnail={v.previewUrl || v.thumbnail_url}
                                                channel_name={channel.name}
                                                channel_avatar={avatarSrc ?? undefined}
                                                views={v.views}
                                                timeAgo={
                                                    v.createdAt
                                                        ? timeAgo(v.createdAt)
                                                        : v.publishedAt
                                                        ? timeAgo(v.publishedAt)
                                                        : undefined
                                                }
                                            />
                                        </Link>
                                    ))}
                                    {videosLoading &&
                                        Array.from({ length: 4 }).map((_, i) => <VideoCard key={i} loading />)}
                                </div>
                            </InfiniteScroll>
                        )}
                    </div>
                )}

                {/* About tab */}
                {activeTab === "about" && (
                    <div className="mt-6 max-w-2xl space-y-8">
                        <section>
                            <h2 className="text-base font-semibold mb-3">Description</h2>
                            {bio ? (
                                <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">{bio}</p>
                            ) : (
                                <p className="text-sm text-muted-foreground italic">No description provided.</p>
                            )}
                        </section>

                        <section>
                            <h2 className="text-base font-semibold mb-3">Stats</h2>
                            <div className="text-sm text-muted-foreground space-y-1.5">
                                {joinedAt && <p>Joined {timeAgo(joinedAt)}</p>}
                                <p>{formatSubs(subCount)}</p>
                                {videoCount > 0 && <p>{videoCount} video{videoCount !== 1 ? "s" : ""}</p>}
                            </div>
                        </section>
                    </div>
                )}
            </div>
        </div>
    );
}
