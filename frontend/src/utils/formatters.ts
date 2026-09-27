/**
 * The one place a number becomes display text.
 *
 * There used to be five ways to abbreviate a count -- two `formatViews`,
 * a `formatCount`, a `formatSubs` and a `formatNumber` -- and they did not
 * agree: 1000 rendered as "1K views", "1K", "1.0K" and "1k" depending on
 * which screen you were looking at.
 */

export function formatCategoryName(name: string): string {
    return name.replace(/\b\w/g, (c) => c.toUpperCase());
}

/** 999 -> "999", 1000 -> "1K", 1500 -> "1.5K", 2_400_000 -> "2.4M". */
export function formatCompact(n: number | undefined): string {
    if (n === undefined || n === null || Number.isNaN(n)) return "0";
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${strip(n / 1_000_000)}M`;
    if (abs >= 1_000) return `${strip(n / 1_000)}K`;
    return String(n);
}

/** Empty string for an unknown count, so callers can filter it out. */
export function formatViews(views: number | undefined): string {
    if (views === undefined || views === null) return "";
    return `${formatCompact(views)} ${views === 1 ? "view" : "views"}`;
}

export function formatSubscribers(n: number | undefined): string {
    const count = n ?? 0;
    return `${formatCompact(count)} ${count === 1 ? "subscriber" : "subscribers"}`;
}

/** Duration as "1h 5m" / "5m 3s" / "3s". */
export function formatSeconds(total: number): string {
    if (!total) return "0s";
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m ${s}s`;
    return `${s}s`;
}

function strip(value: number): string {
    return value.toFixed(1).replace(/\.0$/, "");
}
