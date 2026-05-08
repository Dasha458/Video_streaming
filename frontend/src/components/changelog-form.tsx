import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getChangelog } from "@api/authApi";
import type { ChangelogEntry } from "@api/types";

const TAG_COLORS: Record<string, string> = {
    "New Features": "bg-emerald-500/20 text-emerald-600 hover:bg-emerald-500/30",
    "Improvements": "bg-purple-500/20 text-purple-600 hover:bg-purple-500/30",
    "Bug Fixes": "bg-red-500/20 text-red-600 hover:bg-red-500/30",
};

function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export default function ChangelogForm() {
    const [entries, setEntries] = useState<ChangelogEntry[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getChangelog()
            .then(setEntries)
            .catch(() => setEntries([]))
            .finally(() => setLoading(false));
    }, []);

    return (
        <div className="min-h-screen p-4">
            <header className="relative overflow-hidden rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 p-8 text-center text-white shadow-lg md:p-16 lg:p-20">
                <div className="relative z-10 mx-auto max-w-4xl space-y-4">
                    <h1 className="text-3xl font-bold tracking-tight md:text-5xl">What&apos;s new?</h1>
                    <p className="text-lg text-balance opacity-80 sm:text-xl">
                        A rundown of the latest feature releases, improvements, and bug fixes.
                    </p>
                </div>
            </header>

            <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
                {loading ? (
                    <div className="grid gap-12">
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="grid gap-4 md:grid-cols-[120px_1fr] md:gap-8">
                                <Skeleton className="h-4 w-24 mt-1" />
                                <div className="space-y-3">
                                    <Skeleton className="h-7 w-40" />
                                    <Skeleton className="h-4 w-full" />
                                    <Skeleton className="h-4 w-3/4" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="grid gap-12">
                        {entries.map((entry) => (
                            <div key={entry.version} className="grid gap-4 md:grid-cols-[120px_1fr] md:gap-8">
                                <div className="text-muted-foreground mt-1 text-sm md:text-right">
                                    {formatDate(entry.date)}
                                </div>
                                <div className="grid gap-4">
                                    <h2 className="text-2xl font-bold">Version {entry.version}</h2>
                                    {entry.tags && entry.tags.length > 0 && (
                                        <div className="flex flex-wrap gap-2">
                                            {entry.tags.map((tag) => (
                                                <Badge key={tag} className={TAG_COLORS[tag] ?? "bg-muted text-muted-foreground"}>
                                                    {tag}
                                                </Badge>
                                            ))}
                                        </div>
                                    )}
                                    {entry.newFeatures && entry.newFeatures.length > 0 && (
                                        <div>
                                            <p className="text-sm font-semibold text-emerald-600 mb-1">New Features</p>
                                            <ul className="space-y-1">
                                                {entry.newFeatures.map((f, i) => (
                                                    <li key={i} className="flex items-start gap-2 text-sm">
                                                        <span className="text-emerald-500 mt-0.5">✦</span>
                                                        {f}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                    {entry.improvements && entry.improvements.length > 0 && (
                                        <div>
                                            <p className="text-sm font-semibold text-purple-600 mb-1">Improvements</p>
                                            <ul className="space-y-1">
                                                {entry.improvements.map((f, i) => (
                                                    <li key={i} className="flex items-start gap-2 text-sm">
                                                        <span className="text-purple-500 mt-0.5">✦</span>
                                                        {f}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                    {entry.bugfixes && entry.bugfixes.length > 0 && (
                                        <div>
                                            <p className="text-sm font-semibold text-red-600 mb-1">Bug Fixes</p>
                                            <ul className="space-y-1">
                                                {entry.bugfixes.map((f, i) => (
                                                    <li key={i} className="flex items-start gap-2 text-sm">
                                                        <span className="text-red-500 mt-0.5">✦</span>
                                                        {f}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}
