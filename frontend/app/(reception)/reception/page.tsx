"use client";

import { CashCounter } from "@/components/finance/cash-counter";
import { ReceptionCounter } from "@/components/reception/reception-counter";

export default function ReceptionPage() {
  return (
    <div className="space-y-5">
      <ReceptionCounter />
      {/* The cashier's own drawer, on the terminal where the cash actually is. */}
      <CashCounter />
    </div>
  );
}
