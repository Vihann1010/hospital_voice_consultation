"use client";

/**
 * The appointment desk: the day's queue on the left, booking on the right.
 *
 * Side by side rather than on two pages, because the two are one
 * conversation — a patient rings to ask when they can come, and the clerk
 * needs to see how full today already is while answering.
 */
import { useCallback, useRef, useState } from "react";
import { BookingPanel } from "@/components/appointments/booking-panel";
import { QueueBoard } from "@/components/appointments/queue-board";

export default function AppointmentsPage() {
  // Bumping this key remounts the board after a booking, so a slot taken on
  // the right appears on the left without waiting for the refresh tick.
  const [boardKey, setBoardKey] = useState(0);
  const bookingRef = useRef<HTMLDivElement>(null);

  const focusBooking = useCallback(() => {
    bookingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    bookingRef.current?.querySelector("input")?.focus();
  }, []);

  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold text-pine">Appointments</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Today&apos;s queue, and the diary for the days ahead.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_400px]">
        <QueueBoard key={boardKey} onBook={focusBooking} />
        <div ref={bookingRef}>
          <BookingPanel onBooked={() => setBoardKey((value) => value + 1)} />
        </div>
      </div>
    </div>
  );
}
