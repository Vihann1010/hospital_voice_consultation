/** Chrome for the patient-facing intake app. */
import { Logo } from "@/components/brand/logo";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-pine/10 bg-mint-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <Logo width={172} priority />
          <p className="hidden text-sm text-ink-muted sm:block">
            Trauma &amp; Orthopedics · Maternity &amp; Gynecology
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-8">{children}</main>
      <footer className="mx-auto max-w-5xl px-5 pb-8 pt-4 text-xs text-ink-faint">
        For emergencies, come directly to the hospital emergency department. This assistant
        prepares your visit and does not give medical advice.
      </footer>
    </>
  );
}
