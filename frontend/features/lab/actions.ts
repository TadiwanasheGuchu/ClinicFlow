"use server";

import { revalidatePath } from "next/cache";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";

const orderPath = (id: string) => `/lab/${id}`;

/** Request tests from a consultation: ticked tests from the list plus any named by hand. */
export async function orderTests(encounterId: string, _: FormState, form: FormData): Promise<FormState> {
  const items = [
    ...form.getAll("test_id").map((id) => ({ test_id: String(id) })),
    ...form.getAll("other_test").map((v) => String(v).trim()).filter(Boolean).map((name) => ({ test_name: name })),
  ];
  if (!items.length) return { error: "Choose at least one test." };
  const state = await attempt(
    () => api(`/encounters/${encounterId}/lab-orders`, { method: "POST", body: {
      items,
      laboratory_id: optional(form, "laboratory_id"),
      urgency: optional(form, "urgency") ?? "routine",
      clinical_information: optional(form, "clinical_information"),
    } }),
    "Tests requested.",
  );
  revalidatePath(`/consultations/${encounterId}`);
  return state;
}

export async function progressOrder(orderId: string, _: FormState, form: FormData): Promise<FormState> {
  const status = required(form, "status");
  const state = await attempt(
    () => api(`/lab-orders/${orderId}/progress`, { method: "POST", body: {
      status,
      external_reference: optional(form, "external_reference"),
      laboratory_id: optional(form, "laboratory_id"),
    } }),
    "Order updated.",
  );
  revalidatePath(orderPath(orderId));
  return state;
}

export async function cancelOrder(orderId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/lab-orders/${orderId}/cancel`, { method: "POST", body: { reason: required(form, "reason") } }), "Order cancelled.");
  revalidatePath(orderPath(orderId));
  return state;
}

/** One form row per reported value: `row.<n>.item_id`, `.analyte`, `.value`, … */
export async function recordResults(orderId: string, _: FormState, form: FormData): Promise<FormState> {
  const rows = new Set<string>();
  for (const key of form.keys()) {
    const m = /^row\.(\d+)\.value$/.exec(key);
    if (m) rows.add(m[1]!);
  }
  const field = (r: string, f: string) => optional(form, `row.${r}.${f}`);
  const results = [...rows]
    .map((r) => ({
      item_id: field(r, "item_id") ?? "", analyte: field(r, "analyte"), value: field(r, "value") ?? "",
      unit: field(r, "unit"), reference_range: field(r, "reference_range"), flag: field(r, "flag") ?? "none", comment: field(r, "comment"),
    }))
    .filter((r) => r.value);
  if (!results.length) return { error: "Enter at least one result value." };
  const state = await attempt(() => api(`/lab-orders/${orderId}/results`, { method: "POST", body: { results } }), "Results recorded.");
  revalidatePath(orderPath(orderId));
  return state;
}

export async function markResultError(orderId: string, resultId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/lab-results/${resultId}/entered-in-error`, { method: "POST", body: { reason: required(form, "reason") } }));
  revalidatePath(orderPath(orderId));
  return state;
}

export async function reviewOrder(orderId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/lab-orders/${orderId}/review`, { method: "POST", body: { comment: optional(form, "comment") } }), "Results reviewed.");
  revalidatePath(orderPath(orderId));
  return state;
}

export async function saveLabTest(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = {
    code: required(form, "code").toUpperCase(), name: required(form, "name"), category: optional(form, "category"),
    specimen_type: optional(form, "specimen_type"), is_active: id ? form.get("is_active") === "on" : true,
  };
  const state = await attempt(() => api(id ? `/laboratory-tests/${id}` : "/laboratory-tests", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Test added.");
  revalidatePath("/lab-setup");
  return state;
}

export async function saveLaboratory(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = {
    name: required(form, "name"), phone: optional(form, "phone"), email: optional(form, "email"),
    notes: optional(form, "notes"), is_active: id ? form.get("is_active") === "on" : true,
  };
  const state = await attempt(() => api(id ? `/laboratories/${id}` : "/laboratories", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Laboratory added.");
  revalidatePath("/lab-setup");
  return state;
}
