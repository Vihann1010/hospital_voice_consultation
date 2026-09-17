"use client";

/**
 * The shortcuts that mean the same thing everywhere.
 *
 * Carried over from the old system, because they are the keys staff already
 * know. Three things had to change, and the reasons are the browser and the
 * shape of this application rather than preference:
 *
 *   F1  new patient       registered by the counter screen itself, so it
 *                         focuses the form rather than reloading the page
 *                         someone is already standing on
 *   F2  OPD registration  kept
 *   F3  IPD admission     points at the ward board; the admission form lives
 *                         inside it
 *   F4  lab registration  not bound — the lab module arrives in Part 4, and a
 *                         hint promising a key that does nothing is worse
 *                         than no hint
 *   F5  patient diary     kept, aimed at whichever patient list this shell
 *                         can actually open
 *   Ctrl+N                unavailable: the browser opens a new window on
 *                         Ctrl+N and a page cannot intercept it. The old
 *                         client was a desktop app and could.
 *   Esc                   back one level, as before
 *
 * The targets differ per shell because the shells have different permissions.
 * Sending a receptionist to the ward board would bounce them straight back to
 * the counter, which reads as the shortcut being broken.
 */
import { usePathname, useRouter } from "next/navigation";
import { useShortcut } from "@/components/keyboard/keyboard-provider";

export type ShortcutVariant = "clinical" | "reception";

export function GlobalShortcuts({ variant }: { variant: ShortcutVariant }) {
  const router = useRouter();
  const pathname = usePathname();

  const counter = "/reception";
  const patients = variant === "reception" ? "/reception/patients" : "/patients";
  const appointments = "/reception/appointments";

  useShortcut("F2", "Reception counter", () => router.push(counter), { order: 2 });

  useShortcut("F3", "Ward board", () => router.push("/ipd"), {
    order: 3,
    // Reception can open the ward board, but it is not part of the counter's
    // work and the key is more useful left unbound there than as a surprise.
    enabled: variant === "clinical",
  });

  useShortcut("F5", "Find a patient", () => router.push(patients), { order: 5 });

  // Not a key the old system used — it had no appointment book. Alt is the
  // only modifier the browser leaves alone, and the remaining function keys
  // are spoken for by modules that arrive in later parts.
  useShortcut("alt+a", "Appointments", () => router.push(appointments), { order: 6 });

  // "What does this patient owe" is asked constantly at a counter, and the
  // answer used to take three screens. F6 is free — the old system stopped
  // at F5.
  useShortcut("F6", "Patient diary", () => router.push("/reception/diary"), {
    order: 7,
  });

  // Back one level, matching the old system. On a shell's home screen there is
  // nowhere above to go, so this does nothing rather than ejecting someone
  // out of the terminal they are working in.
  useShortcut(
    "Escape",
    "Back",
    () => {
      if (pathname.split("/").filter(Boolean).length > 1) router.back();
    },
    { order: 90 }
  );

  return null;
}
