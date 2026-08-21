"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchCurrentUser, logout as doLogout } from "@/lib/auth";
import type { User } from "@/lib/types";

type Role = User["role"];

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
          router.replace(fallbackPath);
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
