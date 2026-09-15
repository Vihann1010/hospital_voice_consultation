"use client";

/**
 * Staff authentication.
 *
 * The bearer token is kept in a cookie so Next middleware can gate dashboard
 * routes before a page renders. Note that this is a UX guard only — the cookie
 * is readable by JavaScript (same exposure as localStorage) and the real
 * security boundary is the API, which validates the JWT on every request.
 * Serve over HTTPS in production so the cookie is sent with `Secure`.
 */
import { API_URL } from "@/lib/api";
import type { User } from "@/lib/types/core";

export const TOKEN_COOKIE = "satya_staff_token";

export function setToken(token: string, maxAgeSeconds = 60 * 60 * 8): void {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:";
  document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax${
    secure ? "; Secure" : ""
  }`;
}

export function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${TOKEN_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function clearToken(): void {
  document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

export async function login(email: string, password: string): Promise<string> {
  const response = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Incorrect email or password.");
    let detail = "Could not sign in. Please try again.";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  const body = (await response.json()) as { access_token: string };
  setToken(body.access_token);
  return body.access_token;
}

export async function fetchCurrentUser(): Promise<User | null> {
  const token = getToken();
  if (!token) return null;
  const response = await fetch(`${API_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) return null;
  return response.json();
}

export function logout(): void {
  clearToken();
  if (typeof window !== "undefined") sessionStorage.removeItem("finance_unlock");
  if (typeof window !== "undefined") window.location.href = "/login";
}
