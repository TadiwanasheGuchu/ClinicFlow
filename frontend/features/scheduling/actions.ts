"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import { localISO } from "@/lib/time";
import type { Provider } from "@/types/api";

export async function createProvider(_: FormState, form: FormData): Promise<FormState> {
  let created: Provider | undefined;
  const state = await attempt(async () => {
    created = await api<Provider>("/providers", {
      method: "POST",
      body: {
        membership_id: required(form, "membership_id"),
        display_name: optional(form, "display_name"),
      },
    });
  });
  if (created) {
    revalidatePath("/practitioners");
    redirect(`/practitioners/${created.id}`);
  }
  return state;
}

export async function updateProvider(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/providers/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: {
          display_name: required(form, "display_name"),
          booking_enabled: form.get("booking_enabled") === "on",
          online_booking_enabled: form.get("online_booking_enabled") === "on",
        },
      }),
    "Practitioner saved.",
  );
  revalidatePath(`/practitioners/${id}`);
  return state;
}

/** Rows are posted as row.<n>.weekday / branch / start / end. */
export async function saveAvailability(id: string, _: FormState, form: FormData): Promise<FormState> {
  const indexes = new Set<string>();
  for (const key of form.keys()) {
    const m = /^row\.(\d+)\.weekday$/.exec(key);
    if (m) indexes.add(m[1]!);
  }
  const windows = [...indexes].map((i) => ({
    weekday: Number(required(form, `row.${i}.weekday`)),
    branch_id: required(form, `row.${i}.branch`),
    start_time: required(form, `row.${i}.start`),
    end_time: required(form, `row.${i}.end`),
  }));
  const state = await attempt(
    () => api(`/providers/${encodeURIComponent(id)}/availability`, { method: "PUT", body: { windows } }),
    "Working hours saved. Existing bookings are unchanged.",
  );
  revalidatePath(`/practitioners/${id}`);
  return state;
}

export async function addLeave(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/providers/${encodeURIComponent(id)}/unavailability`, {
        method: "POST",
        body: {
          start_at: localISO(required(form, "start_date"), required(form, "start_time")),
          end_at: localISO(required(form, "end_date"), required(form, "end_time")),
          reason: optional(form, "reason"),
        },
      }),
    "Blocked time added. Check the calendar for bookings in this period.",
  );
  revalidatePath(`/practitioners/${id}`);
  return state;
}

export async function removeLeave(providerId: string, itemId: string): Promise<void> {
  await api(`/providers/${encodeURIComponent(providerId)}/unavailability/${encodeURIComponent(itemId)}`, { method: "DELETE" });
  revalidatePath(`/practitioners/${providerId}`);
}

const typeBody = (form: FormData) => ({
  name: required(form, "name"),
  description: optional(form, "description"),
  duration_minutes: Number(required(form, "duration_minutes")),
  fee: required(form, "fee"),
  booking_buffer_minutes: Number(optional(form, "booking_buffer_minutes") ?? 0),
  online_bookable: form.get("online_bookable") === "on",
});

export async function createAppointmentType(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api("/appointment-types", { method: "POST", body: typeBody(form) }), "Appointment type added.");
  revalidatePath("/appointment-types");
  return state;
}

export async function updateAppointmentType(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/appointment-types/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { ...typeBody(form), is_active: form.get("is_active") === "on" },
      }),
    "Saved.",
  );
  revalidatePath("/appointment-types");
  return state;
}
