import "server-only";

/**
 * The app's public address. Behind a hosting proxy, `request.url` is the server's internal
 * bind address (e.g. http://0.0.0.0:10000), so redirects and cookie flags must use this.
 */
const base = new URL(process.env.NEXTAUTH_URL ?? "http://localhost:3000");

export const publicUrl = (path: string) => new URL(path, base);
export const isHttps = base.protocol === "https:";
