"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api, ApiError } from "@/lib/api";
import { NOTE_SECTIONS } from "@/lib/clinical";
import { type FormState, optional, required } from "@/lib/form";
import type { EncounterDetail } from "@/types/api";

const consult = (id: string) => `/consultations/${id}`;

export async function startConsultation(patientId: string, appointmentId: string | null, form?: FormData): Promise<void> {
  let encounterId: string | undefined;
  try {
    const created = await api<EncounterDetail>("/encounters", {
      method: "POST",
      body: {
        patient_id: patientId,
        appointment_id: appointmentId,
        branch_id: form ? optional(form, "branch_id") : null,
        encounter_type: (form && optional(form, "encounter_type")) || "consultation",
      },
    });
    encounterId = created.id;
  } catch (error) {
    if (error instanceof ApiError && error.code === "encounter_exists") {
      encounterId = String(error.details.encounter_id);
    } else {
      throw error;
    }
  }
  redirect(consult(encounterId));
}

function noteContent(form: FormData, noteType: string) {
  return Object.fromEntries((NOTE_SECTIONS[noteType] ?? []).map((s) => [s.key, String(form.get(`section.${s.key}`) ?? "")]));
}

/** Save, sign or discard a draft (or start an amendment) depending on the button pressed. */
export async function noteAction(encounterId: string, noteId: string | null, amendsId: string | null, _: FormState, form: FormData): Promise<FormState> {
  const intent = required(form, "intent");
  const noteType = optional(form, "note_type") ?? "consultation";
  const content = noteContent(form, noteType);
  const state = await attempt(async () => {
    let id = noteId;
    if (intent === "discard" && id) {
      await api(`/notes/${id}`, { method: "DELETE" });
      return;
    }
    if (!id && amendsId) {
      id = (await api<{ id: string }>(`/notes/${amendsId}/amend`, { method: "POST", body: { note_type: noteType, content, reason: required(form, "reason") } })).id;
    } else if (!id) {
      id = (await api<{ id: string }>(`/encounters/${encounterId}/notes`, { method: "POST", body: { note_type: noteType, content } })).id;
    } else {
      await api(`/notes/${id}`, { method: "PUT", body: { note_type: noteType, content } });
    }
    if (intent === "sign") await api(`/notes/${id}/sign`, { method: "POST" });
  }, intent === "sign" ? "Note signed." : intent === "discard" ? "Draft discarded." : "Draft saved.");
  revalidatePath(consult(encounterId));
  return state;
}

export async function recordVitals(encounterId: string, _: FormState, form: FormData): Promise<FormState> {
  const items = [...form.entries()]
    .filter(([k, v]) => k.startsWith("obs.") && String(v).trim() !== "")
    .map(([k, v]) => ({ observation_type: k.slice(4), value: String(v) }));
  if (!items.length) return { error: "Enter at least one measurement." };
  const state = await attempt(() => api(`/encounters/${encounterId}/observations`, { method: "POST", body: { items } }), "Vital signs recorded.");
  revalidatePath(consult(encounterId));
  return state;
}

export async function markObservationError(encounterId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/observations/${id}/entered-in-error`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(consult(encounterId));
  return state;
}

export async function addDiagnosis(encounterId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/encounters/${encounterId}/diagnoses`, { method: "POST", body: { description: required(form, "description"), code: optional(form, "code")?.toUpperCase() ?? null } }),
    "Diagnosis recorded.",
  );
  revalidatePath(consult(encounterId));
  return state;
}

export async function changeDiagnosis(encounterId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/diagnoses/${id}/status`, { method: "POST", body: { clinical_status: required(form, "clinical_status"), reason: required(form, "reason") } }));
  revalidatePath(consult(encounterId));
  return state;
}

export async function addReferral(encounterId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/encounters/${encounterId}/referrals`, { method: "POST", body: {
      receiving_provider: required(form, "receiving_provider"), receiving_specialty: optional(form, "receiving_specialty"),
      urgency: optional(form, "urgency") ?? "routine", reason: required(form, "reason") } }),
    "Referral issued.",
  );
  revalidatePath(consult(encounterId));
  return state;
}

export async function cancelReferral(encounterId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/referrals/${id}/cancel`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(consult(encounterId));
  return state;
}

export async function prescribe(encounterId: string, _: FormState, form: FormData): Promise<FormState> {
  const rows = new Set<string>();
  for (const key of form.keys()) {
    const m = /^item\.(\d+)\.medication$/.exec(key);
    if (m) rows.add(m[1]!);
  }
  const field = (i: string, f: string) => optional(form, `item.${i}.${f}`);
  const items = [...rows].map((i) => ({
    medication: field(i, "medication") ?? "", strength: field(i, "strength"), dose: field(i, "dose") ?? "",
    frequency: field(i, "frequency") ?? "", route: field(i, "route"), duration: field(i, "duration"),
    quantity: field(i, "quantity"), instructions: field(i, "instructions"),
  })).filter((i) => i.medication);
  const acknowledged = form.get("acknowledge_allergy_warning") === "on";
  const state = await attempt(
    () => api(`/encounters/${encounterId}/prescriptions`, { method: "POST", body: {
      items, acknowledge_allergy_warning: acknowledged, acknowledgement_reason: acknowledged ? optional(form, "acknowledgement_reason") : null } }),
    "Prescription issued.",
  );
  revalidatePath(consult(encounterId));
  return state;
}

export async function cancelPrescription(encounterId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/prescriptions/${id}/cancel`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(consult(encounterId));
  return state;
}

export async function closeConsultation(encounterId: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/encounters/${encounterId}/close`, { method: "POST" }), "Consultation closed.");
  revalidatePath(consult(encounterId));
  return state;
}

export async function addAllergy(patientId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/patients/${patientId}/allergies`, { method: "POST", body: { substance: required(form, "substance"), reaction: optional(form, "reaction"), severity: optional(form, "severity") ?? "unknown" } }),
    "Allergy recorded.",
  );
  revalidatePath(`/patients/${patientId}/clinical`);
  return state;
}

export async function noKnownAllergies(patientId: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/patients/${patientId}/allergies/none-known`, { method: "POST" }), "Recorded: no known allergies.");
  revalidatePath(`/patients/${patientId}/clinical`);
  return state;
}

export async function changeAllergy(patientId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/allergies/${id}/status`, { method: "POST", body: { status: required(form, "status"), reason: required(form, "reason") } }));
  revalidatePath(`/patients/${patientId}/clinical`);
  return state;
}
