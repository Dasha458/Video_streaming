import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

interface VideoCardProps {
    id?: string;
    title?: string;
    thumbnail?: string;
    channel_avatar?: string;
    channel_name?: string;
    views?: number;
    timeAgo?: string;
    /** Optional "MM:SS" / "H:MM:SS" — rendered as the YouTube-style duration pill. */
    duration?: string;
    loading?: boolean;
    /** Render as a compact horizontal row (Watch sidebar). */
    horizontal?: boolean;
}

/** Formats raw view counts the way YouTube does: 1.2K / 3.4M. */
const formatViews = (views: number | undefined): string => {
    if (views === undefined) return "";
    if (views < 1000) return `${views} views`;
    if (views < 1_000_000) return `${(views / 1000).toFixed(1).replace(/\.0$/, "")}K views`;
    return `${(views / 1_000_000).toFixed(1).replace(/\.0$/, "")}M views`;
};

const Avatar = ({
    src,
    name,
    size,
}: {
    src?: string;
    name?: string;
    size: number;
}) => {
    const [imgError, setImgError] = useState(false);
    const initial = (name ?? "?").charAt(0).toUpperCase();

    if (src && !imgError) {
        return (
            <img
                src={src}
                alt={name}
                width={size}
                height={size}
                className="rounded-full object-cover shrink-0"
                style={{ width: size, height: size }}
                loading="lazy"
                decoding="async"
                onError={() => setImgError(true)}
            />
        );
    }
    return (
        <div
            className="rounded-full bg-muted flex items-center justify-center shrink-0 text-xs font-semibold text-muted-foreground"
            style={{ width: size, height: size }}
        >
            {initial}
        </div>
    );
};

/* ── Skeletons ─────────────────────────────────────────────────────────── */

function CardSkeleton({ horizontal }: { horizontal?: boolean }) {
    if (horizontal) {
        return (
            <div className="flex gap-2">
                <Skeleton
                    className="rounded-xl shrink-0"
                    style={{ width: 168, aspectRatio: "16 / 9" }}
                />
                <div className="flex-1 min-w-0 pt-1 space-y-2">
                    <Skeleton className="h-3.5 w-full" />
                    <Skeleton className="h-3 w-2/3" />
                    <Skeleton className="h-3 w-1/2" />
                </div>
            </div>
        );
    }
    return (
        <div className="flex flex-col w-full">
            <Skeleton
                className="w-full rounded-xl"
                style={{ aspectRatio: "16 / 9" }}
            />
            <div className="flex gap-3 pt-3">
                <Skeleton
                    className="rounded-full shrink-0"
                    style={{ width: 36, height: 36 }}
                />
                <div className="flex-1 min-w-0 space-y-2 pt-1">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-3 w-2/3" />
                    <Skeleton className="h-3 w-1/2" />
                </div>
            </div>
        </div>
    );
}

/* ── Card ──────────────────────────────────────────────────────────────── */

export default function VideoCard({
    title,
    thumbnail,
    channel_avatar,
    channel_name,
    views,
    timeAgo,
    duration,
    loading = false,
    horizontal = false,
}: VideoCardProps) {
    if (loading) return <CardSkeleton horizontal={horizontal} />;

    // Use \u00b7 escape (middle dot) to avoid raw-byte encoding issues.
    const meta = [formatViews(views), timeAgo].filter(Boolean).join(" \u00b7 ");

    /* ── Horizontal (Watch sidebar) ───────────────────────────────────── */
    if (horizontal) {
        return (
            <div className="flex gap-2 group">
                <div
                    className="relative shrink-0 rounded-xl overflow-hidden bg-muted"
                    style={{ width: 168, aspectRatio: "16 / 9" }}
                >
                    <img
                        src={thumbnail}
                        alt={title}
                        className="absolute inset-0 w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-200"
                        loading="lazy"
                        decoding="async"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                    />
                    {duration && (
                        <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 text-[10px] font-medium text-white">
                            {duration}
                        </span>
                    )}
                </div>
                <div className="flex-1 min-w-0 pt-0.5">
                    <p className="text-sm font-semibold line-clamp-2 leading-snug">
                        {title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1 truncate">
                        {channel_name}
                    </p>
                    {meta && (
                        <p className="text-xs text-muted-foreground truncate">{meta}</p>
                    )}
                </div>
            </div>
        );
    }

    /* ── Vertical (Home grid) — YouTube-style 16:9 thumbnail ──────────── */
    return (
        <div className="flex flex-col group cursor-pointer w-full">
            {/* Thumbnail — full rounded-xl, strict 16:9 aspect ratio */}
            <div
                className="relative w-full overflow-hidden rounded-xl bg-muted"
                style={{ aspectRatio: "16 / 9" }}
            >
                {thumbnail && (
                    <img
                        src={thumbnail}
                        alt={title}
                        className="absolute inset-0 w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-200"
                        loading="lazy"
                        decoding="async"
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                    />
                )}
                {duration && (
                    <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
                        {duration}
                    </span>
                )}
            </div>

            {/* Meta row — no fixed height; title may be 1 or 2 lines like YouTube */}
            <div className="flex gap-3 pt-3">
                <div className="pt-0.5 shrink-0">
                    <Avatar src={channel_avatar} name={channel_name} size={36} />
                </div>
                <div className="flex-1 min-w-0">
                    <h3 className="text-[15px] font-semibold leading-snug line-clamp-2">
                        {title}
                    </h3>
                    <p className="text-sm text-muted-foreground mt-1 truncate">
                        {channel_name}
                    </p>
                    {meta && (
                        <p className="text-sm text-muted-foreground truncate">{meta}</p>
                    )}
                </div>
            </div>
        </div>
    );
}
