import type { Period } from "@/lib/api/analyticsApi";

// Re-exported so the Studio tabs keep one import path; the implementation
// lives with the other formatters.
export { formatSeconds } from "@/utils/formatters";

export function formatHour(iso: string): string {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:00`;
}

export const PERIODS: { value: Period; label: string }[] = [
    { value: "7d",   label: "Last 7 days" },
    { value: "28d",  label: "Last 28 days" },
    { value: "90d",  label: "Last 90 days" },
    { value: "365d", label: "Last 365 days" },
    { value: "all",  label: "Lifetime" },
];

export const SOURCE_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b",
    "#10b981", "#06b6d4", "#f97316", "#64748b",
];
