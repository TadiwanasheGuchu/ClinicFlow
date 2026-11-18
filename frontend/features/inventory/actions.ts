"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { PurchaseOrder } from "@/types/api";

const int = (form: FormData, key: string) => Number(required(form, key));

export async function receiveStock(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api("/inventory/receipts", { method: "POST", body: {
      branch_id: required(form, "branch_id"), item_id: required(form, "item_id"), quantity: int(form, "quantity"),
      unit_cost: optional(form, "unit_cost") ?? "0", batch_number: optional(form, "batch_number"),
      expiry_date: optional(form, "expiry_date"), supplier_id: optional(form, "supplier_id"), reference: optional(form, "reference"),
    } }),
    "Stock received.",
  );
  revalidatePath("/stock");
  return state;
}

export async function recordUsage(_: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api("/inventory/usage", { method: "POST", body: {
      branch_id: required(form, "branch_id"), item_id: required(form, "item_id"), quantity: int(form, "quantity"),
      reason: optional(form, "reason"),
    } }),
    "Usage recorded.",
  );
  revalidatePath("/stock");
  return state;
}

export async function adjustBatch(itemId: string, batchId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/inventory/batches/${batchId}/adjust`, { method: "POST", body: {
      kind: required(form, "kind"), quantity: int(form, "quantity"), reason: required(form, "reason"),
    } }),
    "Stock adjusted.",
  );
  revalidatePath(`/stock/items/${itemId}`);
  return state;
}

export async function transferBatch(itemId: string, batchId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/inventory/batches/${batchId}/transfer`, { method: "POST", body: {
      to_branch_id: required(form, "to_branch_id"), quantity: int(form, "quantity"), reason: optional(form, "reason"),
    } }),
    "Stock transferred.",
  );
  revalidatePath(`/stock/items/${itemId}`);
  return state;
}

function poBody(form: FormData) {
  const rows = new Set<string>();
  for (const key of form.keys()) {
    const m = /^line\.(\d+)\.item_id$/.exec(key);
    if (m) rows.add(m[1]!);
  }
  const lines = [...rows]
    .map((r) => ({ item_id: optional(form, `line.${r}.item_id`), quantity_ordered: Number(optional(form, `line.${r}.quantity`) ?? 0), unit_cost: optional(form, `line.${r}.unit_cost`) ?? "0" }))
    .filter((l) => l.item_id && l.quantity_ordered > 0);
  return { branch_id: required(form, "branch_id"), supplier_id: required(form, "supplier_id"), expected_on: optional(form, "expected_on"), notes: optional(form, "notes"), lines };
}

export async function savePurchaseOrder(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  let created: PurchaseOrder | undefined;
  const state = await attempt(async () => {
    created = await api<PurchaseOrder>(id ? `/inventory/purchase-orders/${id}` : "/inventory/purchase-orders", { method: id ? "PUT" : "POST", body: poBody(form) });
  }, "Purchase order saved.");
  if (!id && created) redirect(`/stock/purchase-orders/${created.id}`);
  revalidatePath(`/stock/purchase-orders/${id}`);
  return state;
}

export async function placePurchaseOrder(id: string, _: FormState): Promise<FormState> {
  const state = await attempt(() => api(`/inventory/purchase-orders/${id}/place`, { method: "POST" }), "Order placed.");
  revalidatePath(`/stock/purchase-orders/${id}`);
  return state;
}

export async function cancelPurchaseOrder(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() => api(`/inventory/purchase-orders/${id}/cancel`, { method: "POST", body: { reason: required(form, "reason") } }), "Order cancelled.");
  revalidatePath(`/stock/purchase-orders/${id}`);
  return state;
}

export async function receivePurchaseOrder(id: string, _: FormState, form: FormData): Promise<FormState> {
  const lines = [...form.keys()]
    .map((k) => /^recv\.([0-9a-f-]{36})\.quantity$/.exec(k)?.[1])
    .filter((x): x is string => !!x)
    .map((lineId) => ({
      line_id: lineId, quantity: Number(optional(form, `recv.${lineId}.quantity`) ?? 0),
      batch_number: optional(form, `recv.${lineId}.batch_number`), expiry_date: optional(form, `recv.${lineId}.expiry_date`),
    }))
    .filter((l) => l.quantity > 0);
  if (!lines.length) return { error: "Enter the quantity received for at least one line." };
  const state = await attempt(
    () => api(`/inventory/purchase-orders/${id}/receive`, { method: "POST", body: { lines, reference: optional(form, "reference") } }),
    "Delivery received into stock.",
  );
  revalidatePath(`/stock/purchase-orders/${id}`);
  return state;
}

export async function saveItem(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = {
    sku: required(form, "sku").toUpperCase(), name: required(form, "name"), category: optional(form, "category"), unit: required(form, "unit"),
    reorder_level: Number(optional(form, "reorder_level") ?? 0), track_expiry: form.get("track_expiry") === "on",
    is_active: id ? form.get("is_active") === "on" : true,
  };
  const state = await attempt(() => api(id ? `/inventory/items/${id}` : "/inventory/items", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Item added.");
  revalidatePath("/stock/setup");
  return state;
}

export async function saveSupplier(id: string | null, _: FormState, form: FormData): Promise<FormState> {
  const body = {
    name: required(form, "name"), contact_person: optional(form, "contact_person"), phone: optional(form, "phone"),
    email: optional(form, "email"), address: optional(form, "address"), is_active: id ? form.get("is_active") === "on" : true,
  };
  const state = await attempt(() => api(id ? `/inventory/suppliers/${id}` : "/inventory/suppliers", { method: id ? "PUT" : "POST", body }), id ? "Saved." : "Supplier added.");
  revalidatePath("/stock/setup");
  return state;
}
