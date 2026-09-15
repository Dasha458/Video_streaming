import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { useRealtimeData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, ChartSkeleton, EmptyState, StatCard } from "../shared";
import { formatHour } from "../utils";

export function RealtimeTab() {
    const { data, loading } = useRealtimeData();

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
                <StatCard label="Views — last 60 min" value={data?.views_last_60min ?? 0} loading={loading} />
                <StatCard label="Views — last 48 h" value={data?.views_last_48h ?? 0} loading={loading} />
            </div>

            <ChartCard title="Views per hour — last 48 hours">
                {loading ? <ChartSkeleton /> : data?.views_per_hour.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={data.views_per_hour}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={formatHour} interval={3} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip labelFormatter={(l: unknown) => new Date(String(l)).toLocaleString()} />
                            <Bar dataKey="count" name="Views" fill="hsl(var(--primary))" />
                        </BarChart>
                    </ResponsiveContainer>
                ) : <EmptyState>No recent views</EmptyState>}
            </ChartCard>

            <ChartCard title="Top videos — last 48 hours">
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
            </ChartCard>
        </div>
    );
}
