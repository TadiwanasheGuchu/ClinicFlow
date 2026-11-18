"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { DentalPlan } from "@/types/api";

function rows(form: FormData, prefix: string, field: string): string[] {
  const keys = new Set<string>();
  for (const key of form.keys()) {
    const m = new RegExp(`^${prefix}\\.(\\d+)\\.${field}$`).exec(key);
    if (m) keys.add(m[1]!);
  }
  return [...keys];
}

export async function recordChart(encounterId: string, patientId: string, _: FormState, form: FormData): Promise<FormState> {
  const entries = rows(form, "chart", "tooth")
    .map((r) => ({
      tooth: Number(optional(form, `chart.${r}.tooth`) ?? 0), surfaces: optional(form, `chart.${r}.surfaces`) ?? "",
      condition: optional(form, `chart.${r}.condition`) ?? "", note: optional(form, `chart.${r}.note`),
    }))
    .filter((e) => e.tooth && e.condition);
  if (!entries.length) return { error: "Enter a tooth and a finding." };
  const state = await attempt(() => api(`/encounters/${encounterId}/dental-chart`, { method: "POST", body: { entries } }), "Chart updated.");
  revalidatePath(`/consultations/${encounterId}`);
  revalidatePath(`/patients/${patientId}/dental`);
  return state;
}

export async function chartError(patientId: string, entryId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/dental-chart/${entryId}/entered-in-error`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(`/patients/${patientId}/dental`);
  return state;
}

function planBody(form: FormData, patientId: string) {
  const items = rows(form, "item", "procedure")
    .map((r) => {
      const tooth = optional(form, `item.${r}.tooth`);
      return {
        tooth: tooth ? Number(tooth) : null, surfaces: optional(form, `item.${r}.surfaces`) ?? "",
        procedure: optional(form, `item.${r}.procedure`), service_id: optional(form, `item.${r}.service_id`),
        fee: optional(form, `item.${r}.fee`),
      };
    })
    .filter((i) => i.procedure || i.service_id);
  return { patient_id: patientId, branch_id: required(form, "branch_id"), title: required(form, "title"), notes: optional(form, "notes"), items };
}

export async function savePlan(patientId: string, planId: string | null, _: FormState, form: FormData): Promise<FormState> {
  let saved: DentalPlan | undefined;
  const state = await attempt(async () => {
    saved = await api<DentalPlan>(planId ? `/dental-plans/${planId}` : "/dental-plans", { method: planId ? "PUT" : "POST", body: planBody(form, patientId) });
  }, "Plan saved.");
  if (!planId && saved) redirect(`/dental-plans/${saved.id}`);
  revalidatePath(`/dental-plans/${planId}`);
  return state;
}

async function planStep(planId: string, path: string, body: unknown, message?: string): Promise<FormState> {
  const state = await attempt(() => api(`/dental-plans/${planId}${path}`, { method: "POST", body }), message);
  revalidatePath(`/dental-plans/${planId}`);
  return state;
}

export async function proposePlan(planId: string, _: FormState, form: FormData): Promise<FormState> {
  return planStep(planId, "/propose", { valid_days: Number(optional(form, "valid_days") ?? 30) }, "Quotation issued.");
}

export async function decidePlan(planId: string, _: FormState, form: FormData): Promise<FormState> {
  return planStep(planId, "/decide", { decision: required(form, "decision"), note: optional(form, "note") });
}

export async function itemDone(planId: string, itemId: string, _: FormState, form: FormData): Promise<FormState> {
  return planStep(planId, `/items/${itemId}/done`, { encounter_id: optional(form, "encounter_id") });
}

export async function itemCancel(planId: string, itemId: string, _: FormState): Promise<FormState> {
  return planStep(planId, `/items/${itemId}/cancel`, undefined);
}

export async function cancelPlan(planId: string, _: FormState, form: FormData): Promise<FormState> {
  return planStep(planId, "/cancel", { reason: required(form, "reason") }, "Plan cancelled.");
}

export async function invoicePlan(planId: string, _: FormState): Promise<FormState> {
  let invoiceId: string | undefined;
  const state = await attempt(async () => {
    invoiceId = (await api<{ invoice_id: string }>(`/dental-plans/${planId}/invoice`, { method: "POST" })).invoice_id;
  });
  if (invoiceId) redirect(`/invoices/${invoiceId}`);
  return state;
}
