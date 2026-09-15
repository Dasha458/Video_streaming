import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getContent, type Period } from "@/lib/api/analyticsApi";
import { useStudioData } from "@/hooks/queries/useStudioQuery";
import { ChartCard, EmptyState } from "../shared";

export function ContentTab({ period }: { period: Period }) {
    const { data, loading } = useStudioData("content", getContent, period);

    return (
        <ChartCard title="Your videos">
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
            ) : <EmptyState>No videos uploaded yet</EmptyState>}
        </ChartCard>
    );
}
