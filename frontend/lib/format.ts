/** Date, duration and name formatting used across the clinical dashboard. */

/**
 * The hospital's own clock, not the device's.
 *
 * Every stored timestamp is UTC and the server renders in Asia/Kolkata. A
 * browser left on another timezone — a laptop brought from abroad, a cloud
 * desktop, a phone that has not caught up — would otherwise show a different
 * time for the same receipt than the printed copy carries.
 */
const HOSPITAL_ZONE = "Asia/Kolkata";

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: HOSPITAL_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const TIME_ONLY = new Intl.DateTimeFormat("en-IN", {
  timeZone: HOSPITAL_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const DATE_ONLY = new Intl.DateTimeFormat("en-IN", {
  timeZone: HOSPITAL_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : DATE_TIME.format(date);
}

export function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : TIME_ONLY.format(date);
}

const WEEKDAY = new Intl.DateTimeFormat("en-IN", {
  timeZone: HOSPITAL_ZONE,
  weekday: "long",
});
const LONG_DATE = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/**
 * "Friday, 31 July 2026".
 *
 * Composed from two formatters rather than one: locales disagree about whether
 * a comma follows the weekday, and this heading has a fixed required format.
 */
export function formatFullDate(date: Date = new Date()): string {
  if (Number.isNaN(date.getTime())) return "";
  return `${WEEKDAY.format(date)}, ${LONG_DATE.format(date)}`;
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : DATE_ONLY.format(date);
}

/** "just now", "12m ago", "3h ago", "5d ago" */
export function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** Elapsed span between two timestamps, e.g. "4m 12s". */
export function duration(startIso?: string | null, endIso?: string | null): string {
  if (!startIso) return "—";
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  const total = Math.floor((end - start) / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  }
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export function clockDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "0:00";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function titleCase(value?: string | null): string {
  if (!value) return "";
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export const DEPARTMENT_LABEL: Record<string, string> = {
  orthopedics: "Orthopedics",
  gynecology: "Gynecology",
  gastroenterology: "Gastroenterology",
  dentistry: "Dentistry",
};

/** The hospital's own name for the department, used on the dropdowns where
 * staff pick one. Kept separate from the short label, which is what fits in a
 * table cell. */
export const DEPARTMENT_FULL_LABEL: Record<string, string> = {
  orthopedics: "Trauma & Orthopedics",
  gynecology: "Maternity & Gynecology",
  gastroenterology: "Gastroenterology",
  dentistry: "Dentistry",
};

/** Three letters used in visit and prescription numbers.
 *
 * Mirrors DepartmentProfile.code in backend/app/departments.py. Both sides
 * print the same number for the same visit, so the two must not drift; the
 * backend is the authority if they ever do. */
export const DEPARTMENT_CODE: Record<string, string> = {
  orthopedics: "ORT",
  gynecology: "GYN",
  gastroenterology: "GAS",
  dentistry: "DEN",
};

/** Doctor names are NOT listed here. They belong to the consultant register,
 * which is where the hospital maintains them; a name hardcoded in the frontend
 * is wrong the day a consultant changes, and wrong from the start in a clinic
 * that never employed them. */

const HOSPITAL_TIME = new Intl.DateTimeFormat("en-IN", {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
  timeZone: HOSPITAL_ZONE,
});

const HOSPITAL_DATE = new Intl.DateTimeFormat("en-IN", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  timeZone: HOSPITAL_ZONE,
});

export function formatHospitalTime(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : HOSPITAL_TIME.format(date);
}

export function formatHospitalDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : HOSPITAL_DATE.format(date);
}

/** Today in the hospital's timezone, as the YYYY-MM-DD the API expects. */
export function hospitalToday(offsetDays = 0): string {
  const now = new Date();
  now.setDate(now.getDate() + offsetDays);
  // en-CA renders ISO order, which is what the query parameter wants.
  return new Intl.DateTimeFormat("en-CA", { timeZone: HOSPITAL_ZONE }).format(now);
}
