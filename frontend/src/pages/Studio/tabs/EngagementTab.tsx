import {
    Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getEngagement, type Period } from "@/lib/api/analyticsApi";
import { useStudioData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, ChartSkeleton, EmptyState, StatCard } from "../shared";
import { formatSeconds } from "../utils";

export function EngagementTab({ period }: { period: Period }) {
    const { data, loading } = useStudioData("engagement", getEngagement, period);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Total watch time" value={formatSeconds(data?.total_watch_time_seconds ?? 0)} loading={loading} />
                <StatCard label="Avg view duration" value={formatSeconds(Math.round(data?.average_view_duration_seconds ?? 0))} loading={loading} />
                <StatCard label="Avg % viewed" value={`${data?.average_percent_viewed ?? 0}%`} loading={loading} />
                <StatCard label="Engagement rate" value={`${data?.engagement_rate ?? 0}%`} loading={loading} />
            </div>

            <ChartCard title="Watch time (seconds) per day">
                {loading ? <ChartSkeleton /> : data?.watch_time_per_day.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={data.watch_time_per_day}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip formatter={(v: unknown) => formatSeconds(Number(v ?? 0))} />
                            <Bar dataKey="count" name="Watch time" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                ) : (
                    <EmptyState>
                        No watch-time data yet — install the heartbeat in the player and generate some views.
                    </EmptyState>
                )}
            </ChartCard>

            <ChartCard title="Average % viewed per day">
                {loading ? <ChartSkeleton /> : data?.avg_percent_viewed_per_day.length ? (
                    <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={data.avg_percent_viewed_per_day}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                            <Tooltip formatter={(v: unknown) => `${v ?? 0}%`} />
                            <Line type="monotone" dataKey="count" name="% viewed" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                        </LineChart>
                    </ResponsiveContainer>
                ) : <EmptyState>No retention data yet</EmptyState>}
            </ChartCard>
        </div>
    );
}
