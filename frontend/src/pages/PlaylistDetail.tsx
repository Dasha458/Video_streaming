import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ListVideo, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import VideoCard from "@/components/VideoCard";
import { getPlaylist, deleteFromPlaylist, type PlaylistDetail } from "@api/playlistApi";
import type { VideoPreview } from "@api/types";
import { timeAgo } from "@/utils/timeAgo";

export default function PlaylistDetailPage() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [playlist, setPlaylist] = useState<PlaylistDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [removing, setRemoving] = useState<string | null>(null);

    useEffect(() => {
        if (!id) return;
        setLoading(true);
        getPlaylist(id)
            .then(setPlaylist)
            .catch(() => setError("Failed to load playlist"))
            .finally(() => setLoading(false));
    }, [id]);

    const handleRemove = async (videoId: string) => {
        if (!id) return;
        setRemoving(videoId);
        try {
            await deleteFromPlaylist(id, videoId);
            setPlaylist((prev) =>
                prev
                    ? { ...prev, items: prev.items.filter((v) => v.id !== videoId), total: prev.total - 1 }
                    : prev
            );
        } catch {
            // silent
        } finally {
            setRemoving(null);
        }
    };

    if (error) return <p className="p-6 text-red-500">{error}</p>;

    return (
        <div className="px-4 py-6 max-w-6xl mx-auto space-y-6">
            {/* Back */}
            <button
                onClick={() => navigate(-1)}
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
                <ArrowLeft className="h-4 w-4" /> Back
            </button>

            {/* Header */}
            {loading ? (
                <div className="space-y-2">
                    <Skeleton className="h-7 w-64" />
                    <Skeleton className="h-4 w-40" />
                </div>
            ) : playlist ? (
                <div>
                    <h1 className="text-2xl font-bold">{playlist.name}</h1>
                    {playlist.description && (
                        <p className="text-sm text-muted-foreground mt-1">{playlist.description}</p>
                    )}
                    <p className="text-xs text-muted-foreground mt-1">
                        {playlist.total} video{playlist.total !== 1 ? "s" : ""} · Created {timeAgo(playlist.created_at)}
                    </p>
                </div>
            ) : null}

            {/* Video list */}
            {loading ? (
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                    {Array.from({ length: 8 }).map((_, i) => (
                        <div key={i} className="animate-pulse space-y-2">
                            <div className="aspect-video rounded-xl bg-muted" />
                            <div className="h-4 bg-muted rounded w-3/4" />
                            <div className="h-3 bg-muted rounded w-1/2" />
                        </div>
                    ))}
                </div>
            ) : playlist && playlist.items.length > 0 ? (
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                    {playlist.items.map((video: VideoPreview) => (
                        <div key={video.id} className="group relative">
                            <Link to={`/watch?v=${video.id}`}>
                                <VideoCard
                                    id={video.id}
                                    title={video.title}
                                    thumbnail={video.thumbnail_url ?? video.previewUrl}
                                    channel_avatar={video.channel_avatar}
                                    channel_name={video.channel_name ?? video.channel}
                                    views={video.views}
                                    timeAgo={timeAgo(video.createdAt ?? video.publishedAt)}
                                />
                            </Link>
                            <Button
                                size="icon"
                                variant="destructive"
                                className="absolute top-2 right-2 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                                disabled={removing === video.id}
                                onClick={() => handleRemove(video.id)}
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <ListVideo className="h-16 w-16 text-muted-foreground mb-4" />
                    <h2 className="text-lg font-semibold mb-1">No videos yet</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                        Add videos to this playlist while browsing.
                    </p>
                    <Button asChild className="rounded-full">
                        <Link to="/">Browse videos</Link>
                    </Button>
                </div>
            )}
        </div>
    );
}
