import {
    Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getAudience, type Period } from "@/lib/api/analyticsApi";
import { useStudioData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, ChartSkeleton, EmptyState, StatCard } from "../shared";

export function AudienceTab({ period }: { period: Period }) {
    const { data, loading } = useStudioData("audience", getAudience, period);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
                <StatCard label="Unique viewers" value={data?.unique_viewers ?? 0} loading={loading} />
                <StatCard label="Returning viewers" value={data?.returning_viewers ?? 0} loading={loading} />
            </div>

            <ChartCard title="Subscribers gained">
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
                ) : <EmptyState>No subscription data yet</EmptyState>}
            </ChartCard>

            <ChartCard title="Comments">
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
                ) : <EmptyState>No comment data yet</EmptyState>}
            </ChartCard>
        </div>
    );
}
