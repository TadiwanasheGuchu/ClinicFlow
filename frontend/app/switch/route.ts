import { NextResponse, type NextRequest } from "next/server";

import { api, ORG_COOKIE, orgCookieOptions } from "@/lib/api";
import type { Me } from "@/types/api";

/** Select the active organisation. Only organisations the user is an active member of. */
export async function GET(request: NextRequest) {
  const target = request.nextUrl.searchParams.get("to");
  const next = request.nextUrl.searchParams.get("next");
  const me = await api<Me>("/me", { tenant: false });
  const allowed = me.memberships.some(
    (m) => m.organisation_id === target && m.status === "active" && m.organisation_status === "active",
  );
  // Only same-site relative paths are accepted as the return location.
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/branches";
  const response = NextResponse.redirect(new URL(allowed ? safeNext : "/onboarding", request.url));
  if (allowed && target) {
    response.cookies.set(ORG_COOKIE, target, orgCookieOptions(request.nextUrl.protocol === "https:"));
  }
  return response;
}
