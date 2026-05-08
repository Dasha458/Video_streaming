import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import clientApi from "@api/clientApi";
import { getMyChannel, updateMyChannel } from "@api/channelApi";
import type { ChannelInfo } from "@api/types";

type Tab = "account" | "channel" | "security";

export default function Profile() {
    const { user, isLoading } = useAuth();
    const [tab, setTab] = useState<Tab>("account");

    // Account
    const [username, setUsername] = useState("");
    const [savingAccount, setSavingAccount] = useState(false);
    const [accountMsg, setAccountMsg] = useState<{ ok: boolean; text: string } | null>(null);

    // Channel
    const [channel, setChannel] = useState<ChannelInfo | null>(null);
    const [channelName, setChannelName] = useState("");
    const [channelDesc, setChannelDesc] = useState("");
    const [savingChannel, setSavingChannel] = useState(false);
    const [channelMsg, setChannelMsg] = useState<{ ok: boolean; text: string } | null>(null);

    // Security
    const [currentPw, setCurrentPw] = useState("");
    const [newPw, setNewPw] = useState("");
    const [confirmPw, setConfirmPw] = useState("");
    const [savingPw, setSavingPw] = useState(false);
    const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

    useEffect(() => {
        if (user) setUsername(user.username ?? "");
    }, [user]);

    useEffect(() => {
        if (tab === "channel") {
            getMyChannel().then((c) => {
                if (c) {
                    setChannel(c);
                    setChannelName(c.channel_name ?? c.name ?? "");
                    setChannelDesc(c.description ?? c.bio ?? "");
                }
            }).catch(() => {});
        }
    }, [tab]);

    const handleSaveAccount = async () => {
        if (!username.trim()) return;
        setSavingAccount(true);
        setAccountMsg(null);
        try {
            await clientApi.patch("/api/auth/me", { username: username.trim() });
            setAccountMsg({ ok: true, text: "Username updated" });
        } catch (e: any) {
            setAccountMsg({ ok: false, text: e?.response?.data?.detail ?? "Failed to update" });
        } finally {
            setSavingAccount(false);
        }
    };

    const handleSaveChannel = async () => {
        setSavingChannel(true);
        setChannelMsg(null);
        try {
            const updated = await updateMyChannel({ name: channelName.trim(), description: channelDesc.trim() || undefined });
            setChannel(updated);
            setChannelMsg({ ok: true, text: "Channel updated" });
        } catch (e: any) {
            setChannelMsg({ ok: false, text: e?.response?.data?.detail ?? "Failed to update" });
        } finally {
            setSavingChannel(false);
        }
    };

    const handleChangePassword = async () => {
        if (newPw !== confirmPw) { setPwMsg({ ok: false, text: "Passwords don't match" }); return; }
        if (newPw.length < 8) { setPwMsg({ ok: false, text: "New password must be at least 8 characters" }); return; }
        setSavingPw(true);
        setPwMsg(null);
        try {
            await clientApi.post("/api/auth/me/change-password", { current_password: currentPw, new_password: newPw });
            setPwMsg({ ok: true, text: "Password changed successfully" });
            setCurrentPw(""); setNewPw(""); setConfirmPw("");
        } catch (e: any) {
            setPwMsg({ ok: false, text: e?.response?.data?.detail ?? "Failed to change password" });
        } finally {
            setSavingPw(false);
        }
    };

    if (isLoading) return <div className="flex items-center justify-center p-12"><p className="text-muted-foreground">Loading...</p></div>;
    if (!user) return <div className="flex items-center justify-center p-12"><p className="text-muted-foreground">Not authenticated</p></div>;

    const TABS: { id: Tab; label: string }[] = [
        { id: "account", label: "Account" },
        { id: "channel", label: "Channel" },
        { id: "security", label: "Security" },
    ];

    return (
        <div className="p-6 max-w-2xl mx-auto space-y-6">
            <h1 className="text-2xl font-bold">Profile</h1>

            <div className="flex gap-1 border-b">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                            tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                        }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {tab === "account" && (
                <Card>
                    <CardHeader><CardTitle>Account info</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">Email:</span>
                            <span className="text-sm font-medium">{user.email}</span>
                            {user.is_verified && <Badge variant="outline" className="text-xs">Verified</Badge>}
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="username">Username</Label>
                            <div className="flex gap-2">
                                <Input
                                    id="username"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && handleSaveAccount()}
                                />
                                <Button onClick={handleSaveAccount} disabled={savingAccount || username === user.username}>
                                    {savingAccount ? "Saving…" : "Save"}
                                </Button>
                            </div>
                        </div>
                        {accountMsg && (
                            <p className={`text-sm ${accountMsg.ok ? "text-emerald-500" : "text-red-500"}`}>{accountMsg.text}</p>
                        )}
                        {user.created_at && (
                            <p className="text-xs text-muted-foreground">
                                Member since {new Date(user.created_at).toLocaleDateString()}
                            </p>
                        )}
                    </CardContent>
                </Card>
            )}

            {tab === "channel" && (
                <Card>
                    <CardHeader><CardTitle>Channel settings</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                        {!channel ? (
                            <p className="text-sm text-muted-foreground">You don't have a channel yet. Create one from the Studio page.</p>
                        ) : (
                            <>
                                <div className="space-y-1">
                                    <Label htmlFor="channelName">Channel name</Label>
                                    <Input id="channelName" value={channelName} onChange={(e) => setChannelName(e.target.value)} />
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor="channelDesc">Description</Label>
                                    <textarea
                                        id="channelDesc"
                                        value={channelDesc}
                                        onChange={(e) => setChannelDesc(e.target.value)}
                                        rows={4}
                                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                                    />
                                </div>
                                <Button onClick={handleSaveChannel} disabled={savingChannel}>
                                    {savingChannel ? "Saving…" : "Save channel"}
                                </Button>
                                {channelMsg && (
                                    <p className={`text-sm ${channelMsg.ok ? "text-emerald-500" : "text-red-500"}`}>{channelMsg.text}</p>
                                )}
                            </>
                        )}
                    </CardContent>
                </Card>
            )}

            {tab === "security" && (
                <Card>
                    <CardHeader><CardTitle>Change password</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-1">
                            <Label htmlFor="currentPw">Current password</Label>
                            <Input id="currentPw" type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="newPw">New password</Label>
                            <Input id="newPw" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="confirmPw">Confirm new password</Label>
                            <Input id="confirmPw" type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} />
                        </div>
                        <Button onClick={handleChangePassword} disabled={savingPw || !currentPw || !newPw || !confirmPw}>
                            {savingPw ? "Saving…" : "Change password"}
                        </Button>
                        {pwMsg && (
                            <p className={`text-sm ${pwMsg.ok ? "text-emerald-500" : "text-red-500"}`}>{pwMsg.text}</p>
                        )}
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
