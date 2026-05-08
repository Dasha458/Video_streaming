import { useEffect, useState, type ReactNode } from "react";
import { Tv2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getMyChannel, createChannel } from "@api/channelApi";
import type { ChannelInfo } from "@api/types";

interface Props {
    children: ReactNode;
}

export default function CreateChannelGate({ children }: Props) {
    const [channel, setChannel] = useState<ChannelInfo | null | undefined>(undefined);
    const [name, setName] = useState("");
    const [desc, setDesc] = useState("");
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        getMyChannel()
            .then(setChannel)
            .catch(() => setChannel(null));
    }, []);

    if (channel === undefined) return null;

    if (channel !== null) return <>{children}</>;

    const handleCreate = async () => {
        if (!name.trim()) return;
        setCreating(true);
        setError(null);
        try {
            const created = await createChannel({ name: name.trim(), description: desc.trim() || undefined });
            setChannel(created);
        } catch (e: any) {
            const msg = e?.response?.data?.detail ?? "Failed to create channel";
            setError(typeof msg === "string" ? msg : "Failed to create channel");
        } finally {
            setCreating(false);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
            <Tv2 className="h-16 w-16 text-muted-foreground mb-4" />
            <h2 className="text-xl font-bold mb-1">Create your channel</h2>
            <p className="text-sm text-muted-foreground mb-6 text-center max-w-sm">
                You need a channel before you can upload videos or view analytics.
            </p>
            <div className="w-full max-w-sm space-y-3">
                <Input
                    placeholder="Channel name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                />
                <textarea
                    placeholder="Description (optional)"
                    value={desc}
                    onChange={(e) => setDesc(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
                />
                {error && <p className="text-sm text-red-500">{error}</p>}
                <Button
                    className="w-full"
                    onClick={handleCreate}
                    disabled={!name.trim() || creating}
                >
                    {creating ? "Creating…" : "Create channel"}
                </Button>
            </div>
        </div>
    );
}
