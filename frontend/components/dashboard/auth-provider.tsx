"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchCurrentUser, logout as doLogout } from "@/lib/auth";
import type { User } from "@/lib/types/core";

type Role = User["role"];

/**
 * Where each role belongs when it signs in or reaches a shell it cannot use.
 *
 * One map rather than a fallback per layout: with a fallback each, a nurse
 * sent from the dashboard to reception was sent straight back again, because
 * neither shell admitted her and each pointed at the other.
 */
export function homeFor(role: Role): string {
  if (role === "nurse") return "/ward";
  if (role === "lab") return "/lab";
  if (role === "reception" || role === "supervisor") return "/reception";
  return "/dashboard";
}

interface AuthState {
  user: User | null;
  loading: boolean;
  logout: () => void;
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
          const home = homeFor(value.role);
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
