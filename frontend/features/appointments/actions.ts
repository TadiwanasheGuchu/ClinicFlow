"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import { localISO } from "@/lib/time";
import type { AppointmentDetail, AppointmentStatus, Slot } from "@/types/api";

export async function loadSlots(params: {
  providerId: string;
  branchId: string;
  typeId: string;
  date: string;
}): Promise<Slot[]> {
  return api<Slot[]>(`/providers/${encodeURIComponent(params.providerId)}/slots`, {
    query: { branch_id: params.branchId, appointment_type_id: params.typeId, date: params.date },
  });
}

/** Start time from the chosen slot, a manual (override) time, or "now" for walk-ins. */
function startFrom(form: FormData): string {
  if (optional(form, "booking_source") === "walk_in") return new Date().toISOString();
  const manual = optional(form, "manual_time");
  if (manual && optional(form, "override_reason")) return localISO(required(form, "date"), manual);
  return required(form, "slot");
}

export async function bookAppointment(_: FormState, form: FormData): Promise<FormState> {
  if (!optional(form, "patient_id")) return { error: "Choose a patient." };
  if (optional(form, "booking_source") !== "walk_in" && !optional(form, "slot") && !optional(form, "manual_time")) {
    return { error: "Choose a time." };
  }
  let created: AppointmentDetail | undefined;
  const state = await attempt(async () => {
    created = await api<AppointmentDetail>("/appointments", {
      method: "POST",
      body: {
        patient_id: required(form, "patient_id"),
        provider_id: required(form, "provider_id"),
        branch_id: required(form, "branch_id"),
        appointment_type_id: required(form, "appointment_type_id"),
        start_at: startFrom(form),
        booking_source: optional(form, "booking_source") ?? "reception",
        booking_note: optional(form, "booking_note"),
        override_reason: optional(form, "override_reason"),
      },
    });
  });
  if (created) {
    revalidatePath("/today");
    redirect(`/appointments/${created.id}?booked=1`);
  }
  return state;
}

export async function rescheduleAppointment(id: string, _: FormState, form: FormData): Promise<FormState> {
  const manual = optional(form, "manual_time");
  const start = manual && optional(form, "override_reason") ? localISO(required(form, "date"), manual) : optional(form, "slot");
  if (!start) return { error: "Choose a new time." };
  const state = await attempt(
    () =>
      api(`/appointments/${encodeURIComponent(id)}/reschedule`, {
        method: "POST",
        body: {
          start_at: start,
          reason: required(form, "reason"),
          override_reason: optional(form, "override_reason"),
        },
      }),
    "Appointment moved.",
  );
  revalidatePath(`/appointments/${id}`);
  return state;
}

export async function cancelAppointment(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/appointments/${encodeURIComponent(id)}/cancel`, { method: "POST", body: { reason: required(form, "reason") } }),
    "Appointment cancelled.",
  );
  revalidatePath(`/appointments/${id}`);
  revalidatePath("/today");
  return state;
}

export async function setAppointmentStatus(id: string, status: AppointmentStatus, returnTo?: string): Promise<void> {
  await api(`/appointments/${encodeURIComponent(id)}/status`, { method: "POST", body: { status } });
  revalidatePath(`/appointments/${id}`);
  revalidatePath("/today");
  if (returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//")) redirect(returnTo);
}
