const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * The API address as the browser should use it.
 *
 * The build bakes in "localhost:8000", which is right on the server itself and
 * wrong everywhere else: a phone that opened this page from the QR code at
 * http://192.168.x.x:3000 would send its upload to its own localhost. When the
 * configured address is localhost but the page was reached some other way,
 * the API is assumed to be on the same machine the page came from.
 */
function resolveApiUrl(): string {
  if (typeof window === "undefined") return CONFIGURED_API_URL;
  try {
    const configured = new URL(CONFIGURED_API_URL);
    const local = ["localhost", "127.0.0.1"];
    if (local.includes(configured.hostname) && !local.includes(window.location.hostname)) {
      configured.hostname = window.location.hostname;
      return configured.toString().replace(/\/$/, "");
    }
  } catch {
    /* fall through to the configured value */
  }
  return CONFIGURED_API_URL;
}

export const API_URL = resolveApiUrl();
export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? API_URL.replace(/^http/, "ws");

// Re-exported, never redefined: two copies of this union drift apart.
import { DEPARTMENTS, type Department } from "@/lib/types/core";

export { DEPARTMENTS };
export type { Department };
export type Gender = "male" | "female" | "other";

export interface StartConsultationRequest {
  patient: { name: string; age: number; gender: Gender; phone_number: string };
  department: Department;
}

export interface StartConsultationResponse {
  consultation_id: string;
  patient_id: string;
  department: Department;
  session_token: string;
  ws_path: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function startConsultation(
  payload: StartConsultationRequest
): Promise<StartConsultationResponse> {
  const res = await fetch(`${API_URL}/api/v1/consultations/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Could not start the consultation. Please try again.";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep default message */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export function consultationWsUrl(consultationId: string, token: string): string {
  return `${WS_URL}/api/v1/ws/consultations/${consultationId}?token=${encodeURIComponent(token)}`;
}
