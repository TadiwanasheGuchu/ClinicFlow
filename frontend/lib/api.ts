import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth";

const API_URL = process.env.CLINICFLOW_API_URL ?? "http://localhost:8000";
export const ORG_COOKIE = "cf_org";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fieldErrors: Record<string, string> = {},
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

type ValidationDetail = { loc: (string | number)[]; msg: string };

function parseError(status: number, body: unknown): ApiError {
  const b = body as {
    error?: { code: string; message: string; details?: Record<string, unknown> };
    detail?: ValidationDetail[];
  };
  if (b?.error) return new ApiError(status, b.error.code, b.error.message, {}, b.error.details ?? {});
  if (Array.isArray(b?.detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const d of b.detail) {
      const field = d.loc.filter((p) => p !== "body").join(".") || "form";
      fieldErrors[field] = d.msg.replace(/^Value error, /, "");
    }
    return new ApiError(status, "validation_failed", "Check the highlighted fields.", fieldErrors);
  }
  return new ApiError(status, "unexpected", "Something went wrong. Try again.");
}

export async function getActiveOrgId(): Promise<string | null> {
  return (await cookies()).get(ORG_COOKIE)?.value ?? null;
}

export const orgCookieOptions = (secure: boolean) => ({
  httpOnly: true,
  sameSite: "lax" as const,
  secure,
  path: "/",
  maxAge: 60 * 60 * 24 * 30,
});

/** Select the active organisation from a server action. Callers must only pass an
 *  organisation the user has just joined or created; the API re-checks membership anyway. */
export async function setActiveOrgId(organisationId: string): Promise<void> {
  (await cookies()).set(ORG_COOKIE, organisationId, orgCookieOptions(process.env.NODE_ENV === "production"));
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Send the active organisation header (default true). */
  tenant?: boolean;
};

/** Server-side call to the ClinicFlow API with the user's access token. */
export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const token = await getAccessToken();
  if (!token) redirect("/signin");

  const url = new URL(`/api/v1${path}`, API_URL);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.tenant !== false) {
    const org = await getActiveOrgId();
    if (org) headers["X-Organisation-Id"] = org;
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });
  if (response.status === 401) redirect("/signin");
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw parseError(response.status, body);
  return body as T;
}
