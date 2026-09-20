"use client";

/**
 * Which optional modules this installation runs.
 *
 * Read from the API rather than from a build-time variable, because the API is
 * where the switch actually lives: a disabled module's endpoints are never
 * registered. Two copies of that decision — one in the backend environment,
 * one baked into the frontend bundle — would eventually disagree, and the way
 * that disagreement shows up is a menu item that leads to a 404.
 *
 * The answer is cached in localStorage so the sidebar draws the right shape on
 * every load after the first. Until it is known, a module-gated item is not
 * shown: offering a ward board that turns out not to exist is worse than
 * showing it a moment late.
 */
import { createContext, useContext, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

export const MODULES = [
  "laboratory",
  "ipd",
  "diet",
  "theatre",
  "insurance",
  "room_charges",
] as const;

export type ModuleName = (typeof MODULES)[number];

const CACHE_KEY = "satya_modules";

interface ModuleState {
  /** Null until the first answer arrives — not "none". */
  enabled: ModuleName[] | null;
  hospitalName: string | null;
  /** False while unknown, so nothing is offered that may not exist. */
  has: (module: ModuleName) => boolean;
}

const ModuleContext = createContext<ModuleState>({
  enabled: null,
  hospitalName: null,
  has: () => false,
});

export function useModules() {
  return useContext(ModuleContext);
}

function readCache(): { modules: ModuleName[]; hospital_name: string } | null {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // Private windows and cleared site data both land here; it is a cache.
    return null;
  }
}

export function ModulesProvider({ children }: { children: React.ReactNode }) {
  const cached = typeof window === "undefined" ? null : readCache();
  const [enabled, setEnabled] = useState<ModuleName[] | null>(cached?.modules ?? null);
  const [hospitalName, setHospitalName] = useState<string | null>(
    cached?.hospital_name ?? null
  );

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/v1/config`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active || !data) return;
        setEnabled(data.modules ?? []);
        setHospitalName(data.hospital_name ?? null);
        try {
          window.localStorage.setItem(CACHE_KEY, JSON.stringify(data));
        } catch {
          // Cache only; the fetch above is the source of truth.
        }
      })
      .catch(() => {
        // Offline or the API is down. Whatever was cached stands; if nothing
        // was, module screens stay hidden until it answers.
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <ModuleContext.Provider
      value={{
        enabled,
        hospitalName,
        has: (module) => enabled !== null && enabled.includes(module),
      }}
    >
      {children}
    </ModuleContext.Provider>
  );
}
