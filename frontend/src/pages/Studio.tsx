import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import CreateChannelGate from "@/components/CreateChannelGate";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer, BarChart, Bar,
    PieChart, Pie, Cell, Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
    getOverview, getContent, getAudience, getEngagement,
    getRealtime, getTrafficSources,
    type OverviewData, type ContentData, type AudienceData,
    type EngagementData, type RealtimeData, type TrafficSourcesData,
    type Period, type DeltaInt,
} from "@/lib/api/analyticsApi";

type Tab = "overview" | "content" | "audience" | "engagement" | "realtime" | "traffic";

// ── Utilities ────────────────────────────────────────────────────────────────

function formatSeconds(total: number): string {
    if (!total) return "0s";
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m ${s}s`;
    return `${s}s`;
}

function formatHour(iso: string): string {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:00`;
}

// ── Reusable components ──────────────────────────────────────────────────────

function DeltaBadge({ d }: { d: DeltaInt }) {
    const up = d.delta_percent > 0;
    const flat = d.delta_percent === 0;
    const sign = up ? "+" : "";
    return (
        <span
            className={`text-xs font-medium ${
                flat ? "text-muted-foreground" : up ? "text-emerald-500" : "text-red-500"
            }`}
        >
            {sign}{d.delta_percent}%
        </span>
    );
}

function StatCard({
    label, value, loading, delta,
}: {
    label: string;
    value: number | string;
    loading: boolean;
    delta?: DeltaInt;
}) {
    return (
        <Card>
            <CardHeader className="pb-1">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                    {label}
                </CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-8 w-24" />
                ) : (
                    <div className="flex items-baseline gap-2">
                        <p className="text-2xl font-bold">
                            {typeof value === "number" ? value.toLocaleString() : value}
                        </p>
                        {delta && <DeltaBadge d={delta} />}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function ChartSkeleton() {
    return <Skeleton className="h-[200px] w-full" />;
}

// ── Period selector ──────────────────────────────────────────────────────────

const PERIODS: { value: Period; label: string }[] = [
    { value: "7d",   label: "Last 7 days" },
    { value: "28d",  label: "Last 28 days" },
    { value: "90d",  label: "Last 90 days" },
    { value: "365d", label: "Last 365 days" },
    { value: "all",  label: "Lifetime" },
];

function PeriodSelector({
    value, onChange,
}: { value: Period; onChange: (p: Period) => void }) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value as Period)}
            className="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
            {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
            ))}
        </select>
    );
}

// ── Overview ─────────────────────────────────────────────────────────────────

function OverviewTab({ period }: { period: Period }) {
    const [data, setData] = useState<OverviewData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getOverview(period).then(setData).finally(() => setLoading(false));
    }, [period]);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                <StatCard label="Views" value={data?.total_views.value ?? 0} loading={loading} delta={data?.total_views} />
                <StatCard label="Watch time" value={formatSeconds(data?.total_watch_time_seconds.value ?? 0)} loading={loading} delta={data?.total_watch_time_seconds} />
                <StatCard label="Subscribers" value={data?.total_subscribers ?? 0} loading={loading} />
                <StatCard label="Likes" value={data?.total_likes.value ?? 0} loading={loading} delta={data?.total_likes} />
                <StatCard label="Comments" value={data?.total_comments.value ?? 0} loading={loading} delta={data?.total_comments} />
            </div>

            <Card>
                <CardHeader><CardTitle className="text-base">Views</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.views_per_day.length ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <LineChart data={data.views_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip />
                                <Line type="monotone" dataKey="count" name="Views" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No view data yet</p>}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle className="text-base">Top videos in period</CardTitle></CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="space-y-3">
                            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
                        </div>
                    ) : data?.top_videos.length ? (
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b text-muted-foreground text-left">
                                    <th className="pb-2 font-medium">Title</th>
                                    <th className="pb-2 font-medium text-right">Views</th>
                                    <th className="pb-2 font-medium text-right">Likes</th>
                                    <th className="pb-2 font-medium text-right">Comments</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.top_videos.map((v) => (
                                    <tr key={v.id} className="border-b last:border-0 hover:bg-muted/30">
                                        <td className="py-2 max-w-60 truncate">
                                            <Link to={`/studio/video/${v.id}`} className="hover:underline">{v.title}</Link>
                                        </td>
                                        <td className="py-2 text-right">{v.views_count.toLocaleString()}</td>
                                        <td className="py-2 text-right">{v.likes_count.toLocaleString()}</td>
                                        <td className="py-2 text-right">{v.comments_count.toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : <p className="text-sm text-muted-foreground text-center py-8">No data</p>}
                </CardContent>
            </Card>
        </div>
    );
}

// ── Content ──────────────────────────────────────────────────────────────────

function ContentTab({ period }: { period: Period }) {
    const [data, setData] = useState<ContentData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getContent(period).then(setData).finally(() => setLoading(false));
    }, [period]);

    return (
        <Card>
            <CardHeader><CardTitle className="text-base">Your videos</CardTitle></CardHeader>
            <CardContent>
                {loading ? (
                    <div className="space-y-3">
                        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
                    </div>
                ) : data?.videos.length ? (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b text-muted-foreground text-left">
                                    <th className="pb-2 font-medium">Title</th>
                                    <th className="pb-2 font-medium">Status</th>
                                    <th className="pb-2 font-medium text-right">Views</th>
                                    <th className="pb-2 font-medium text-right">Likes</th>
                                    <th className="pb-2 font-medium text-right">Dislikes</th>
                                    <th className="pb-2 font-medium text-right">Comments</th>
                                    <th className="pb-2 font-medium text-right">Uploaded</th>
                                    <th className="pb-2 font-medium"></th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.videos.map((v) => (
                                    <tr key={v.id} className="border-b last:border-0 hover:bg-muted/30">
                                        <td className="py-2 max-w-[200px] truncate">{v.title}</td>
                                        <td className="py-2">
                                            <Badge variant={v.privacy === "public" ? "default" : "secondary"}>
                                                {v.privacy}
                                            </Badge>
                                        </td>
                                        <td className="py-2 text-right">{v.views_count.toLocaleString()}</td>
                                        <td className="py-2 text-right">{v.likes_count.toLocaleString()}</td>
                                        <td className="py-2 text-right">{v.dislikes_count.toLocaleString()}</td>
                                        <td className="py-2 text-right">{v.comments_count.toLocaleString()}</td>
                                        <td className="py-2 text-right text-muted-foreground whitespace-nowrap">
                                            {new Date(v.created_at).toLocaleDateString()}
                                        </td>
                                        <td className="py-2">
                                            <Link to={`/studio/video/${v.id}`} className="text-xs text-primary hover:underline">
                                                Analytics →
                                            </Link>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : <p className="text-sm text-muted-foreground text-center py-12">No videos uploaded yet</p>}
            </CardContent>
        </Card>
    );
}

// ── Audience ─────────────────────────────────────────────────────────────────

function AudienceTab({ period }: { period: Period }) {
    const [data, setData] = useState<AudienceData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getAudience(period).then(setData).finally(() => setLoading(false));
    }, [period]);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
                <StatCard label="Unique viewers" value={data?.unique_viewers ?? 0} loading={loading} />
                <StatCard label="Returning viewers" value={data?.returning_viewers ?? 0} loading={loading} />
            </div>

            <Card>
                <CardHeader><CardTitle className="text-base">Subscribers gained</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.subscribers_per_day.length ? (
                        <ResponsiveContainer width="100%" height={200}>
                            <BarChart data={data.subscribers_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip />
                                <Bar dataKey="count" name="Subscribers" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No subscription data yet</p>}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle className="text-base">Comments</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.comments_per_day.length ? (
                        <ResponsiveContainer width="100%" height={200}>
                            <LineChart data={data.comments_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip />
                                <Line type="monotone" dataKey="count" name="Comments" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No comment data yet</p>}
                </CardContent>
            </Card>
        </div>
    );
}

// ── Engagement ───────────────────────────────────────────────────────────────

function EngagementTab({ period }: { period: Period }) {
    const [data, setData] = useState<EngagementData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getEngagement(period).then(setData).finally(() => setLoading(false));
    }, [period]);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Total watch time" value={formatSeconds(data?.total_watch_time_seconds ?? 0)} loading={loading} />
                <StatCard label="Avg view duration" value={formatSeconds(Math.round(data?.average_view_duration_seconds ?? 0))} loading={loading} />
                <StatCard label="Avg % viewed" value={`${data?.average_percent_viewed ?? 0}%`} loading={loading} />
                <StatCard label="Engagement rate" value={`${data?.engagement_rate ?? 0}%`} loading={loading} />
            </div>

            <Card>
                <CardHeader><CardTitle className="text-base">Watch time (seconds) per day</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.watch_time_per_day.length ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={data.watch_time_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip formatter={(v: any) => formatSeconds(Number(v ?? 0))} />
                                <Bar dataKey="count" name="Watch time" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No watch-time data yet — install the heartbeat in the player and generate some views.</p>}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle className="text-base">Average % viewed per day</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.avg_percent_viewed_per_day.length ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <LineChart data={data.avg_percent_viewed_per_day}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                                <Tooltip formatter={(v: any) => `${v ?? 0}%`} />
                                <Line type="monotone" dataKey="count" name="% viewed" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No retention data yet</p>}
                </CardContent>
            </Card>
        </div>
    );
}

// ── Real-time ────────────────────────────────────────────────────────────────

function RealtimeTab() {
    const [data, setData] = useState<RealtimeData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;
        const load = () => getRealtime().then((d) => mounted && setData(d)).finally(() => mounted && setLoading(false));
        load();
        const t = setInterval(load, 30_000); // refresh every 30s
        return () => { mounted = false; clearInterval(t); };
    }, []);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
                <StatCard label="Views — last 60 min" value={data?.views_last_60min ?? 0} loading={loading} />
                <StatCard label="Views — last 48 h" value={data?.views_last_48h ?? 0} loading={loading} />
            </div>

            <Card>
                <CardHeader><CardTitle className="text-base">Views per hour — last 48 hours</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.views_per_hour.length ? (
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={data.views_per_hour}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                                <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={formatHour} interval={3} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip labelFormatter={(l: any) => new Date(l).toLocaleString()} />
                                <Bar dataKey="count" name="Views" fill="hsl(var(--primary))" />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No recent views</p>}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle className="text-base">Top videos — last 48 hours</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <Skeleton className="h-20" /> : data?.top_videos_48h.length ? (
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b text-muted-foreground text-left">
                                    <th className="pb-2 font-medium">Title</th>
                                    <th className="pb-2 font-medium text-right">Views</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.top_videos_48h.map((v) => (
                                    <tr key={v.id} className="border-b last:border-0 hover:bg-muted/30">
                                        <td className="py-2 max-w-60 truncate">
                                            <Link to={`/studio/video/${v.id}`} className="hover:underline">{v.title}</Link>
                                        </td>
                                        <td className="py-2 text-right">{v.views_count.toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : <p className="text-sm text-muted-foreground text-center py-8">No activity</p>}
                </CardContent>
            </Card>
        </div>
    );
}

// ── Traffic sources ──────────────────────────────────────────────────────────

const SOURCE_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b",
    "#10b981", "#06b6d4", "#f97316", "#64748b",
];

function TrafficTab({ period }: { period: Period }) {
    const [data, setData] = useState<TrafficSourcesData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getTrafficSources(period).then(setData).finally(() => setLoading(false));
    }, [period]);

    return (
        <div className="space-y-6">
            <StatCard label="Total views in period" value={data?.total_views ?? 0} loading={loading} />

            <Card>
                <CardHeader><CardTitle className="text-base">Traffic sources</CardTitle></CardHeader>
                <CardContent>
                    {loading ? <ChartSkeleton /> : data?.sources.length ? (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
                            <ResponsiveContainer width="100%" height={240}>
                                <PieChart>
                                    <Pie
                                        data={data.sources}
                                        dataKey="views"
                                        nameKey="source"
                                        outerRadius={90}
                                        innerRadius={55}
                                        paddingAngle={2}
                                    >
                                        {data.sources.map((_, i) => (
                                            <Cell key={i} fill={SOURCE_COLORS[i % SOURCE_COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip formatter={(v: any) => Number(v ?? 0).toLocaleString()} />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b text-muted-foreground text-left">
                                        <th className="pb-2 font-medium">Source</th>
                                        <th className="pb-2 font-medium text-right">Views</th>
                                        <th className="pb-2 font-medium text-right">Share</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.sources.map((s, i) => (
                                        <tr key={s.source} className="border-b last:border-0">
                                            <td className="py-2 flex items-center gap-2">
                                                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: SOURCE_COLORS[i % SOURCE_COLORS.length] }} />
                                                <span className="capitalize">{s.source.replace("_", " ")}</span>
                                            </td>
                                            <td className="py-2 text-right">{s.views.toLocaleString()}</td>
                                            <td className="py-2 text-right">{s.percentage}%</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ) : <p className="text-sm text-muted-foreground text-center py-12">No traffic source data yet</p>}
                </CardContent>
            </Card>
        </div>
    );
}

// ── Main page ────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
    { id: "overview",   label: "Overview" },
    { id: "realtime",   label: "Real-time" },
    { id: "content",    label: "Content" },
    { id: "audience",   label: "Audience" },
    { id: "engagement", label: "Engagement" },
    { id: "traffic",    label: "Traffic sources" },
];

export default function Studio() {
    const [activeTab, setActiveTab] = useState<Tab>("overview");
    const [period, setPeriod] = useState<Period>("28d");

    return (
        <CreateChannelGate>
        <div className="px-4 py-6 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-2xl font-bold">Creator Studio</h1>
                {activeTab !== "realtime" && (
                    <PeriodSelector value={period} onChange={setPeriod} />
                )}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b overflow-x-auto">
                {TABS.map((t) => (
                    <Button
                        key={t.id}
                        variant="ghost"
                        size="sm"
                        onClick={() => setActiveTab(t.id)}
                        className={`rounded-none border-b-2 px-4 whitespace-nowrap ${
                            activeTab === t.id
                                ? "border-primary text-foreground font-medium"
                                : "border-transparent text-muted-foreground"
                        }`}
                    >
                        {t.label}
                    </Button>
                ))}
            </div>

            {activeTab === "overview"   && <OverviewTab period={period} />}
            {activeTab === "realtime"   && <RealtimeTab />}
            {activeTab === "content"    && <ContentTab period={period} />}
            {activeTab === "audience"   && <AudienceTab period={period} />}
            {activeTab === "engagement" && <EngagementTab period={period} />}
            {activeTab === "traffic"    && <TrafficTab period={period} />}
        </div>
        </CreateChannelGate>
    );
}
