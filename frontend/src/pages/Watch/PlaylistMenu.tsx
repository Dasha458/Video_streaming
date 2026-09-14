import { useState } from "react";
import { Check, ListPlus } from "lucide-react";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { addToPlaylist, getPlaylists, type PlaylistItem } from "@api/playlistApi";

interface PlaylistMenuProps {
    videoId: string;
}

/** "Save to playlist" dropdown. Playlists are loaded the first time it opens. */
export function PlaylistMenu({ videoId }: PlaylistMenuProps) {
    const [playlists, setPlaylists] = useState<PlaylistItem[]>([]);
    const [added, setAdded] = useState<Set<string>>(new Set());

    const handleOpenChange = async (open: boolean) => {
        if (!open || playlists.length > 0) return;
        try {
            const data = await getPlaylists();
            setPlaylists(data.items);
        } catch { /* ignore */ }
    };

    const handleAdd = async (playlistId: string) => {
        if (!videoId) return;
        try {
            await addToPlaylist(playlistId, videoId);
            setAdded((prev) => new Set(prev).add(playlistId));
        } catch { /* ignore */ }
    };

    return (
        <DropdownMenu onOpenChange={handleOpenChange}>
            <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-1.5 rounded-full bg-muted px-4 py-2 text-sm font-medium hover:bg-muted/70 transition-colors">
                    <ListPlus className="h-4 w-4" />
                    Save
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[180px]">
                {playlists.length === 0 ? (
                    <p className="px-2 py-1.5 text-sm text-muted-foreground">No playlists yet</p>
                ) : (
                    playlists.map((pl) => (
                        <DropdownMenuItem
                            key={pl.id}
                            className="justify-between"
                            // Keep the menu open so several playlists can be picked.
                            onSelect={(e) => {
                                e.preventDefault();
                                handleAdd(pl.id);
                            }}
                        >
                            <span className="truncate">{pl.name}</span>
                            {added.has(pl.id) && <Check className="h-3.5 w-3.5 text-emerald-500 shrink-0 ml-2" />}
                        </DropdownMenuItem>
                    ))
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
