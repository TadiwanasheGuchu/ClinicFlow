/** Time-zone helpers. All scheduling is in the organisation's timezone (Africa/Windhoek). */

export const ORG_TZ = "Africa/Windhoek";

/** "+02:00" — the zone's UTC offset on a given date. */
export function tzOffset(date: string, tz = ORG_TZ): string {
  const probe = new Date(`${date}T12:00:00Z`);
  const part = new Intl.DateTimeFormat("en-GB", { timeZone: tz, timeZoneName: "longOffset" })
    .formatToParts(probe)
    .find((p) => p.type === "timeZoneName")?.value;
  const offset = part?.replace("GMT", "") || "+00:00";
  return offset === "" ? "+00:00" : offset;
}

/** Today's date in the org timezone as YYYY-MM-DD. */
export function todayISO(tz = ORG_TZ): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
}

export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const isISODate = (value: string | undefined): value is string =>
  !!value && /^\d{4}-\d{2}-\d{2}$/.test(value);

/** Start and end of a local day, as ISO timestamps with offset. */
export function dayRange(date: string, tz = ORG_TZ): { from: string; to: string } {
  return { from: `${date}T00:00:00${tzOffset(date, tz)}`, to: `${addDays(date, 1)}T00:00:00${tzOffset(addDays(date, 1), tz)}` };
}

/** Local wall-clock time + date -> ISO with offset. */
export const localISO = (date: string, hhmm: string, tz = ORG_TZ) => `${date}T${hhmm}:00${tzOffset(date, tz)}`;

/** "14:30" in the org timezone. */
export const timeOf = (iso: string, tz = ORG_TZ) =>
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz }).format(new Date(iso));

/** Minutes since local midnight. */
export function minutesOfDay(iso: string, tz = ORG_TZ): number {
  const [h, m] = timeOf(iso, tz).split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

/** "Monday 16 Nov 2026" */
export const longDate = (date: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));

/** Age in whole years on today's date. */
export function ageOf(dob: string): number {
  const today = todayISO();
  const [ty, tm, td] = today.split("-").map(Number) as [number, number, number];
  const [by, bm, bd] = dob.split("-").map(Number) as [number, number, number];
  return ty - by - (tm < bm || (tm === bm && td < bd) ? 1 : 0);
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** Local calendar date (YYYY-MM-DD) of an instant in the org timezone. */
export const dateOf = (iso: string, tz = ORG_TZ) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date(iso));
