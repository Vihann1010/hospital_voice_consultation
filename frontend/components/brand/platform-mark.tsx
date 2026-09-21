"use client";

/**
 * The platform's mark, shown beside the site's own identity.
 *
 * A clinic running MedicOS is known to its patients by its own name; the
 * platform's mark says what the software is, and stays in second place. A
 * site configured without it (PLATFORM_BRAND=none) draws nothing here.
 *
 * "full" is the whole wordmark, for the sign-in screen. "inline" sits just
 * after the site's own name in a header, behind a thin divider. "credit" is
 * the small "Powered by" line.
 */
import Image from "next/image";
import { cn } from "@/lib/utils";
import { useModules } from "@/components/dashboard/modules-provider";

// The trimmed artwork is 1200 × 249.
const ASPECT = 249 / 1200;

export function PlatformMark({
  variant = "full",
  width = 160,
  className,
}: {
  variant?: "full" | "inline" | "credit";
  width?: number;
  className?: string;
}) {
  const { platform } = useModules();
  if (platform !== "medicos") return null;

  const image = (
    <Image
      src="/brand/medicos.png"
      alt="MedicOS"
      width={width}
      height={Math.round(width * ASPECT)}
      className="h-auto select-none"
    />
  );

  if (variant === "full") return <span className={cn("inline-block", className)}>{image}</span>;

  if (variant === "inline") {
    return (
      <span className={cn("inline-flex shrink-0 items-center gap-3", className)}>
        <span className="h-6 w-px bg-pine/15" aria-hidden />
        {image}
      </span>
    );
  }

  return (
    <span className={cn("inline-flex items-center gap-2 rounded-md bg-white px-2 py-1", className)}>
      <span className="text-[10px] uppercase tracking-[0.14em] text-ink-faint">Powered by</span>
      {image}
    </span>
  );
}
