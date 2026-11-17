"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Patient, PatientSummary, Page } from "@/types/api";

function patientBody(form: FormData) {
  const contactName = optional(form, "emergency_contact.name");
  const contactPhone = optional(form, "emergency_contact.phone");
  return {
    first_name: required(form, "first_name"),
    last_name: required(form, "last_name"),
    date_of_birth: required(form, "date_of_birth"),
    sex: optional(form, "sex"),
    nationality: optional(form, "nationality"),
    id_number: optional(form, "id_number"),
    phone: optional(form, "phone"),
    email: optional(form, "email"),
    address: optional(form, "address"),
    preferred_channel: optional(form, "preferred_channel") ?? "sms",
    emergency_contact:
      contactName || contactPhone
        ? {
            name: contactName ?? "",
            phone: contactPhone ?? "",
            relationship: optional(form, "emergency_contact.relationship"),
          }
        : null,
  };
}

export async function registerPatient(_: FormState, form: FormData): Promise<FormState> {
  let created: Patient | undefined;
  const state = await attempt(async () => {
    created = await api<Patient>("/patients", {
      method: "POST",
      body: { ...patientBody(form), confirm_not_duplicate: form.get("confirm_not_duplicate") === "on" },
    });
  });
  if (created) {
    revalidatePath("/patients");
    const next = optional(form, "next");
    redirect(next === "book" ? `/appointments/new?patient=${created.id}` : `/patients/${created.id}`);
  }
  return state;
}

export async function updatePatient(id: string, _: FormState, form: FormData): Promise<FormState> {
  const body = patientBody(form);
  const state = await attempt(
    () => api(`/patients/${encodeURIComponent(id)}`, { method: "PATCH", body }),
    "Patient details saved.",
  );
  revalidatePath(`/patients/${id}`);
  return state;
}

/** Used by the booking form's patient picker. */
export async function searchPatients(q: string): Promise<PatientSummary[]> {
  if (q.trim().length < 2) return [];
  const page = await api<Page<PatientSummary>>("/patients", { query: { q, limit: 10, status: "active" } });
  return page.items;
}
