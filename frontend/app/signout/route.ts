import { NextResponse, type NextRequest } from "next/server";

import { ORG_COOKIE } from "@/lib/api";
import { getIdToken, providerLogoutUrl } from "@/lib/auth";
import { publicUrl } from "@/lib/public-url";
import { safePath } from "@/lib/safe-path";

/** End both the local session and the identity provider's session. POST only (no CSRF-able GET logout). */
export async function POST(request: NextRequest) {
  const idToken = await getIdToken();
  const form = await request.formData().catch(() => null);
  const home = publicUrl(safePath(form?.get("next"), "/signin")).toString();
  const response = NextResponse.redirect(await providerLogoutUrl(idToken, home), { status: 303 });
  for (const cookie of request.cookies.getAll()) {
    if (cookie.name.includes("next-auth") || cookie.name === ORG_COOKIE) {
      response.cookies.delete(cookie.name);
    }
  }
  return response;
}
