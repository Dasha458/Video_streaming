import { Link } from "react-router-dom";
import {
    CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { getOverview, type Period } from "@/lib/api/analyticsApi";
import { useStudioData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, ChartSkeleton, EmptyState, StatCard } from "../shared";
import { formatSeconds } from "../utils";

export function OverviewTab({ period }: { period: Period }) {
    const { data, loading } = useStudioData("overview", getOverview, period);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                <StatCard label="Views" value={data?.total_views.value ?? 0} loading={loading} delta={data?.total_views} />
                <StatCard label="Watch time" value={formatSeconds(data?.total_watch_time_seconds.value ?? 0)} loading={loading} delta={data?.total_watch_time_seconds} />
                <StatCard label="Subscribers" value={data?.total_subscribers ?? 0} loading={loading} />
                <StatCard label="Likes" value={data?.total_likes.value ?? 0} loading={loading} delta={data?.total_likes} />
                <StatCard label="Comments" value={data?.total_comments.value ?? 0} loading={loading} delta={data?.total_comments} />
            </div>

            <ChartCard title="Views">
                {loading ? <ChartSkeleton /> : data?.views_per_day.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={data.views_per_day} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip formatter={(v) => [v, "Views"]} />
                            <Line
                                type="monotone"
                                dataKey="count"
                                name="Views"
                                stroke="hsl(var(--primary))"
                                strokeWidth={2}
                                dot={{ r: 3, fill: "hsl(var(--primary))", strokeWidth: 0 }}
                                activeDot={{ r: 5, fill: "hsl(var(--primary))" }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                ) : <EmptyState>No view data yet</EmptyState>}
            </ChartCard>

            <ChartCard title="Top videos in period">
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
            </ChartCard>
        </div>
    );
}
