import { useEffect, useState } from "react";
import ChannelCard from "@/components/ChannelCard";
import { getMySubscriptions, unsubscribeFromChannel } from "@/lib/api/channelApi";
import type { ChannelSubscriptionItem } from "@/lib/api/types";
import { toast } from "@/components/ui/toast/use-toast";

export default function Subscriptions() {
    const [channels, setChannels] = useState<ChannelSubscriptionItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [unsubscribingId, setUnsubscribingId] = useState<string | null>(null);

    useEffect(() => {
        getMySubscriptions()
            .then(setChannels)
            .catch(() => setError("Failed to load subscriptions."))
            .finally(() => setLoading(false));
    }, []);

    const handleUnsubscribe = async (channelName: string) => {
        setUnsubscribingId(channelName);
        try {
            await unsubscribeFromChannel(channelName);
            setChannels((prev) => prev.filter((c) => c.channel_name !== channelName));
            toast({ title: `Unsubscribed from ${channelName}` });
        } catch {
            toast({ title: "Failed to unsubscribe", variant: "destructive" });
        } finally {
            setUnsubscribingId(null);
        }
    };

    if (loading) {
        return (
            <div className="px-4 py-6 max-w-3xl">
                <h1 className="text-3xl font-bold mb-6">
                    Channels you're subscribed to
                </h1>
                <p className="text-muted-foreground">Loading...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="px-4 py-6 max-w-3xl">
                <h1 className="text-3xl font-bold mb-6">
                    Channels you're subscribed to
                </h1>
                <p className="text-destructive">{error}</p>
            </div>
        );
    }

    return (
        <div className="px-4 py-6 max-w-3xl">
            <h1 className="text-3xl font-bold mb-6">
                Channels you're subscribed to
            </h1>

            {channels.length === 0 ? (
                <p className="text-muted-foreground">
                    You haven't subscribed to any channels yet.
                </p>
            ) : (
                <div className="flex flex-col gap-4">
                    {channels.map((channel) => (
                        <ChannelCard
                            key={channel.channel_name}
                            channel_avatar={channel.channel_avatar ?? undefined}
                            channel_name={channel.channel_name}
                            handle={`@${channel.channel_name}`}
                            subscribers={`${channel.subscribersCount} subscribers`}
                            description=""
                            onUnsubscribe={() => handleUnsubscribe(channel.channel_name)}
                            unsubscribing={unsubscribingId === channel.channel_name}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
