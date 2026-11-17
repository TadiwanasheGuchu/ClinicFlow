import { NextResponse, type NextRequest } from "next/server";

/** Passes the requested path to server components (as `x-pathname`) so the organisation
 *  selection redirect in lib/session.ts can return the user to where they were going. */
export function proxy(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("x-pathname", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Skip static assets and the auth endpoints.
  matcher: ["/((?!_next/|api/auth/|favicon.ico).*)"],
};
