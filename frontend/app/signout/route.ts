import { NextResponse, type NextRequest } from "next/server";

import { ORG_COOKIE } from "@/lib/api";
import { getIdToken, keycloakLogoutUrl } from "@/lib/auth";

/** End both the local session and the Keycloak session. POST only (no CSRF-able GET logout). */
export async function POST(request: NextRequest) {
  const idToken = await getIdToken();
  const home = new URL("/signin", request.url).toString();
  const response = NextResponse.redirect(keycloakLogoutUrl(idToken, home), { status: 303 });
  for (const cookie of request.cookies.getAll()) {
    if (cookie.name.includes("next-auth") || cookie.name === ORG_COOKIE) {
      response.cookies.delete(cookie.name);
    }
  }
  return response;
}
