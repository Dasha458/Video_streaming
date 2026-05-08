import { useEffect, useRef } from "react";
import { beaconWatchSession, sendWatchSession } from "@/lib/api/analyticsApi";

/**
 * Tracks playback progress for creator-analytics watch-time / retention.
 *
 *   * A stable v4 ``session_id`` is generated once per mount.
 *   * While the video is playing the watched-seconds counter increments
 *     locally and a heartbeat is POSTed every ~10 seconds.
 *   * On tab close / component unmount we fire a final ``sendBeacon`` so
 *     the server gets the last cursor even after the page is gone.
 *
 * The "source" tag is derived from ``document.referrer`` the first time
 * the hook runs on this page-load; callers can override by passing
 * ``sourceOverride``.
 */
export function useWatchSession(
    videoId: string | undefined,
    videoElementRef: React.RefObject<HTMLVideoElement | null>,
    sourceOverride?: string,
) {
    const sessionIdRef = useRef<string>("");
    const watchedRef = useRef<number>(0);
    const lastTickRef = useRef<number | null>(null);
    const durationRef = useRef<number>(0);
    const sentOnceRef = useRef<boolean>(false);

    // Derive a source tag from the referrer once per mount.
    const sourceRef = useRef<string | undefined>(undefined);
    if (sourceRef.current === undefined) {
        sourceRef.current = sourceOverride ?? inferSource();
    }

    // Fresh session id on every new videoId.
    useEffect(() => {
        if (!videoId) return;
        sessionIdRef.current = cryptoUUID();
        watchedRef.current = 0;
        lastTickRef.current = null;
        sentOnceRef.current = false;
    }, [videoId]);

    // Attach player listeners + periodic heartbeat.
    useEffect(() => {
        if (!videoId) return;
        const el = videoElementRef.current;
        if (!el) return;

        const onPlay = () => { lastTickRef.current = performance.now(); };
        const onPauseOrEnded = () => {
            accumulate();
            flush();
        };
        const onLoaded = () => {
            durationRef.current = Math.max(0, Math.floor(el.duration || 0));
        };
        const onTimeUpdate = () => {
            // every video timeupdate we accumulate wallclock delta when playing.
            if (!el.paused && !el.ended) accumulate();
        };

        el.addEventListener("play", onPlay);
        el.addEventListener("pause", onPauseOrEnded);
        el.addEventListener("ended", onPauseOrEnded);
        el.addEventListener("loadedmetadata", onLoaded);
        el.addEventListener("timeupdate", onTimeUpdate);

        // Periodic heartbeat (10s).
        const heartbeat = setInterval(() => {
            if (!el.paused && !el.ended) accumulate();
            flush();
        }, 10_000);

        // Final beacon on navigation away.
        const onVisibility = () => {
            if (document.visibilityState === "hidden") {
                accumulate();
                flushBeacon();
            }
        };
        document.addEventListener("visibilitychange", onVisibility);

        return () => {
            clearInterval(heartbeat);
            el.removeEventListener("play", onPlay);
            el.removeEventListener("pause", onPauseOrEnded);
            el.removeEventListener("ended", onPauseOrEnded);
            el.removeEventListener("loadedmetadata", onLoaded);
            el.removeEventListener("timeupdate", onTimeUpdate);
            document.removeEventListener("visibilitychange", onVisibility);
            accumulate();
            flushBeacon();
        };

        function accumulate() {
            const now = performance.now();
            if (lastTickRef.current !== null) {
                const delta = (now - lastTickRef.current) / 1000;
                if (delta > 0 && delta < 30) watchedRef.current += delta;
            }
            lastTickRef.current = now;
        }

        function flush() {
            if (!videoId || !sessionIdRef.current) return;
            sendWatchSession({
                session_id: sessionIdRef.current,
                video_id: videoId,
                watched_seconds: Math.floor(watchedRef.current),
                video_duration_seconds: durationRef.current,
                source_type: sentOnceRef.current ? undefined : sourceRef.current,
            }).catch(() => { /* best effort */ });
            sentOnceRef.current = true;
        }

        function flushBeacon() {
            if (!videoId || !sessionIdRef.current) return;
            beaconWatchSession({
                session_id: sessionIdRef.current,
                video_id: videoId,
                watched_seconds: Math.floor(watchedRef.current),
                video_duration_seconds: durationRef.current,
                source_type: sentOnceRef.current ? undefined : sourceRef.current,
            });
        }
    }, [videoId, videoElementRef]);
}

function cryptoUUID(): string {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
        return (crypto as Crypto).randomUUID();
    }
    // RFC4122 v4 fallback
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

function inferSource(): string {
    try {
        const ref = document.referrer;
        if (!ref) return "direct";
        const here = window.location.host;
        const u = new URL(ref);
        if (u.host !== here) return "external";
        if (u.pathname.startsWith("/search")) return "search";
        if (u.pathname.startsWith("/subscriptions")) return "subscriptions";
        if (u.pathname.startsWith("/channel")) return "channel_page";
        if (u.pathname.startsWith("/playlists")) return "playlist";
        if (u.pathname.startsWith("/watch")) return "recommendation";
        if (u.pathname === "/") return "recommendation";
        return "direct";
    } catch {
        return "direct";
    }
}
