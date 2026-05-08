import { useEffect, useState } from "react";
import { SidebarIcon, Video, Bell, Upload, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSidebar } from "@/components/ui/sidebar";
import { NavUser } from "@/components/nav-user";
import { ModeToggle } from "@/components/mode-toggle";
import { SearchForm } from "@/components/search-form";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";
import clientApi from "@api/clientApi";

export function SiteHeader() {
    const { toggleSidebar } = useSidebar();
    const { user, isAuthenticated, isLoading } = useAuth();
    const [unreadCount, setUnreadCount] = useState(0);

    useEffect(() => {
        if (!isAuthenticated) { setUnreadCount(0); return; }
        const fetch = () => {
            clientApi.get<{ count: number }>("/api/notifications/unread-count")
                .then((r) => setUnreadCount(r.data.count ?? 0))
                .catch(() => {});
        };
        fetch();
        const id = setInterval(fetch, 60_000);
        return () => clearInterval(id);
    }, [isAuthenticated]);

    const userData = isAuthenticated && user
        ? { name: user.username, email: user.email, avatar: "" }
        : null;

    return (
        <header className="fixed top-0 left-0 right-0 z-50 h-[var(--header-height)] bg-background border-b border-border flex items-center px-4 gap-4">
            {/* LEFT: Hamburger + Logo */}
            <div className="flex items-center gap-2 flex-shrink-0">
                <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-full h-9 w-9"
                    onClick={toggleSidebar}
                >
                    <SidebarIcon className="h-5 w-5" />
                </Button>
                <Link to="/" className="flex items-center gap-1.5 ml-1">
                    <div className="flex h-7 w-7 items-center justify-center rounded bg-red-600">
                        <Video className="h-4 w-4 text-white" />
                    </div>
                    <span className="font-bold text-base tracking-tight hidden sm:block">StreamHub</span>
                </Link>
            </div>

            {/* CENTER: Search */}
            <div className="flex-1 flex justify-center min-w-0 max-w-2xl mx-auto">
                <SearchForm className="w-full" />
            </div>

            {/* RIGHT: Actions + User */}
            <div className="flex items-center gap-1 flex-shrink-0">
                <ModeToggle />
                {isAuthenticated && (
                    <>
                        <Button variant="ghost" size="icon" className="rounded-full h-9 w-9" asChild>
                            <Link to="/upload" title="Upload">
                                <Upload className="h-5 w-5" />
                            </Link>
                        </Button>
                        <Button variant="ghost" size="icon" className="relative rounded-full h-9 w-9" asChild>
                            <Link to="/notifications" title="Notifications">
                                <Bell className="h-5 w-5" />
                                {unreadCount > 0 && (
                                    <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white leading-none">
                                        {unreadCount > 99 ? "99+" : unreadCount}
                                    </span>
                                )}
                            </Link>
                        </Button>
                    </>
                )}
                {isLoading ? null : userData ? (
                    <NavUser user={userData} />
                ) : (
                    <Button variant="outline" size="sm" className="rounded-full gap-1.5 border-blue-500 text-blue-500 hover:bg-blue-500/10" asChild>
                        <Link to="/login">
                            <UserCircle className="h-4 w-4" />
                            Sign in
                        </Link>
                    </Button>
                )}
            </div>
        </header>
    );
}
