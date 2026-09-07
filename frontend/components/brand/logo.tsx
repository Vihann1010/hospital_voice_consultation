"use client";

/**
 * The Satya Trauma & Maternity Center mark.
 *
 * The logo is always placed on white — on the navy sidebar and sign-in panel
 * it sits inside a white strip or card. Its blue mark is close in value to the
 * navy chrome, and recolouring the mark to survive a dark background would
 * mean altering the hospital's logo, so the surface changes instead.
 *
 * The "dark" variant (white wordmark, transparent background) is retained for
 * any future placement where a white panel is not possible.
 */
import Image from "next/image";
import { cn } from "@/lib/utils";

export function Logo({
  variant = "light",
  className,
  width = 168,
  priority = false,
}: {
  /** "light" for light backgrounds, "dark" for navy surfaces. */
  variant?: "light" | "dark";
  className?: string;
  width?: number;
  priority?: boolean;
}) {
  const height = Math.round((width * 154) / 316); // preserve the logo's aspect
  return (
    <Image
      src={variant === "dark" ? "/brand/logo-dark.png" : "/brand/logo.png"}
      alt="Satya Trauma & Maternity Center"
      width={width}
      height={height}
      priority={priority}
      className={cn("h-auto select-none", className)}
    />
  );
}
