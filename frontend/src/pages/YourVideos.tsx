import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
    Eye, ThumbsUp, MessageSquare, MoreVertical, Search,
    BarChart2, Globe, Lock, Trash2, Play,
} from "lucide-react";
import { timeAgo } from "@/utils/timeAgo";
import videoApi from "@api/videoApi";
import type { VideoPreview } from "@api/types";
import { toast } from "@/components/ui/toast/use-toast";

type StatusFilter = "all" | "public" | "private" | "processing";

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
    Ready:      { label: "Published",  color: "text-green-500" },
    Processing: { label: "Processing", color: "text-yellow-500" },
    Failed:     { label: "Failed",     color: "text-red-500" },
    Queued:     { label: "Processing", color: "text-yellow-500" },
};

function VideoMenu({ video, onPrivacyChange, onDelete }: {
    video: VideoPreview;
    onPrivacyChange: (id: string, isPublic: boolean) => void;
    onDelete: (id: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();

    useEffect(() => {
        if (!open) return;
        function handle(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener("mousedown", handle);
        return () => document.removeEventListener("mousedown", handle);
    }, [open]);

    const isPublic = (video.privacy ?? "public").toLowerCase() === "public";

    const actions = [
        {
            icon: <Play className="h-4 w-4" />,
            label: "Watch",
            onClick: () => navigate(`/watch?v=${video.id}`),
        },
        {
            icon: <BarChart2 className="h-4 w-4" />,
            label: "Analytics",
            onClick: () => navigate(`/studio/video/${video.id}`),
        },
        {
            icon: isPublic ? <Lock className="h-4 w-4" /> : <Globe className="h-4 w-4" />,
            label: isPublic ? "Make private" : "Make public",
            onClick: async () => {
                try {
                    await videoApi.updateVideoPrivacy(video.id, !isPublic);
                    onPrivacyChange(video.id, !isPublic);
                    toast({ title: isPublic ? "Video set to private" : "Video set to public" });
                } catch {
                    toast({ title: "Failed to update privacy", variant: "destructive" });
                }
                setOpen(false);
            },
        },
        {
            icon: <Trash2 className="h-4 w-4 text-destructive" />,
            label: <span className="text-destructive">Delete</span>,
            onClick: async () => {
                if (!confirm("Delete this video? This cannot be undone.")) return;
                try {
                    await videoApi.deleteVideo(video.id);
                    onDelete(video.id);
                    toast({ title: "Video deleted" });
                } catch {
                    toast({ title: "Failed to delete video", variant: "destructive" });
                }
                setOpen(false);
            },
        },
    ];

    return (
        <div ref={ref} className="relative shrink-0">
            <button
                onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }}
                className="p-1.5 rounded-full hover:bg-muted transition-colors opacity-0 group-hover:opacity-100"
            >
                <MoreVertical className="h-4 w-4 text-muted-foreground" />
            </button>

            {open && (
                <div className="absolute right-0 top-8 z-50 min-w-[170px] rounded-md border bg-popover shadow-md py-1">
                    {actions.map((a, i) => (
                        <button
                            key={i}
                            onClick={a.onClick}
                            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-muted transition-colors text-left"
                        >
                            {a.icon}
                            {a.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

export default function YourVideos() {
    const [videos, setVideos] = useState<VideoPreview[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<StatusFilter>("all");
    const [search, setSearch] = useState("");

    useEffect(() => {
        videoApi.getVideos({ page: 1, size: 50 })
            .then(setVideos)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, []);

    const handlePrivacyChange = (id: string, isPublic: boolean) => {
        setVideos((prev) =>
            prev.map((v) => v.id === id ? { ...v, privacy: isPublic ? "public" : "private" } : v)
        );
    };

    const handleDelete = (id: string) => {
        setVideos((prev) => prev.filter((v) => v.id !== id));
    };

    const filtered = videos.filter((v) => {
        const matchSearch = (v.title ?? "").toLowerCase().includes(search.toLowerCase());
        const privacy = (v.privacy ?? "public").toLowerCase();
        const matchFilter =
            filter === "all"        ? true :
            filter === "public"     ? privacy === "public" :
            filter === "private"    ? privacy === "private" :
            false;
        return matchSearch && matchFilter;
    });

    const tabs: { key: StatusFilter; label: string }[] = [
        { key: "all",        label: "All" },
        { key: "public",     label: "Public" },
        { key: "private",    label: "Private" },
        { key: "processing", label: "Processing" },
    ];

    return (
        <div className="px-4 py-6">
            <h1 className="text-2xl font-bold mb-6">Your videos</h1>

            {/* Tabs */}
            <div className="flex gap-1 mb-4 border-b border-border">
                {tabs.map((t) => (
                    <button
                        key={t.key}
                        onClick={() => setFilter(t.key)}
                        className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                            filter === t.key
                                ? "border-foreground text-foreground"
                                : "border-transparent text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Search */}
            <div className="relative mb-4 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search your videos"
                    className="w-full pl-9 pr-4 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                />
            </div>

            {/* List */}
            {loading ? (
                <div className="space-y-3">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div key={i} className="flex gap-4 animate-pulse">
                            <div className="rounded-xl bg-muted shrink-0" style={{ width: 160, height: 90 }} />
                            <div className="flex-1 space-y-2 pt-2">
                                <div className="h-4 bg-muted rounded w-1/2" />
                                <div className="h-3 bg-muted rounded w-1/4" />
                            </div>
                        </div>
                    ))}
                </div>
            ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <h2 className="text-lg font-semibold mb-1">No videos found</h2>
                    <p className="text-sm text-muted-foreground">
                        {search ? "Try a different search term." : "Upload a video to get started."}
                    </p>
                </div>
            ) : (
                <div className="divide-y divide-border">
                    {filtered.map((v) => {
                        const statusKey = (v as any).status ?? "Ready";
                        const status = STATUS_LABEL[statusKey] ?? { label: statusKey, color: "text-muted-foreground" };
                        return (
                            <div key={v.id} className="flex gap-4 py-3 group">
                                {/* Thumbnail */}
                                <Link to={`/watch?v=${v.id}`} className="shrink-0">
                                    <div className="relative rounded-xl overflow-hidden bg-muted" style={{ width: 160, height: 90 }}>
                                        <img
                                            src={v.thumbnail_url || (v as any).previewUrl || ""}
                                            alt={v.title}
                                            className="w-full h-full object-cover"
                                            loading="lazy"
                                        />
                                    </div>
                                </Link>

                                {/* Info */}
                                <div className="flex-1 min-w-0">
                                    <Link to={`/watch?v=${v.id}`}>
                                        <h3 className="font-semibold text-sm line-clamp-2 hover:underline leading-snug">
                                            {v.title}
                                        </h3>
                                    </Link>
                                    <p className={`text-xs mt-0.5 font-medium ${status.color}`}>{status.label}</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {v.createdAt ? timeAgo(v.createdAt) : ""}
                                    </p>
                                </div>

                                {/* Stats */}
                                <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground shrink-0">
                                    <div className="flex items-center gap-1.5 w-20">
                                        <Eye className="h-4 w-4" />
                                        <span>{(v.views ?? 0).toLocaleString()}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 w-20">
                                        <ThumbsUp className="h-4 w-4" />
                                        <span>{(v.likesCount ?? 0).toLocaleString()}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 w-20">
                                        <MessageSquare className="h-4 w-4" />
                                        <span>{((v as any).commentCount ?? 0).toLocaleString()}</span>
                                    </div>
                                </div>

                                {/* Three-dot menu */}
                                <VideoMenu
                                    video={v}
                                    onPrivacyChange={handlePrivacyChange}
                                    onDelete={handleDelete}
                                />
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
