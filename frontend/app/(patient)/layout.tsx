/** Chrome for the patient-facing intake app. */
import { Logo } from "@/components/brand/logo";
import { ModulesProvider } from "@/components/dashboard/modules-provider";
import { SiteDepartments } from "@/components/brand/site-departments";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <ModulesProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <header className="border-b border-pine/10 bg-mint-card/80 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
            <Logo width={172} priority />
            <SiteDepartments className="hidden text-sm text-ink-muted sm:block" />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto px-5 py-8">
          <div className="mx-auto max-w-5xl">{children}</div>
        </main>
        <footer className="mx-auto w-full max-w-5xl shrink-0 px-5 pb-4 pt-3 text-xs text-ink-faint">
          For emergencies, come directly to the hospital emergency department. This assistant
          prepares your visit and does not give medical advice.
        </footer>
      </div>
    </ModulesProvider>
  );
}
