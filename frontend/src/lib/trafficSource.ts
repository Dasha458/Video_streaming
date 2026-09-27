/**
 * Where the viewer came from, derived from the referrer.
 *
 * The backend stamps this onto the VideoView row it creates, and the
 * Traffic Sources panel in Creator Studio is a breakdown of it. Nothing
 * used to send it, so every row was recorded as "unknown" and the panel
 * had exactly one slice.
 *
 * Kept in its own module because both the video request and the watch
 * session need the same answer, and two copies would drift.
 */
export type TrafficSource =
    | "direct"
    | "search"
    | "recommendation"
    | "external"
    | "channel_page"
    | "playlist"
    | "subscriptions";

export function inferSource(): TrafficSource {
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
