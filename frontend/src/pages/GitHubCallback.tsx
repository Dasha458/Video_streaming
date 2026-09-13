import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "@/components/ui/toast/use-toast";

export default function GitHubCallback() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { refreshUser } = useAuth();
    const handled = useRef(false);

    useEffect(() => {
        if (handled.current) return;
        handled.current = true;

        const token = searchParams.get("token");
        if (!token) {
            toast({ title: "GitHub login failed: no token received", variant: "destructive" });
            navigate("/login", { replace: true });
            return;
        }

        localStorage.setItem("token", token);
        refreshUser().then(() => {
            toast({ title: "Logged in with GitHub" });
            navigate("/", { replace: true });
        });
    }, []);

    return (
        <div className="flex min-h-screen items-center justify-center">
            <p className="text-gray-500">Completing GitHub login...</p>
        </div>
    );
}
