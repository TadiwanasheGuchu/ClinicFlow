import "server-only";

import type { AuthOptions } from "next-auth";
import { decode, type JWT } from "next-auth/jwt";
import KeycloakProvider from "next-auth/providers/keycloak";
import { cookies } from "next/headers";

/**
 * Authentication runs as a backend-for-frontend: identity-provider tokens live only in
 * the encrypted, httpOnly session cookie and are used server-side. The session object
 * exposed to the browser never contains tokens.
 *
 * AUTH_PROVIDER selects the identity provider:
 *   keycloak (default) — self-hosted Keycloak (KEYCLOAK_* variables)
 *   oidc               — any standards-based OIDC provider, e.g. Auth0 (AUTH_* variables);
 *                        endpoints come from its discovery document.
 */

const mode = process.env.AUTH_PROVIDER === "oidc" ? "oidc" : "keycloak";
export const PROVIDER_ID = mode;

const publicIssuer =
  (mode === "oidc" ? process.env.AUTH_ISSUER : process.env.KEYCLOAK_ISSUER) ?? "http://localhost:8080/realms/clinicflow";
// Inside Docker the server reaches Keycloak by service name; tokens still carry the public issuer.
const internalIssuer = (mode === "oidc" ? undefined : process.env.KEYCLOAK_INTERNAL_ISSUER) ?? publicIssuer;
const clientId = (mode === "oidc" ? process.env.AUTH_CLIENT_ID : process.env.KEYCLOAK_CLIENT_ID) ?? "clinicflow-web";
// Confidential (server-side) client when a secret is set; otherwise a public client with PKCE.
const clientSecret = mode === "oidc" ? (process.env.AUTH_CLIENT_SECRET ?? "") : "";
// Auth0 issues an API (JWT) access token only when asked for the API's audience.
const audience = mode === "oidc" ? process.env.AUTH_AUDIENCE : undefined;
const oidc = (base: string) => `${base}/protocol/openid-connect`;

type Discovery = { token_endpoint: string; end_session_endpoint?: string };
let discovery: Promise<Discovery> | null = null;
function discover(): Promise<Discovery> {
  if (mode === "keycloak") {
    return Promise.resolve({ token_endpoint: `${oidc(internalIssuer)}/token`, end_session_endpoint: `${oidc(publicIssuer)}/logout` });
  }
  discovery ??= fetch(`${publicIssuer.replace(/\/$/, "")}/.well-known/openid-configuration`, { cache: "force-cache" })
    .then((r) => {
      if (!r.ok) throw new Error(`OIDC discovery failed: ${r.status}`);
      return r.json() as Promise<Discovery>;
    })
    .catch((error) => {
      discovery = null; // retry next time
      throw error;
    });
  return discovery;
}

type TokenSet = JWT & {
  accessToken?: string;
  refreshToken?: string;
  idToken?: string;
  expiresAt?: number; // epoch seconds
  error?: "RefreshTokenError";
};

async function refresh(token: TokenSet): Promise<TokenSet> {
  if (!token.refreshToken) return { ...token, error: "RefreshTokenError" };
  const { token_endpoint } = await discover();
  const response = await fetch(token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: clientId,
      refresh_token: token.refreshToken,
      ...(clientSecret ? { client_secret: clientSecret } : {}),
    }),
    cache: "no-store",
  });
  if (!response.ok) return { ...token, error: "RefreshTokenError" };
  const data = (await response.json()) as {
    access_token: string;
    refresh_token?: string;
    id_token?: string;
    expires_in: number;
  };
  return {
    ...token,
    accessToken: data.access_token,
    refreshToken: data.refresh_token ?? token.refreshToken,
    idToken: data.id_token ?? token.idToken,
    expiresAt: Math.floor(Date.now() / 1000) + data.expires_in,
    error: undefined,
  };
}

const isFresh = (token: TokenSet) => !!token.expiresAt && Date.now() < (token.expiresAt - 30) * 1000;

export const authOptions: AuthOptions = {
  providers: [
    mode === "keycloak"
      ? KeycloakProvider({
          clientId,
          clientSecret: "", // public client using PKCE
          issuer: publicIssuer,
          wellKnown: undefined,
          authorization: {
            url: `${oidc(publicIssuer)}/auth`,
            params: { scope: "openid email profile" },
          },
          token: `${oidc(internalIssuer)}/token`,
          userinfo: `${oidc(internalIssuer)}/userinfo`,
          jwks_endpoint: `${oidc(internalIssuer)}/certs`,
          client: { token_endpoint_auth_method: "none" },
          checks: ["pkce", "state"],
        })
      : {
          id: "oidc",
          name: "ClinicFlow sign-in",
          type: "oauth",
          wellKnown: `${publicIssuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
          issuer: publicIssuer,
          clientId,
          clientSecret,
          authorization: {
            params: {
              scope: "openid email profile offline_access",
              ...(audience ? { audience } : {}),
            },
          },
          idToken: true,
          checks: ["pkce", "state"],
          client: clientSecret ? undefined : { token_endpoint_auth_method: "none" },
          profile: (p: { sub: string; name?: string; email?: string }) => ({ id: p.sub, name: p.name ?? p.email, email: p.email }),
        },
  ],
  session: { strategy: "jwt", maxAge: 10 * 60 * 60 },
  pages: { signIn: "/signin" },
  callbacks: {
    async jwt({ token, account }) {
      const t = token as TokenSet;
      if (account) {
        return {
          ...t,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          idToken: account.id_token,
          expiresAt: account.expires_at,
        };
      }
      return isFresh(t) ? t : refresh(t);
    },
    async session({ session, token }) {
      // Deliberately no tokens here: this object is readable from the browser.
      const t = token as TokenSet;
      return { ...session, error: t.error };
    },
  },
};

const SESSION_COOKIES = ["__Secure-next-auth.session-token", "next-auth.session-token"];

/** Read the encrypted session cookie on the server (handles chunked cookies). */
async function readSessionToken(): Promise<TokenSet | null> {
  const store = await cookies();
  for (const name of SESSION_COOKIES) {
    const whole = store.get(name)?.value;
    const chunks = store
      .getAll()
      .filter((c) => c.name.startsWith(`${name}.`))
      .sort((a, b) => Number(a.name.split(".").pop()) - Number(b.name.split(".").pop()))
      .map((c) => c.value);
    const raw = whole ?? (chunks.length ? chunks.join("") : undefined);
    if (raw) {
      return (await decode({ token: raw, secret: process.env.NEXTAUTH_SECRET ?? "" })) as TokenSet | null;
    }
  }
  return null;
}

/** A valid access token for calling the ClinicFlow API, or null if signed out. */
export async function getAccessToken(): Promise<string | null> {
  const token = await readSessionToken();
  if (!token?.accessToken) return null;
  if (isFresh(token)) return token.accessToken;
  const refreshed = await refresh(token);
  return refreshed.error ? null : (refreshed.accessToken ?? null);
}

export async function getIdToken(): Promise<string | null> {
  return (await readSessionToken())?.idToken ?? null;
}

/** Where to send the browser to end the identity provider's session too. */
export async function providerLogoutUrl(idToken: string | null, redirect: string): Promise<string> {
  let endSession: string | undefined;
  try {
    endSession = (await discover()).end_session_endpoint;
  } catch {
    endSession = undefined;
  }
  if (!endSession) {
    // Auth0 tenants without OIDC logout discovery still support /v2/logout.
    const url = new URL(`${publicIssuer.replace(/\/$/, "")}/v2/logout`);
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("returnTo", redirect);
    return url.toString();
  }
  const url = new URL(endSession);
  url.searchParams.set("post_logout_redirect_uri", redirect);
  url.searchParams.set("client_id", clientId);
  if (idToken) url.searchParams.set("id_token_hint", idToken);
  return url.toString();
}
