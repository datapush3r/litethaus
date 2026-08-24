import { Box } from "lucide-react";

// Icons from https://github.com/homarr-labs/dashboard-icons, served via jsdelivr.
const ICON_BASE =
    "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@main/svg";

interface StackIconProps {
    icon?: unknown;
    size?: number;
    className?: string;
}

export function StackIcon({ icon, size = 18, className }: StackIconProps) {
    const slug = typeof icon === "string" ? icon.trim() : "";

    if (!slug) {
        return (
            <Box
                size={size}
                className={
                    className ??
                    "shrink-0 text-neutral-400 dark:text-neutral-500"
                }
            />
        );
    }

    // Rendered as an <object> (not <img>): some SVGs (e.g. calibre) carry raw
    // path coordinates far outside their viewBox, which makes <img> mis-size
    // them; CSS containment on the <object> forces a uniform square.
    return (
        <object
            type="image/svg+xml"
            data={`${ICON_BASE}/${slug}.svg`}
            aria-hidden
            className={className ?? "shrink-0 overflow-hidden"}
            style={{ width: size, height: size }}
        >
            <Box size={size} />
        </object>
    );
}
