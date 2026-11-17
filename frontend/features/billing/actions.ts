"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api, ApiError } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Claim, Invoice } from "@/types/api";

/** Invoice lines are posted as line.<n>.service / description / unit_price / quantity. */
function readItems(form: FormData) {
  const rows = new Set<string>();
  for (const key of form.keys()) {
    const m = /^line\.(\d+)\.quantity$/.exec(key);
    if (m) rows.add(m[1]!);
  }
  return [...rows].map((i) => {
    const serviceId = optional(form, `line.${i}.service`);
    const description = optional(form, `line.${i}.description`);
    const price = optional(form, `line.${i}.unit_price`);
    return {
      service_id: serviceId,
      description: serviceId && !description ? null : description,
      unit_price: price,
      quantity: optional(form, `line.${i}.quantity`) ?? "1",
    };
  }).filter((l) => l.service_id || l.description);
}

export async function createInvoice(_: FormState, form: FormData): Promise<FormState> {
  let created: Invoice | undefined;
  const state = await attempt(async () => {
    created = await api<Invoice>("/invoices", {
      method: "POST",
      body: { patient_id: required(form, "patient_id"), branch_id: optional(form, "branch_id"), items: readItems(form), notes: optional(form, "notes") },
    });
  });
  if (created) redirect(`/invoices/${created.id}`);
  return state;
}

export async function invoiceForAppointment(patientId: string, appointmentId: string): Promise<void> {
  const existing = await api<{ items: { id: string; status: string }[] }>("/invoices", { query: { appointment_id: appointmentId, limit: 5 } });
  const open = existing.items.find((i) => i.status !== "credited");
  if (open) redirect(`/invoices/${open.id}`);
  const created = await api<Invoice>("/invoices", { method: "POST", body: { patient_id: patientId, appointment_id: appointmentId } });
  redirect(`/invoices/${created.id}`);
}

export async function saveDraft(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/invoices/${id}/items`, { method: "PUT", body: { items: readItems(form), notes: optional(form, "notes") } }), "Draft saved.");
  revalidatePath(`/invoices/${id}`);
  return state;
}

export async function issueInvoice(id: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/invoices/${id}/issue`, { method: "POST" }), "Invoice issued.");
  revalidatePath(`/invoices/${id}`);
  return state;
}

export async function discardInvoice(id: string): Promise<void> {
  await api(`/invoices/${id}`, { method: "DELETE" });
  redirect("/invoices");
}

export async function takePayment(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/invoices/${id}/payments`, { method: "POST", body: { amount: required(form, "amount"), method: required(form, "method"), reference: optional(form, "reference") } }),
    "Payment recorded.",
  );
  revalidatePath(`/invoices/${id}`);
  return state;
}

export async function reversePayment(invoiceId: string, paymentId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/payments/${paymentId}/reverse`, { method: "POST", body: { reason: required(form, "reason") } }), "Payment reversed.");
  revalidatePath(`/invoices/${invoiceId}`);
  return state;
}

export async function creditInvoice(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/invoices/${id}/credit-notes`, { method: "POST", body: { amount: required(form, "amount"), reason: required(form, "reason") } }), "Credit note issued.");
  revalidatePath(`/invoices/${id}`);
  return state;
}

export async function refundInvoice(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/invoices/${id}/refunds`, { method: "POST", body: { amount: required(form, "amount"), method: required(form, "method"), reference: optional(form, "reference"), reason: required(form, "reason") } }),
    "Refund recorded.",
  );
  revalidatePath(`/invoices/${id}`);
  return state;
}

export async function prepareClaim(invoiceId: string, _: FormState, form: FormData): Promise<FormState> {
  let claim: Claim | undefined;
  const state = await attempt(async () => {
    try {
      claim = await api<Claim>("/claims", { method: "POST", body: { invoice_id: invoiceId, membership_id: required(form, "membership_id") } });
    } catch (error) {
      if (error instanceof ApiError && error.code === "claim_exists") redirect(`/claims/${String(error.details.claim_id)}`);
      throw error;
    }
  });
  if (claim) redirect(`/claims/${claim.id}`);
  return state;
}

export async function editClaim(id: string, _: FormState, form: FormData): Promise<FormState> {
  const codes = (optional(form, "diagnosis_codes") ?? "").split(/[\s,;]+/).filter(Boolean);
  const state = await attempt(() => api(`/claims/${id}`, { method: "PATCH", body: { diagnosis_codes: codes, claimed_amount: optional(form, "claimed_amount") } }), "Claim saved.");
  revalidatePath(`/claims/${id}`);
  return state;
}

export async function claimTransition(id: string, status: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/claims/${id}/status`, { method: "POST", body: {
      status, fund_reference: optional(form, "fund_reference"), submission_method: optional(form, "submission_method"),
      approved_amount: optional(form, "approved_amount"), reason: optional(form, "reason") } }),
    "Claim updated.",
  );
  revalidatePath(`/claims/${id}`);
  return state;
}

export async function recordRemittance(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/claims/${id}/remittance`, { method: "POST", body: { amount: required(form, "amount"), reference: required(form, "reference") } }), "Payment from the fund recorded.");
  revalidatePath(`/claims/${id}`);
  return state;
}

export async function saveService(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = {
    code: required(form, "code").toUpperCase(), tariff_code: optional(form, "tariff_code"), name: required(form, "name"),
    unit_price: required(form, "unit_price"), tax_category: optional(form, "tax_category") ?? "standard",
    is_active: id ? form.get("is_active") === "on" : true,
  };
  const state = await attempt(() => api(id ? `/services/${id}` : "/services", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Service added.");
  revalidatePath("/services");
  return state;
}

export async function saveFund(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = { name: required(form, "name"), administrator: optional(form, "administrator"), phone: optional(form, "phone"), email: optional(form, "email"), claims_address: optional(form, "claims_address"), is_active: id ? form.get("is_active") === "on" : true };
  const state = await attempt(() => api(id ? `/medical-aid/funds/${id}` : "/medical-aid/funds", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Fund added.");
  revalidatePath("/medical-aid-funds");
  return state;
}

export async function addMembership(patientId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/patients/${patientId}/medical-aid`, { method: "POST", body: {
      fund_id: required(form, "fund_id"), plan_name: optional(form, "plan_name"), membership_number: required(form, "membership_number"),
      dependant_code: optional(form, "dependant_code"), principal_member_name: optional(form, "principal_member_name") } }),
    "Medical aid added.",
  );
  revalidatePath(`/patients/${patientId}`);
  return state;
}

export async function verifyMembership(patientId: string, membershipId: string, method: string): Promise<void> {
  await api(`/medical-aid/memberships/${membershipId}/verify`, { method: "POST", body: { method } });
  revalidatePath(`/patients/${patientId}`);
}
