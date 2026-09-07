import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-pine text-mint",
        secondary: "border-transparent bg-mint text-pine",
        outline: "border-border text-ink-muted",
        success: "border-transparent bg-pine/10 text-pine",
        warning: "border-transparent bg-marigold/20 text-marigold-deep",
        danger: "border-transparent bg-clay/12 text-clay",
        ai: "border-marigold/40 bg-marigold/10 text-marigold-deep",
      },
      size: { default: "", sm: "px-2 py-0 text-[10px]" },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, size }), className)} {...props} />;
}

export { Badge, badgeVariants };
