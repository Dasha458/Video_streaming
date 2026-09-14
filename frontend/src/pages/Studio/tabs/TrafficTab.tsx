import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { getTrafficSources, type Period } from "@/lib/api/analyticsApi";
import { useStudioData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, ChartSkeleton, EmptyState, StatCard } from "../shared";
import { SOURCE_COLORS } from "../utils";

export function TrafficTab({ period }: { period: Period }) {
    const { data, loading } = useStudioData("traffic", getTrafficSources, period);

    return (
        <div className="space-y-6">
            <StatCard label="Total views in period" value={data?.total_views ?? 0} loading={loading} />

            <ChartCard title="Traffic sources">
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
                                <Tooltip formatter={(v: unknown) => Number(v ?? 0).toLocaleString()} />
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
                                            <span
                                                className="inline-block h-3 w-3 rounded-sm"
                                                style={{ background: SOURCE_COLORS[i % SOURCE_COLORS.length] }}
                                            />
                                            <span className="capitalize">{s.source.replace("_", " ")}</span>
                                        </td>
                                        <td className="py-2 text-right">{s.views.toLocaleString()}</td>
                                        <td className="py-2 text-right">{s.percentage}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : <EmptyState>No traffic source data yet</EmptyState>}
            </ChartCard>
        </div>
    );
}
