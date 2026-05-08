import { useEffect, useState } from "react";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import clientApi from "@api/clientApi";
import { timeAgo } from "@/utils/timeAgo";

interface Notification {
    id: string;
    content: string;
    is_read: boolean;
    created_at: string;
    type: string;
}

interface NotificationsPage {
    items: Notification[];
    total: number;
    unread_count: number;
}

export default function Notifications() {
    const [items, setItems] = useState<Notification[]>([]);
    const [loading, setLoading] = useState(true);

    const load = () => {
        setLoading(true);
        clientApi.get<NotificationsPage>("/api/notifications", { params: { page: 1, size: 50 } })
            .then((r) => setItems(r.data.items ?? []))
            .catch(() => {})
            .finally(() => setLoading(false));
    };

    useEffect(() => { load(); }, []);

    const markRead = async (id: string) => {
        await clientApi.put(`/api/notifications/${id}/read`).catch(() => {});
        setItems((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n));
    };

    const markAll = async () => {
        await clientApi.put("/api/notifications/read-all").catch(() => {});
        setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    };

    const unread = items.filter((n) => !n.is_read).length;

    return (
        <div className="px-4 py-6 max-w-2xl mx-auto space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold flex items-center gap-2">
                    <Bell className="h-6 w-6" />
                    Notifications
                    {unread > 0 && (
                        <span className="ml-1 rounded-full bg-red-500 px-2 py-0.5 text-xs font-bold text-white">{unread}</span>
                    )}
                </h1>
                {unread > 0 && (
                    <Button variant="outline" size="sm" onClick={markAll}>
                        <Check className="h-3.5 w-3.5 mr-1" /> Mark all read
                    </Button>
                )}
            </div>

            {loading ? (
                <div className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}
                </div>
            ) : items.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <Bell className="h-14 w-14 text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">No notifications yet</p>
                </div>
            ) : (
                <div className="space-y-2">
                    {items.map((n) => (
                        <div
                            key={n.id}
                            className={`flex items-start gap-3 rounded-lg border p-4 transition-colors ${n.is_read ? "bg-background" : "bg-muted/40"}`}
                        >
                            <div className={`mt-1 h-2 w-2 rounded-full shrink-0 ${n.is_read ? "bg-transparent" : "bg-blue-500"}`} />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm">{n.content}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{timeAgo(n.created_at)}</p>
                            </div>
                            {!n.is_read && (
                                <button
                                    onClick={() => markRead(n.id)}
                                    className="text-xs text-muted-foreground hover:text-foreground shrink-0"
                                >
                                    Mark read
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
