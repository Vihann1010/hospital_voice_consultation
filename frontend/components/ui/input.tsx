import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-lg border border-input bg-white px-3 py-2 text-sm text-ink",
        "placeholder:text-ink-faint focus-visible:outline-none focus-visible:border-pine",
        "focus-visible:ring-2 focus-visible:ring-pine/20 disabled:cursor-not-allowed disabled:opacity-50 transition",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";

export { Input };
