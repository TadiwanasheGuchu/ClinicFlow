/** Uptime check for the whole service: the web app is up and can reach the API (and the
 *  API its database). Returns no data. Used by the host's health check and uptime monitor. */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const api = process.env.CLINICFLOW_API_URL ?? "http://localhost:8000";
    const response = await fetch(`${api}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
    return new Response(response.ok ? "ok" : "api unavailable", { status: response.ok ? 200 : 503 });
  } catch {
    return new Response("api unavailable", { status: 503 });
  }
}
