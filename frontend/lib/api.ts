export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? API_URL.replace(/^http/, "ws");

export type Department = "orthopedics" | "gynecology";
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
