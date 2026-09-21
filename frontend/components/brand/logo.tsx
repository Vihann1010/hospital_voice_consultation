"use client";

/**
 * The site's mark.
 *
 * The bundled artwork is the Satya Trauma & Maternity Center logo. A site that
 * has not supplied its own sets HOSPITAL_LOGO=none and gets its name set as a
 * wordmark instead — better plain type than another hospital's logo on the
 * sign-in screen. Until the setting is known nothing is drawn, so the wrong
 * mark is never flashed.
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
import { useModules } from "@/components/dashboard/modules-provider";

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
  const { logo, hospitalName } = useModules();
  if (logo === null) {
    // Reserve the space so the header does not jump when the answer arrives.
    return <span className={cn("inline-block", className)} style={{ width, height }} aria-hidden />;
  }
  if (logo === "none") {
    return (
      <span
        className={cn(
          "inline-flex items-center font-display font-semibold leading-tight",
          variant === "dark" ? "text-white" : "text-pine",
          className
        )}
        style={{ maxWidth: width, fontSize: Math.max(14, Math.round(width / 9)) }}
      >
        {hospitalName ?? ""}
      </span>
    );
  }
  return (
    <Image
      src={variant === "dark" ? "/brand/logo-dark.png" : "/brand/logo.png"}
      alt={hospitalName ?? "Hospital logo"}
      width={width}
      height={height}
      priority={priority}
      className={cn("h-auto select-none", className)}
    />
  );
}
