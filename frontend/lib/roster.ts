import type { LeaveType } from "@/types/api";
import { addDays } from "@/lib/time";

export const LEAVE_TYPE: Record<LeaveType, string> = {
  annual: "Annual leave",
  sick: "Sick leave",
  family: "Family responsibility",
  study: "Study leave",
  unpaid: "Unpaid leave",
  other: "Other",
};

export const LEAVE_STATUS = { requested: "Waiting for approval", approved: "Approved", declined: "Declined", cancelled: "Cancelled" } as const;

/** Monday of the week containing `date` (YYYY-MM-DD). */
export function mondayOf(date: string): string {
  const day = new Date(`${date}T12:00:00Z`).getUTCDay(); // 0 = Sunday
  return addDays(date, -((day + 6) % 7));
}

/** "Mon 16 Nov" for a YYYY-MM-DD date. */
export const shortDay = (date: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
