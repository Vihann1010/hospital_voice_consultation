"use client";

/**
 * The page a patient's phone opens after scanning the nurse's QR code.
 *
 * Everything about it assumes a phone held one-handed in a waiting room by
 * somebody who has never seen this application and will never see it again:
 * no login, no navigation, one job on the screen, and large touch targets.
 *
 * There is deliberately nothing here that reads patient data. The token in
 * the URL grants exactly one capability — attach a file to one consultation
 * — so a code photographed by the wrong person leaks nothing, and the page
 * cannot become a way to look someone up.
 */
import { useParams } from "next/navigation";
import { Camera, ShieldCheck } from "lucide-react";
import { PreviousReportsUpload } from "@/components/patient/previous-reports-upload";

export default function PhoneUploadPage() {
  // `useParams`, matching every other dynamic route here. This is Next 14,
  // where params is a plain object — the Promise form belongs to 15 and
  // throws "unsupported type was passed to use()".
  const { token } = useParams<{ token: string }>();

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col gap-5 bg-mint px-4 py-6">
      <header className="text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-pine">
          <Camera className="h-5 w-5 text-white" />
        </div>
        <h1 className="mt-3 font-display text-xl font-semibold text-pine">
          Add your old reports
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Photograph any prescriptions, blood tests or scans you have brought with
          you. The doctor will see them before you go in.
        </p>
      </header>

      <div className="rounded-2xl bg-white p-4 shadow-card">
        <PreviousReportsUpload sessionToken={token} bare />
      </div>

      <p className="flex items-start gap-2 px-1 text-[11px] leading-relaxed text-ink-faint">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        This link works for a few minutes and only lets you add files to today&apos;s
        visit. It shows nobody&apos;s records, including your own. Ask the desk for a
        fresh code if it stops working.
      </p>
    </main>
  );
}
