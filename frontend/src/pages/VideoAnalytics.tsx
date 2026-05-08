import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, BarChart, Bar,
} from "recharts";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
    getVideoAnalytics, type VideoAnalyticsData, type Period, type DeltaInt,
} from "@/lib/api/analyticsApi";

const PERIODS: { value: Period; label: string }[] = [
    { value: "7d",   label: "Last 7 days" },
    { value: "28d",  label: "Last 28 days" },
    { value: "90d",  label: "Last 90 days" },
    { value: "365d", label: "Last 365 days" },
    { value: "all",  label: "Lifetime" },
];

function formatSeconds(total: number): string {
    if (!total) return "0s";
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m ${s}s`;
    return `${s}s`;
}

function DeltaBadge({ d }: { d: DeltaInt }) {
    const up = d.delta_percent > 0;
    const flat = d.delta_percent === 0;
    const sign = up ? "+" : "";
    return (
        <span className={`text-xs font-medium ${flat ? "text-muted-foreground" : up ? "text-emerald-500" : "text-red-500"}`}>
            {sign}{d.delta_percent}%
        </span>
    );
}

function StatTile({ label, value, loading, delta }: {
    label: string; value: number | string; loading: boolean; delta?: DeltaInt;
}) {
    return (
        <Card>
            <CardHeader className="pb-1">
                <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? <Skeleton className="h-8 w-20" /> : (
                    <div className="flex items-baseline gap-2">
                        <p className="text-xl font-bold">{typeof value === "number" ? value.toLocaleString() : value}</p>
                        {delta && <DeltaBadge d={delta} />}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default function VideoAnalytics() {
    const { id } = useParams<{ id: string }>();
    const [period, setPeriod] = useState<Period>("28d");
    const [data, setData] = useState<VideoAnalyticsData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id) return;
        setLoading(true);
        setError(null);
        getVideoAnalytics(id, period)
            .then(setData)
            .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load"))
            .finally(() => setLoading(false));
    }, [id, period]);

    if (error) return <p className="p-6 text-red-500">{error}</p>;

    return (
        <div className="px-4 py-6 space-y-6 max-w-6xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <Link to="/studio" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                    <ArrowLeft className="h-4 w-4" /> Back to Studio
                </Link>
                <select
                    value={period}
                    onChange={(e) => setPeriod(e.target.value as Period)}
                    className="rounded-md border bg-background px-3 py-1.5 text-sm"
                >
                    {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
            </div>

            {/* Video header card */}
            <Card>
                <CardContent className="flex gap-4 p-4">
                    {loading ? (
                        <Skeleton className="w-40 aspect-video rounded-md" />
                    ) : data?.thumbnail ? (
                        <img src={data.thumbnail} alt="" className="w-40 aspect-video object-cover rounded-md" />
                    ) : (
                        <div className="w-40 aspect-video rounded-md bg-muted" />
                    )}
                    <div className="flex-1 min-w-0">
                        <h1 className="text-xl font-bold truncate">{loading ? "Loading…" : data?.title}</h1>
                        {!loading && data && (
                            <Link to={`/watch?v=${data.video_id}`} className="text-sm text-primary hover:underline mt-1 inline-block">
                                Open video →
                            </Link>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Top stats */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                <StatTile label="Views" value={data?.views.value ?? 0} loading={loading} delta={data?.views} />
                <StatTile label="Watch time" value={formatSeconds(data?.watch_time_seconds.value ?? 0)} loading={loading} delta={data?.watch_time_seconds} />
                <StatTile label="Avg duration" value={formatSeconds(Math.round(data?.average_view_duration_seconds ?? 0))} loading={loading} />
                <StatTile label="Avg % viewed" value={`${data?.average_percent_viewed ?? 0}%`} loading={loading} />
                <StatTile label="Likes" value={data?.likes.value ?? 0} loading={loading} delta={data?.likes} />
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                <StatTile label="Dislikes" value={data?.dislikes.value ?? 0} loading={loading} delta={data?.dislikes} />
                <StatTile label="Comments" value={data?.comments.value ?? 0} loading={loading} delta={data?.comments} />
                <StatTile
                    label="Like ratio"
                    value={
                        data && (data.likes.value + data.dislikes.value) > 0
                            ? `${Math.round(data.likes.value / (data.likes.value + data.dislikes.value) * 100)}%`
                            : "—"
                    }
                    loading={loading}
                />
            </div>

            {/* Views over time */}
            <Card>
                <CardHeader><CardTitle className="text-base">Views</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <Skeleton className="h-[220px] w-full" /> : data?.views_per_day.length ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <LineChart data={data.views_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip />
                                <Line type="monotone" dataKey="count" name="Views" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No view data in this period</p>}
                </CardContent>
            </Card>

            {/* Retention */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Audience retention</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? <Skeleton className="h-[220px] w-full" /> : data?.retention.length ? (
                        <>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart data={data.retention}>
                                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                    <XAxis dataKey="percent" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
                                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                    <Tooltip formatter={(v: any) => `${Number(v ?? 0).toLocaleString()} viewers`} labelFormatter={(l: any) => `Reached ≥ ${l}%`} />
                                    <Bar dataKey="viewers" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                            <p className="text-xs text-muted-foreground mt-2">
                                Each bar shows how many viewers watched at least this percentage of the video.
                            </p>
                        </>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No retention data yet (player must send watch-session heartbeats).</p>}
                </CardContent>
            </Card>

            {/* Traffic sources */}
            <Card>
                <CardHeader><CardTitle className="text-base">Traffic sources</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <Skeleton className="h-[140px] w-full" /> : data?.traffic_sources.length ? (
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b text-muted-foreground text-left">
                                    <th className="pb-2 font-medium">Source</th>
                                    <th className="pb-2 font-medium text-right">Views</th>
                                    <th className="pb-2 font-medium text-right">Share</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.traffic_sources.map((s) => (
                                    <tr key={s.source} className="border-b last:border-0">
                                        <td className="py-2 capitalize">{s.source.replace("_", " ")}</td>
                                        <td className="py-2 text-right">{s.views.toLocaleString()}</td>
                                        <td className="py-2 text-right">{s.percentage}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : <p className="text-sm text-muted-foreground text-center py-8">No traffic data yet</p>}
                </CardContent>
            </Card>
        </div>
    );
}
