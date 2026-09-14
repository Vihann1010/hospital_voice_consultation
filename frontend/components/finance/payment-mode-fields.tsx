"use client";

/**
 * The fields a payment mode needs, rendered from the server's own spec.
 *
 * Not hardcoded here on purpose. The backend refuses a cheque with no bank
 * name; if this file carried its own opinion about which fields matter, the
 * two would drift and the counter would meet a validation error it could not
 * satisfy. So the shape is fetched, and the screen renders whatever the rule
 * currently is.
 *
 * A mode with nothing to record — cash, or the wallet — renders nothing at
 * all rather than an empty box, because a labelled space that never needs
 * filling reads like something is missing.
 */
import { useEffect, useState } from "react";
import { staffApi } from "@/lib/staffApi";
import type { PaymentMode, PaymentModeSpec } from "@/lib/emrTypes";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Fetched once and shared: the spec is the same for every screen. */
let cached: Promise<PaymentModeSpec[]> | null = null;

export function usePaymentModes(): PaymentModeSpec[] {
  const [specs, setSpecs] = useState<PaymentModeSpec[]>([]);
  useEffect(() => {
    if (!cached) {
      cached = staffApi
        .paymentModes()
        .then((result) => result.modes)
        // A failure here must not block taking money. The counter falls back
        // to no extra fields, and the server still enforces the rule.
        .catch(() => []);
    }
    void cached.then(setSpecs);
  }, []);
  return specs;
}

export function PaymentModeFields({
  mode,
  values,
  onChange,
  className,
}: {
  mode: PaymentMode;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
  className?: string;
}) {
  const specs = usePaymentModes();
  const spec = specs.find((item) => item.mode === mode);
  const fields = spec?.fields ?? [];

  if (fields.length === 0) return null;

  return (
    <div className={cn("grid gap-1.5 sm:grid-cols-2", className)}>
      {fields.map((field) => (
        <div key={field.name}>
          <label
            className="text-[11px] uppercase tracking-wide text-ink-faint"
            htmlFor={`pm-${field.name}`}
          >
            {field.label}
            {!field.required && <span className="ml-1 normal-case">(optional)</span>}
          </label>
          <Input
            id={`pm-${field.name}`}
            value={values[field.name] ?? ""}
            inputMode={field.digits ? "numeric" : undefined}
            maxLength={field.digits ?? undefined}
            onChange={(event) =>
              onChange({ ...values, [field.name]: event.target.value })
            }
            className="mt-0.5 h-9 text-sm"
          />
        </div>
      ))}
    </div>
  );
}

/**
 * Drop the blanks before sending.
 *
 * An optional field left empty must not travel as "", which the server reads
 * as a value that was entered and is wrong, rather than one that was skipped.
 */
export function cleanModeDetails(
  values: Record<string, string>
): Record<string, string> | null {
  const cleaned = Object.fromEntries(
    Object.entries(values)
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value !== "")
  );
  return Object.keys(cleaned).length > 0 ? cleaned : null;
}
