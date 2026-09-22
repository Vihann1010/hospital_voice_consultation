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
import { DEPARTMENTS as ALL_DEPARTMENTS, type Department } from "@/lib/types/core";

export const MODULES = [
  "laboratory",
  "ipd",
  "diet",
  "theatre",
  "insurance",
  "room_charges",
  "radiology",
] as const;

export type ModuleName = (typeof MODULES)[number];

const CACHE_KEY = "medicos_site";

/** What this site calls the theatre module. A hospital operates in a theatre;
 *  a clinic doing fifteen-minute scopes does procedures in a suite, and calling
 *  that screen "Theatre" sends staff looking for an operating list they do not
 *  have. Only the words differ — the records and the rules are identical. */
export type TheatreVocabulary = "theatre" | "procedures";

export interface TheatreWords {
  board: string;
  setup: string;
  room: string;
  caseWord: string;
  /** The booking dialog and the case screen. */
  bookTitle: string;
  operation: string;
  operationPlaceholder: string;
  operationHint: string;
  roomOne: string;
  operator: string;
  anaesthetist: string;
  anaesthesia: string;
  times: string;
  slip: string;
  notes: string;
  checklist: string;
  durations: readonly [string, string, string];
  /** Whether the booking asks for a side. A scope has none, and asking
   *  invites a click on "Left" to get past the form. When it is not asked the
   *  booking records "Not applicable", said by the site's configuration. */
  askSide: boolean;
  /** The anaesthesia choices offered, or null for the whole list. */
  anaesthesiaChoices: readonly string[] | null;
  /** The status a case has between wheel-in and wheel-out. */
  inRoom: string;
  /** Times this kind of case never has. A scope has no incision and no
   *  closure; offering the buttons invites times that mean nothing. */
  skipMilestones: readonly string[];
  /** Whether the booking asks which teeth (FDI numbers). */
  askTeeth: boolean;
}

export const THEATRE_WORDS: Record<TheatreVocabulary, TheatreWords> = {
  theatre: {
    board: "Theatre",
    setup: "Operation list",
    room: "Theatres",
    caseWord: "operation",
    bookTitle: "Book for theatre",
    operation: "Operation",
    operationPlaceholder: "Total knee replacement…",
    operationHint: "Search the operation list, or type a procedure not on it",
    roomOne: "Theatre",
    operator: "Surgeon",
    anaesthetist: "Anaesthetist",
    anaesthesia: "Anaesthesia",
    times: "Theatre times",
    slip: "Surgery slip",
    notes: "Notes for theatre",
    checklist: "pre-op checklist",
    durations: ["In theatre", "Surgery", "Anaesthesia"],
    askSide: true,
    anaesthesiaChoices: null,
    inRoom: "In theatre",
    skipMilestones: [],
    askTeeth: false,
  },
  procedures: {
    board: "Procedures",
    setup: "Procedure list",
    room: "Procedure rooms",
    caseWord: "procedure",
    bookTitle: "Book a procedure",
    operation: "Procedure",
    operationPlaceholder: "Colonoscopy, upper GI endoscopy…",
    operationHint: "Search the procedure list, or type one not on it",
    roomOne: "Procedure room",
    operator: "Doctor performing it",
    anaesthetist: "Sedation given by",
    anaesthesia: "Sedation",
    times: "Procedure times",
    slip: "Procedure slip",
    notes: "Notes for the procedure room",
    checklist: "day-procedure checklist",
    durations: ["In the room", "Procedure", "Sedation"],
    askSide: false,
    anaesthesiaChoices: ["Sedation", "Local", "General"],
    inRoom: "In the room",
    skipMilestones: ["incision_at", "closure_at"],
    askTeeth: false,
  },
};

/** A department whose cases read differently from the site's own words.
 *
 * One clinic can hold a scope suite and a dental chair. The site's
 * vocabulary sets the screens' headings; a case in one of these departments
 * is described in its own words wherever the case itself is on screen. */
const DEPARTMENT_WORDS: Partial<Record<Department, Partial<TheatreWords>>> = {
  dentistry: {
    caseWord: "dental procedure",
    bookTitle: "Book a dental procedure",
    operation: "Dental procedure",
    operationPlaceholder: "Extraction, root canal, scaling…",
    operationHint: "Search the procedure list, or type one not on it",
    roomOne: "Dental chair",
    operator: "Treating dentist",
    anaesthetist: "Anaesthesia given by",
    anaesthesia: "Anaesthesia",
    times: "Chair times",
    slip: "Procedure slip",
    notes: "Notes for the chair",
    checklist: "dental checklist",
    durations: ["In the chair", "Procedure", "Anaesthesia"],
    askSide: false,
    anaesthesiaChoices: ["Local", "Sedation", "General"],
    inRoom: "In the chair",
    skipMilestones: ["incision_at", "closure_at"],
    askTeeth: true,
  },
};

interface ModuleState {
  /** Null until the first answer arrives — not "none". */
  enabled: ModuleName[] | null;
  hospitalName: string | null;
  /** False while unknown, so nothing is offered that may not exist. */
  has: (module: ModuleName) => boolean;
  /** The site's words for the theatre module; "theatre" until told otherwise. */
  words: TheatreWords;
  /** The words for one case: the site's, with its department's on top. */
  wordsFor: (department?: Department | null) => TheatreWords;
  /** The departments this site runs, in the order to offer them.
   *
   * Every department until the API answers: a registration screen showing one
   * department too many for a moment is a nuisance, showing none is a screen
   * nobody can use. */
  departments: readonly Department[];
  /** Where a screen should start when it must pick a department. */
  defaultDepartment: Department;
  /** Departments whose drafted prescribing content is still withheld, so the
   *  prescribing screen can say why its medicine list looks short. */
  formularyPendingSignoff: readonly string[];
  /** "bundled" shows the logo that ships with the build; "none" shows the
   *  site's name, for a site that has not supplied artwork yet. Null until
   *  the API answers, so neither is flashed on the wrong site. */
  logo: "bundled" | "none" | null;
  hospitalCity: string | null;
  /** The practice each department works under ("dentistry" → "Smile
   *  Dental"), where it is not the site's own name. */
  departmentBrands: Readonly<Record<string, string>>;
  /** The platform this site runs, shown beside its own identity: "medicos",
   *  or null for a site that shows only its own. */
  platform: "medicos" | null;
}

const ModuleContext = createContext<ModuleState>({
  enabled: null,
  hospitalName: null,
  has: () => false,
  words: THEATRE_WORDS.theatre,
  wordsFor: () => THEATRE_WORDS.theatre,
  departments: ALL_DEPARTMENTS,
  defaultDepartment: ALL_DEPARTMENTS[0],
  formularyPendingSignoff: [],
  logo: null,
  hospitalCity: null,
  departmentBrands: {},
  platform: null,
});

export function useModules() {
  return useContext(ModuleContext);
}

/**
 * A department field that can only ever hold a department this site runs.
 *
 * A plain `useState(defaultDepartment)` has two ways to go wrong, and both
 * happened. It captures the default on first render, before the site's
 * configuration has arrived, so it starts on whatever the build lists first.
 * And a <select> whose value is not among its options shows the first option
 * anyway while the state keeps the old value — so the screen said
 * Gastroenterology, nobody had reason to touch it, and Orthopedics was saved.
 *
 * This keeps the state honest: whenever the value is not one the site offers,
 * it is moved to the site's default. What is on screen is what gets saved.
 */
export function useSiteDepartment(initial?: Department | null) {
  const { departments, defaultDepartment } = useModules();
  const [department, setDepartment] = useState<Department>(initial ?? defaultDepartment);
  useEffect(() => {
    if (!departments.includes(department)) {
      setDepartment(departments.includes(defaultDepartment) ? defaultDepartment : departments[0]);
    }
  }, [departments, defaultDepartment, department]);
  return [department, setDepartment] as const;
}

function readCache(): {
  modules: ModuleName[];
  hospital_name: string;
  theatre_vocabulary?: TheatreVocabulary;
  departments?: Department[];
  default_department?: Department;
  formulary_pending_signoff?: string[];
  hospital_logo?: "bundled" | "none";
  hospital_city?: string;
  platform_brand?: string;
  department_brands?: Record<string, string>;
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
  const [departments, setDepartments] = useState<readonly Department[]>(
    cached?.departments?.length ? cached.departments : ALL_DEPARTMENTS
  );
  const [defaultDepartment, setDefaultDepartment] = useState<Department>(
    cached?.default_department ?? ALL_DEPARTMENTS[0]
  );
  const [formularyPendingSignoff, setPending] = useState<readonly string[]>(
    cached?.formulary_pending_signoff ?? []
  );
  const [logo, setLogo] = useState<"bundled" | "none" | null>(cached?.hospital_logo ?? null);
  const [hospitalCity, setHospitalCity] = useState<string | null>(cached?.hospital_city ?? null);
  const [departmentBrands, setDepartmentBrands] = useState<Record<string, string>>(
    cached?.department_brands ?? {}
  );
  const [platform, setPlatform] = useState<"medicos" | null>(
    cached?.platform_brand === "medicos" ? "medicos" : null
  );

  // The tab title is the site's own name. It used to be written into the
  // root layout as one hospital's name, and every other site inherited it.
  useEffect(() => {
    if (hospitalName) document.title = platform ? `${hospitalName} · MedicOS` : hospitalName;
  }, [hospitalName, platform]);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/v1/config`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active || !data) return;
        setEnabled(data.modules ?? []);
        setHospitalName(data.hospital_name ?? null);
        setVocabulary(data.theatre_vocabulary === "procedures" ? "procedures" : "theatre");
        if (Array.isArray(data.departments) && data.departments.length > 0) {
          setDepartments(data.departments);
        }
        if (data.default_department) setDefaultDepartment(data.default_department);
        setPending(data.formulary_pending_signoff ?? []);
        setLogo(data.hospital_logo === "none" ? "none" : "bundled");
        setHospitalCity(data.hospital_city ?? null);
        setDepartmentBrands(data.department_brands ?? {});
        setPlatform(data.platform_brand === "medicos" ? "medicos" : null);
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
        wordsFor: (department) => ({
          ...THEATRE_WORDS[vocabulary],
          ...(department ? DEPARTMENT_WORDS[department] ?? {} : {}),
        }),
        departments,
        defaultDepartment,
        formularyPendingSignoff,
        logo,
        hospitalCity,
        departmentBrands,
        platform,
      }}
    >
      {children}
    </ModuleContext.Provider>
  );
}
