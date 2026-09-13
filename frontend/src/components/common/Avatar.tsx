import { useState } from "react";
import { cn } from "@/lib/utils";

interface AvatarProps {
    src?: string | null;
    name?: string;
    size: number;
    /** "gradient" is the larger profile-style avatar used on channel pages. */
    variant?: "default" | "gradient";
    /** Adds the 4px background-colored ring used around channel/profile avatars. */
    bordered?: boolean;
    className?: string;
}

/**
 * Single shared avatar: an image when `src` loads, otherwise the first
 * letter of `name` in a colored circle. Falls back automatically on a
 * broken/missing image via onError, not just a missing `src`.
 */
export function Avatar({ src, name, size, variant = "default", bordered = false, className }: AvatarProps) {
    const [imgError, setImgError] = useState(false);
    const initial = (name ?? "?").charAt(0).toUpperCase();
    const borderClass = bordered ? "border-4 border-background" : "";

    if (src && !imgError) {
        return (
            <img
                src={src}
                alt={name}
                width={size}
                height={size}
                className={cn("rounded-full object-cover shrink-0", borderClass, className)}
                style={{ width: size, height: size }}
                loading="lazy"
                decoding="async"
                onError={() => setImgError(true)}
            />
        );
    }

    if (variant === "gradient") {
        return (
            <div
                className={cn(
                    "rounded-full flex items-center justify-center font-bold text-white shrink-0",
                    borderClass,
                    className,
                )}
                style={{
                    width: size,
                    height: size,
                    fontSize: size * 0.38,
                    background: "linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary)/0.6))",
                }}
            >
                {initial}
            </div>
        );
    }

    return (
        <div
            className={cn(
                "rounded-full bg-muted flex items-center justify-center shrink-0 text-xs font-semibold text-muted-foreground",
                borderClass,
                className,
            )}
            style={{ width: size, height: size }}
        >
            {initial}
        </div>
    );
}
