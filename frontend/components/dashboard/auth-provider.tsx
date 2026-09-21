"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchCurrentUser, logout as doLogout } from "@/lib/auth";
import type { User } from "@/lib/types/core";
import { useModules } from "@/components/dashboard/modules-provider";

type Role = User["role"];

/**
 * Where each role belongs when it signs in or reaches a shell it cannot use.
 *
 * One map rather than a fallback per layout: with a fallback each, a nurse
 * sent from the dashboard to reception was sent straight back again, because
 * neither shell admitted her and each pointed at the other.
 *
 * A nurse's home is the ward, where there is one. A clinic with no beds has
 * its nurse on the voice intake terminal instead, taking vitals and sitting
 * the patient through the intake.
 */
export function homeFor(role: Role, hasWards = true): string {
  if (role === "nurse") return hasWards ? "/ward" : "/intake";
  if (role === "lab") return "/lab";
  if (role === "reception" || role === "supervisor") return "/reception";
  return "/dashboard";
}

interface AuthState {
  user: User | null;
  loading: boolean;
  logout: () => void;
}

/** Whether this site has wards, for homeFor. Assumed so until the site's
 *  configuration has answered, so a hospital's nurse is never sent away
 *  from the ward while it loads. */
export function useHasWards(): boolean {
  const { enabled, has } = useModules();
  return enabled === null || has("ipd");
}

const AuthContext = createContext<AuthState>({ user: null, loading: true, logout: doLogout });

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({
  children,
  allow,
  fallbackPath = "/login",
}: {
  children: React.ReactNode;
  /** Roles permitted in this shell. Omit to allow any signed-in user. */
  allow?: Role[];
  /** Where a signed-in user of the wrong role is sent instead. */
  fallbackPath?: string;
}) {
  const router = useRouter();
  // Read through a ref: the answer can arrive after this shell mounts, and
  // it should not re-run the sign-in check when it does.
  const hasWards = useHasWards();
  const hasWardsRef = useRef(hasWards);
  hasWardsRef.current = hasWards;
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetchCurrentUser()
      .then((value) => {
        if (!active) return;
        if (!value) {
          router.replace("/login");
          return;
        }
        // Convenience, not security: the API enforces permissions on every
        // request. This only keeps someone from landing on a shell whose
        // every panel would return 403.
        if (allow && !allow.includes(value.role)) {
          const home = homeFor(value.role, hasWardsRef.current);
          // The role's own home, unless that is this very shell — then the
          // layout's fallback, so a misconfigured allow list cannot loop.
          router.replace(
            typeof window !== "undefined" && window.location.pathname.startsWith(home)
              ? fallbackPath
              : home
          );
          return;
        }
        setUser(value);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [router, allow, fallbackPath]);

  return (
    <AuthContext.Provider value={{ user, loading, logout: doLogout }}>{children}</AuthContext.Provider>
  );
}
