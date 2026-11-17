"use server";

import { revalidatePath } from "next/cache";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";

const int = (form: FormData, key: string) => Number(required(form, key));

export async function updateOrganisation(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api("/organisation", {
        method: "PATCH",
        body: {
          name: required(form, "name"),
          legal_name: optional(form, "legal_name"),
          registration_number: optional(form, "registration_number"),
          email: optional(form, "email"),
          phone: optional(form, "phone"),
          settings: {
            patient_number_prefix: required(form, "settings.patient_number_prefix").toUpperCase(),
            invoice_number_prefix: required(form, "settings.invoice_number_prefix").toUpperCase(),
            default_appointment_minutes: int(form, "settings.default_appointment_minutes"),
            booking_buffer_minutes: int(form, "settings.booking_buffer_minutes"),
            portal_enabled: form.get("settings.portal_enabled") === "on",
            online_auto_confirm: form.get("settings.online_auto_confirm") === "on",
            online_min_notice_hours: int(form, "settings.online_min_notice_hours"),
            online_max_days_ahead: int(form, "settings.online_max_days_ahead"),
            online_cancel_cutoff_hours: int(form, "settings.online_cancel_cutoff_hours"),
            online_max_upcoming: int(form, "settings.online_max_upcoming"),
            reminders_enabled: form.get("settings.reminders_enabled") === "on",
            reminder_hours_before: int(form, "settings.reminder_hours_before"),
          },
          ...(optional(form, "slug") ? { slug: required(form, "slug").toLowerCase() } : {}),
        },
      }),
    "Organisation saved.",
  );
  revalidatePath("/organisation");
  return state;
}
