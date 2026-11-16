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
          },
        },
      }),
    "Organisation saved.",
  );
  revalidatePath("/organisation");
  return state;
}
