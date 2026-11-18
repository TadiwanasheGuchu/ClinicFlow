"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import { addDays, localISO } from "@/lib/time";

/** Date + start/end times; an end at or before the start means the shift ends the next day. */
function shiftBody(form: FormData) {
  const date = required(form, "date");
  const start = required(form, "start");
  const end = required(form, "end");
  return {
    branch_id: required(form, "branch_id"), membership_id: required(form, "membership_id"),
    starts_at: localISO(date, start), ends_at: localISO(end <= start ? addDays(date, 1) : date, end),
    duty: optional(form, "duty"), notes: optional(form, "notes"),
  };
}

export async function addShift(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api("/shifts", { method: "POST", body: shiftBody(form) }), "Shift added.");
  revalidatePath("/roster");
  return state;
}

export async function cancelShift(id: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/shifts/${id}/cancel`, { method: "POST" }), "Shift removed.");
  revalidatePath("/roster");
  return state;
}

export async function copyWeek(branchId: string, from: string, to: string, _: FormState): Promise<FormState> {
  let message = "";
  const state = await attempt(async () => {
    const r = await api<{ created: number; skipped: number }>("/shifts/copy-week", { method: "POST", body: { branch_id: branchId, from_start: from, to_start: to } });
    message = `${r.created} shift${r.created === 1 ? "" : "s"} copied${r.skipped ? `; ${r.skipped} skipped because they would clash with existing shifts or leave` : ""}.`;
  });
  revalidatePath("/roster");
  return state.error ? state : { success: message };
}

export async function requestLeave(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api("/me/leave", { method: "POST", body: {
      starts_on: required(form, "starts_on"), ends_on: optional(form, "ends_on") ?? required(form, "starts_on"),
      leave_type: required(form, "leave_type"), reason: optional(form, "reason"),
    } }),
    "Leave requested. A manager will approve or decline it.",
  );
  revalidatePath("/my-roster");
  return state;
}

export async function cancelLeave(id: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/leave/${id}/cancel`, { method: "POST" }), "Leave cancelled.");
  revalidatePath("/my-roster");
  revalidatePath("/roster/leave");
  return state;
}

export async function decideLeave(id: string, _: FormState, form: FormData): Promise<FormState> {
  const decision = required(form, "decision");
  let result: { appointments_affected: number | null; shifts_affected: number | null } | undefined;
  const state = await attempt(async () => {
    result = await api(`/leave/${id}/decide`, { method: "POST", body: { decision, note: optional(form, "note") } });
  });
  if (state.error || !result) return state;
  // The request leaves the waiting list, so report the outcome on the page itself. Only
  // structured values go in the URL; the page builds the wording.
  redirect(`/roster/leave?${new URLSearchParams({
    decided: decision === "approved" ? "approved" : "declined",
    appointments: String(result.appointments_affected ?? 0),
    shifts: String(result.shifts_affected ?? 0),
  })}`);
}

export async function recordLeave(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api("/leave", { method: "POST", body: {
      membership_id: required(form, "membership_id"), starts_on: required(form, "starts_on"),
      ends_on: optional(form, "ends_on") ?? required(form, "starts_on"), leave_type: required(form, "leave_type"),
      reason: optional(form, "reason"), approve: true,
    } }),
    "Leave recorded and approved.",
  );
  revalidatePath("/roster/leave");
  return state;
}
