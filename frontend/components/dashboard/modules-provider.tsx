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

/** What this site calls the theatre module. A hospital operates in a theatre;
 *  a clinic doing fifteen-minute scopes does procedures in a suite, and calling
 *  that screen "Theatre" sends staff looking for an operating list they do not
 *  have. Only the words differ — the records and the rules are identical. */
export type TheatreVocabulary = "theatre" | "procedures";

export const THEATRE_WORDS: Record<TheatreVocabulary, {
  board: string; setup: string; room: string; caseWord: string;
}> = {
  theatre: {
    board: "Theatre",
    setup: "Operation list",
    room: "Theatres",
    caseWord: "operation",
  },
  procedures: {
    board: "Procedures",
    setup: "Procedure list",
    room: "Procedure rooms",
    caseWord: "procedure",
  },
};

interface ModuleState {
  /** Null until the first answer arrives — not "none". */
  enabled: ModuleName[] | null;
  hospitalName: string | null;
  /** False while unknown, so nothing is offered that may not exist. */
  has: (module: ModuleName) => boolean;
  /** The site's words for the theatre module; "theatre" until told otherwise. */
  words: (typeof THEATRE_WORDS)[TheatreVocabulary];
}

const ModuleContext = createContext<ModuleState>({
  enabled: null,
  hospitalName: null,
  has: () => false,
  words: THEATRE_WORDS.theatre,
});

export function useModules() {
  return useContext(ModuleContext);
}

function readCache(): {
  modules: ModuleName[];
  hospital_name: string;
  theatre_vocabulary?: TheatreVocabulary;
} | null {
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
  const [vocabulary, setVocabulary] = useState<TheatreVocabulary>(
    cached?.theatre_vocabulary ?? "theatre"
  );

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/v1/config`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active || !data) return;
        setEnabled(data.modules ?? []);
        setHospitalName(data.hospital_name ?? null);
        setVocabulary(data.theatre_vocabulary === "procedures" ? "procedures" : "theatre");
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
        words: THEATRE_WORDS[vocabulary],
      }}
    >
      {children}
    </ModuleContext.Provider>
  );
}
