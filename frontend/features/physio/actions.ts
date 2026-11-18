"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { PhysioEpisodeDetail } from "@/types/api";

export async function openEpisode(patientId: string, _: FormState, form: FormData): Promise<FormState> {
  let created: PhysioEpisodeDetail | undefined;
  const planned = optional(form, "planned_sessions");
  const state = await attempt(async () => {
    created = await api<PhysioEpisodeDetail>("/physio-episodes", { method: "POST", body: {
      patient_id: patientId, branch_id: required(form, "branch_id"), condition: required(form, "condition"),
      body_region: optional(form, "body_region"), referral_source: optional(form, "referral_source"),
      goals: optional(form, "goals"), planned_sessions: planned ? Number(planned) : null,
    } });
  });
  if (created) redirect(`/physio-episodes/${created.id}`);
  return state;
}

export async function linkSession(episodeId: string, encounterId: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/physio-episodes/${episodeId}/sessions`, { method: "POST", body: { encounter_id: encounterId } }), "Counted as a session.");
  revalidatePath(`/consultations/${encounterId}`);
  return state;
}

export async function recordMeasurements(episodeId: string, _: FormState, form: FormData): Promise<FormState> {
  const keys = new Set<string>();
  for (const key of form.keys()) {
    const m = /^m\.(\d+)\.value$/.exec(key);
    if (m) keys.add(m[1]!);
  }
  const items = [...keys]
    .map((k) => ({
      measure: optional(form, `m.${k}.measure`) ?? "custom", label: optional(form, `m.${k}.label`) ?? "",
      side: optional(form, `m.${k}.side`), value: optional(form, `m.${k}.value`) ?? "", unit: optional(form, `m.${k}.unit`),
    }))
    .filter((i) => i.value !== "" && i.label);
  if (!items.length) return { error: "Enter at least one measurement with a label and value." };
  const state = await attempt(
    () => api(`/physio-episodes/${episodeId}/measurements`, { method: "POST", body: { encounter_id: required(form, "encounter_id"), items } }),
    "Measurements recorded.",
  );
  revalidatePath(`/physio-episodes/${episodeId}`);
  return state;
}

export async function measurementError(episodeId: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/physio-measurements/${id}/entered-in-error`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(`/physio-episodes/${episodeId}`);
  return state;
}

export async function dischargeEpisode(episodeId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/physio-episodes/${episodeId}/discharge`, { method: "POST", body: { outcome: required(form, "outcome"), summary: required(form, "summary") } }),
    "Discharged.",
  );
  revalidatePath(`/physio-episodes/${episodeId}`);
  return state;
}
