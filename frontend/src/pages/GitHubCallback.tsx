import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "@/components/ui/toast/use-toast";

/**
 * Landing page for the GitHub OAuth redirect. The backend has already set the
 * httpOnly session cookie on that redirect, so there is nothing to read from
 * the URL -- we just ask the backend who we are.
 */
export default function GitHubCallback() {
    const navigate = useNavigate();
    const { refreshUser } = useAuth();
    const handled = useRef(false);

    useEffect(() => {
        if (handled.current) return;
        handled.current = true;

        refreshUser().then((user) => {
            if (user) {
                toast({ title: "Logged in with GitHub" });
                navigate("/", { replace: true });
            } else {
                toast({ title: "GitHub login failed", variant: "destructive" });
                navigate("/login", { replace: true });
            }
        });
    }, []);

    return (
        <div className="flex min-h-screen items-center justify-center">
            <p className="text-gray-500">Completing GitHub login...</p>
        </div>
    );
}
