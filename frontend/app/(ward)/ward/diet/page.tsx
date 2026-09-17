"use client";

import { KitchenSheet } from "@/components/diet/kitchen-sheet";

/** The kitchen's diet sheet at the ward terminal. */
export default function WardDietPage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink">Diet sheet</h1>
        <p className="text-sm text-ink-muted">What each inpatient is served at every meal of the day.</p>
      </div>
      <KitchenSheet />
    </div>
  );
}
