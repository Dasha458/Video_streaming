import {cn} from "@/lib/utils"
import {Button} from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import {Input} from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useState } from "react";
import { toast } from "react-hot-toast";
import { checkUserExists, getGithubAuthUrl } from "@api/authApi";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { getApiErrorMessage } from "@/utils/apiError";
import { PasswordInput } from "@/components/ui/PasswordInput";

export function RegisterForm({
                                 className,
                                 ...props
}: React.ComponentProps<"div">) {
    const navigate = useNavigate();
    const { register } = useAuth();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordRepeat, setPasswordRepeat] = useState("");
    const [loading, setLoading] = useState(false);
    const [githubLoading, setGithubLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleGithubRegister = async () => {
        try {
            setGithubLoading(true);
            const url = await getGithubAuthUrl();
            window.location.href = url;
        } catch {
            toast.error("Failed to connect to GitHub");
            setGithubLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!email || !password) {
            setError("All fields are required.");
            return;
        }

        if (password !== passwordRepeat) {
            setError("Passwords do not match.");
            return;
        }

        if (password.length < 8) {
            setError("Password must be at least 8 characters long.");
            return;
        }

        const { usernameExists, emailExists } = await checkUserExists(email.split("@")[0], email);
        if (emailExists) {
            setError("This email is already registered.");
            return;
        }
        if (usernameExists) {
            setError("This username is already taken. Try a different email.");
            return;
        }

        try {
            setLoading(true);
            await register(email, password);
            toast.success("Registration successful");
            navigate("/");
        } catch (err: unknown) {
            setError(getApiErrorMessage(err, "Registration failed. Please try again."));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={cn("flex flex-col gap-6", className)} {...props}>
            <Card>
                <CardHeader className="text-center">
                    <CardTitle className="text-xl">Create an account</CardTitle>
                    <CardDescription>
                        Enter your email below to create your account
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit}>
                        <div className="grid gap-6">
                            <div className="flex flex-col gap-4">
                                <div className="grid gap-6">
                                    <div className="grid gap-3">
                                        <Label htmlFor="email">Email</Label>
                                        <Input
                                            id="email"
                                            type="email"
                                            placeholder="m@example.com"
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                        />
                                    </div>
                                    <div className="grid gap-3">
                                        <Label htmlFor="password">Password</Label>
                                        <PasswordInput
                                            id="password"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            required
                                        />
                                        <Label htmlFor="password-repeat">Repeat password</Label>
                                        <PasswordInput
                                            id="password-repeat"
                                            value={passwordRepeat}
                                            onChange={(e) => setPasswordRepeat(e.target.value)}
                                            required
                                        />
                                    </div>
                                    {error && (
                                        <p className="text-sm text-destructive text-center">{error}</p>
                                    )}
                                    <Button type="submit" className="w-full" disabled={loading}>
                                        {loading ? "Registering..." : "Register"}
                                    </Button>
                                </div>
                                <div
                                    className="after:border-border relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t">
                                <span className="bg-card text-muted-foreground relative z-10 px-2">
                                  Or continue with
                                </span>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="w-full"
                                    onClick={handleGithubRegister}
                                    disabled={githubLoading}
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                                        <path
                                            fillRule="evenodd"
                                            d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.02c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.1-.76.09-.75.09-.75 1.22.09 1.86 1.26 1.86 1.26 1.08 1.85 2.84 1.32 3.54 1.01.11-.78.42-1.32.76-1.62-2.67-.3-5.47-1.34-5.47-5.97 0-1.32.47-2.39 1.24-3.23-.13-.3-.54-1.51.12-3.15 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 013 0c2.28-1.55 3.3-1.23 3.3-1.23.66 1.64.25 2.85.12 3.15.77.84 1.24 1.91 1.24 3.23 0 4.64-2.81 5.67-5.49 5.97.43.37.82 1.1.82 2.22v3.29c0 .32.22.69.82.58A12.01 12.01 0 0024 12c0-6.63-5.37-12-12-12z"
                                            clipRule="evenodd"
                                        />
                                    </svg>
                                    {githubLoading ? "Redirecting..." : "Register with Github"}
                                </Button>
                            </div>
                            <div
                                className="text-muted-foreground *:[a]:hover:text-primary text-center text-xs text-balance *:[a]:underline *:[a]:underline-offset-4">
                                By clicking continue, you agree to our <a href="/terms">Terms of Service</a>{" "}
                                and <a href="/privacy">Privacy Policy</a>.
                            </div>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}
