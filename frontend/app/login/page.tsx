"use client";

import { homeFor } from "@/components/dashboard/auth-provider";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Lock } from "lucide-react";
import { fetchCurrentUser, login } from "@/lib/auth";
import { Logo } from "@/components/brand/logo";
import { PlatformMark } from "@/components/brand/platform-mark";
import { useModules } from "@/components/dashboard/modules-provider";
import { SiteDepartments } from "@/components/brand/site-departments";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  // An explicit ?next wins — it is how the middleware returns someone to
  // the page they were trying to reach. Otherwise the landing page depends
  // on the role, because "the dashboard" means different work to a doctor
  // and to the front desk.
  const nextPath = params.get("next");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      let destination = nextPath;
      if (!destination) {
        const user = await fetchCurrentUser();
        destination = user ? homeFor(user.role) : "/dashboard";
      }
      router.replace(destination);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="email">Work email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@your-clinic.in"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
          required
        />
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-clay/30 bg-clay/5 px-3 py-2 text-sm text-clay">
          {error}
        </p>
      )}

      <Button type="submit" disabled={submitting} className="w-full" size="lg">
        {submitting ? <Loader2 className="animate-spin" /> : <Lock />}
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

function SiteCity({ className }: { className?: string }) {
  const { hospitalCity } = useModules();
  // Read from the site's configuration; it used to say one hospital's city.
  return hospitalCity ? <p className={className}>{hospitalCity}</p> : null;
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between bg-pine-deep p-12 lg:flex">
        <div>
          {/* Same reasoning as the sidebar: the logo keeps its own colours on
              white rather than being recoloured to survive a navy panel. */}
          <div className="inline-block rounded-xl bg-white px-6 py-5 shadow-lift">
            <Logo width={200} priority />
          </div>
          <SiteCity className="mt-3 text-[11px] uppercase tracking-[0.18em] text-mint/45" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <h2 className="max-w-md font-display text-4xl font-semibold leading-[1.1] text-mint">
            Every patient, prepared before they walk in.
          </h2>
          <p className="mt-4 max-w-sm text-[15px] leading-relaxed text-mint/60">
            Voice intake gathers the history, the clinical pipeline organises it, and the copilot
            surfaces what deserves your attention. You decide everything that follows.
          </p>
        </motion.div>

        {/* Read from the site's configuration. It used to name one hospital's
            two consultants, on every site's sign-in page. */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SiteDepartments className="text-xs text-mint/35" />
          <PlatformMark variant="credit" width={96} />
        </div>
      </div>

      {/* Form panel */}
      <div className="flex w-full items-center justify-center bg-mint px-5 py-12 lg:w-1/2">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="w-full max-w-sm"
        >
          <div className="mb-8 lg:hidden">
            <Logo width={180} priority />
          </div>
          <PlatformMark width={150} className="mb-6 hidden lg:inline-block" />

          <h1 className="font-display text-2xl font-semibold text-pine">Clinical console</h1>
          <p className="mb-6 mt-1 text-sm text-ink-muted">
            Sign in with your staff account to view today&apos;s patients.
          </p>

          <Suspense fallback={<div className="h-64" />}>
            <LoginForm />
          </Suspense>

          <p className="mt-6 text-xs leading-relaxed text-ink-faint">
            Access is limited to authorised hospital staff. All patient records opened here are
            attributed to your account.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
