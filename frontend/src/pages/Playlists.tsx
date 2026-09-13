import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ListVideo, Globe, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { getPlaylists, createPlaylist, deletePlaylist, type PlaylistItem } from "@api/playlistApi";
import { timeAgo } from "@/utils/timeAgo";

export default function Playlists() {
    const [playlists, setPlaylists] = useState<PlaylistItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [newName, setNewName] = useState("");
    const [newDesc, setNewDesc] = useState("");
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        loadPlaylists();
    }, []);

    const loadPlaylists = async () => {
        setLoading(true);
        try {
            const data = await getPlaylists();
            setPlaylists(data.items);
        } catch (err) {
            console.error("Failed to load playlists:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async () => {
        if (!newName.trim()) return;
        setCreating(true);
        try {
            const created = await createPlaylist(newName.trim(), newDesc.trim() || undefined);
            setPlaylists(prev => [created, ...prev]);
            setDialogOpen(false);
            setNewName("");
            setNewDesc("");
        } catch (err) {
            console.error("Failed to create playlist:", err);
        } finally {
            setCreating(false);
        }
    };

    const handleDelete = async (e: React.MouseEvent, playlistId: string) => {
        e.preventDefault();
        e.stopPropagation();
        try {
            await deletePlaylist(playlistId);
            setPlaylists(prev => prev.filter(p => p.id !== playlistId));
        } catch (err) {
            console.error("Failed to delete playlist:", err);
        }
    };

    return (
        <div className="px-4 py-6">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-bold">Playlists</h1>
                <Button
                    variant="outline"
                    className="gap-2 rounded-full"
                    onClick={() => setDialogOpen(true)}
                >
                    <Plus className="h-4 w-4" />
                    New playlist
                </Button>
            </div>

            {loading ? (
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                    {Array.from({ length: 8 }).map((_, i) => (
                        <div key={i} className="animate-pulse">
                            <div className="aspect-video rounded-xl bg-muted mb-3" />
                            <div className="h-4 bg-muted rounded w-3/4 mb-1" />
                            <div className="h-3 bg-muted rounded w-1/2" />
                        </div>
                    ))}
                </div>
            ) : playlists.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <ListVideo className="h-16 w-16 text-muted-foreground mb-4" />
                    <h2 className="text-lg font-semibold mb-1">No playlists yet</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                        Create a playlist to organise your favourite videos.
                    </p>
                    <Button className="rounded-full gap-2" onClick={() => setDialogOpen(true)}>
                        <Plus className="h-4 w-4" />
                        New playlist
                    </Button>
                </div>
            ) : (
                <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                    {playlists.map((pl) => (
                        <Link key={pl.id} to={`/playlist/${pl.id}`} className="group block">
                            <div className="relative aspect-video rounded-xl overflow-hidden bg-muted mb-3">
                                <div className="w-full h-full flex items-center justify-center bg-muted">
                                    <ListVideo className="h-10 w-10 text-muted-foreground" />
                                </div>
                                <div className="absolute inset-y-0 right-0 w-1/3 bg-black/70 flex flex-col items-center justify-center gap-1">
                                    <ListVideo className="h-5 w-5 text-white" />
                                    <span className="text-white text-xs font-semibold">{pl.video_count}</span>
                                </div>
                                <Button
                                    size="icon"
                                    variant="destructive"
                                    className="absolute top-2 left-2 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                                    onClick={(e) => handleDelete(e, pl.id)}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </div>

                            <h3 className="font-semibold text-sm line-clamp-2 leading-snug">{pl.name}</h3>
                            <div className="flex items-center gap-1 mt-0.5 text-xs text-muted-foreground">
                                <Globe className="h-3 w-3" />
                                <span>Public</span>
                                <span>·</span>
                                <span>
                                    {timeAgo(pl.created_at)}
                                </span>
                            </div>
                        </Link>
                    ))}
                </div>
            )}

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>New playlist</DialogTitle>
                        <DialogDescription>
                            Give your playlist a name and an optional description.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                        <Input
                            placeholder="Playlist name"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                        />
                        <textarea
                            placeholder="Description (optional)"
                            value={newDesc}
                            onChange={(e) => setNewDesc(e.target.value)}
                            rows={3}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
                        />
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleCreate} disabled={!newName.trim() || creating}>
                            {creating ? "Creating..." : "Create"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
