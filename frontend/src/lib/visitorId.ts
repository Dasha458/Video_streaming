/**
 * A stable id for this browser, so a signed-out viewer counts once.
 *
 * Views are unique viewers, not page loads. A signed-in person is
 * identified by their account; a signed-out one has nothing to be
 * identified by, so the browser keeps an id of its own and sends it back.
 * Without it the server falls back to hashing the address and user agent,
 * which merges everyone behind one NAT into a single viewer.
 *
 * It identifies a browser, not a person: it is random, holds nothing about
 * the visitor, is never sent anywhere but this application's own API, and
 * clearing site data starts a new one.
 */

const STORAGE_KEY = "vs_visitor_id";

/** Sent on requests that record a view; read by src/services/viewer_identity.py. */
export const VISITOR_HEADER = "X-Visitor-Id";

let cached: string | null = null;

export function getVisitorId(): string {
    if (cached) return cached;

    // Private windows, blocked site data and thumbnail capture all make
    // storage throw or come back empty. A per-session id is still better
    // than none, and the server's fallback covers the rest.
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            cached = stored;
            return cached;
        }
        const fresh = newId();
        localStorage.setItem(STORAGE_KEY, fresh);
        cached = fresh;
        return cached;
    } catch {
        cached = newId();
        return cached;
    }
}

function newId(): string {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
        return crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}
