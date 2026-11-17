/** Accept only same-site relative paths (prevents open redirects). */
export const safePath = (value: unknown, fallback = "/"): string =>
  typeof value === "string" && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\")
    ? value
    : fallback;
