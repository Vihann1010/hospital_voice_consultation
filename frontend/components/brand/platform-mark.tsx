"use client";

/**
 * The platform's mark, shown beside the hospital's own identity.
 *
 * The hospital is known to its patients by its own name; the platform's mark
 * says what the software is, and stays in second place — behind a thin
 * divider, smaller, never competing with the hospital's logo.
 *
 * A deployment that does not want it builds with NEXT_PUBLIC_PLATFORM_BRAND
 * set to "none" and nothing is drawn.
 *
 * "full" is the whole wordmark, for the sign-in screen. "inline" sits just
 * after the hospital's own name in a header. "credit" is the small
 * "Powered by" line.
 */
import Image from "next/image";
import { cn } from "@/lib/utils";

// The trimmed artwork is 1200 × 249.
const ASPECT = 249 / 1200;

const BRAND = process.env.NEXT_PUBLIC_PLATFORM_BRAND ?? "medicos";

export function PlatformMark({
  variant = "full",
  width = 160,
  className,
}: {
  variant?: "full" | "inline" | "credit";
  width?: number;
  className?: string;
}) {
  if (BRAND !== "medicos") return null;

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
