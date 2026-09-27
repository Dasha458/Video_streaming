import { useEffect, useRef } from "react";
import { beaconWatchSession, sendWatchSession } from "@/lib/api/analyticsApi";

/**
 * Tracks playback progress for creator-analytics watch-time / retention.
 *
 *   * A stable v4 ``session_id`` is generated once per video.
 *   * While the video is playing the watched-seconds counter increments
 *     locally and a heartbeat is POSTed every ~10 seconds.
 *   * On tab close / component unmount we fire a final ``sendBeacon`` so
 *     the server gets the last cursor even after the page is gone.
 *
 * Takes the element itself, not a ref object: the watch page renders a
 * skeleton until the video loads, so at first render there is no <video>
 * yet. A ref object never changes identity, so an effect keyed on one
 * would bail out on that first render and never run again -- which is
 * exactly what used to happen, and why no watch session was ever recorded.
 * Pass it via a callback ref (`ref={setVideoEl}`) so this re-runs when the
 * player actually mounts.
 *
 * The traffic-source tag does not belong here: the ping used to carry one
 * and the server discarded it, because a watch session has no column for
 * it. It travels with the video request instead, which is where the view
 * row it labels is created.
 */
export function useWatchSession(
    videoId: string | undefined,
    videoElement: HTMLVideoElement | null,
) {
    const sessionIdRef = useRef<string>("");
    const watchedRef = useRef<number>(0);
    // Timestamp of the last measurement of the *current playing stretch*,
    // or null when playback is not running. Null is what keeps a paused
    // video from accruing time.
    const lastTickRef = useRef<number | null>(null);
    const durationRef = useRef<number>(0);
    const sentOnceRef = useRef<boolean>(false);

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
        const el = videoElement;
        if (!videoId || !el) return;

        // The element may already be loaded/playing by the time this runs.
        if (el.readyState > 0) durationRef.current = Math.max(0, Math.floor(el.duration || 0));
        if (!el.paused && !el.ended) lastTickRef.current = performance.now();

        const onPlay = () => { lastTickRef.current = performance.now(); };
        const onPauseOrEnded = () => {
            accumulate();
            flush();
        };
        const onLoaded = () => {
            durationRef.current = Math.max(0, Math.floor(el.duration || 0));
        };
        const onTimeUpdate = () => {
            if (!el.paused && !el.ended) accumulate();
        };

        el.addEventListener("play", onPlay);
        el.addEventListener("pause", onPauseOrEnded);
        el.addEventListener("ended", onPauseOrEnded);
        el.addEventListener("loadedmetadata", onLoaded);
        el.addEventListener("timeupdate", onTimeUpdate);

        // Periodic heartbeat (10s).
        const heartbeat = setInterval(() => {
            accumulate();
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

        /** Adds the elapsed slice of the current playing stretch, if any. */
        function accumulate() {
            if (lastTickRef.current === null) return; // paused: nothing accrues
            const now = performance.now();
            const delta = (now - lastTickRef.current) / 1000;
            if (delta > 0 && delta < 30) watchedRef.current += delta;
            lastTickRef.current = el!.paused || el!.ended ? null : now;
        }

        function payload() {
            return {
                session_id: sessionIdRef.current,
                video_id: videoId!,
                watched_seconds: Math.floor(watchedRef.current),
                video_duration_seconds: durationRef.current,
            };
        }

        /** Nothing watched and nothing reported yet -> no session worth opening. */
        function nothingToReport() {
            return Math.floor(watchedRef.current) <= 0 && !sentOnceRef.current;
        }

        function flush() {
            if (!videoId || !sessionIdRef.current || nothingToReport()) return;
            sendWatchSession(payload()).catch(() => { /* best effort */ });
            sentOnceRef.current = true;
        }

        function flushBeacon() {
            if (!videoId || !sessionIdRef.current || nothingToReport()) return;
            beaconWatchSession(payload());
            sentOnceRef.current = true;
        }
    }, [videoId, videoElement]);
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
