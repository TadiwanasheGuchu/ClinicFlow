"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";
import type { Branch, InventoryItem, PurchaseOrder, Supplier } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;
type Line = { key: number; item_id: string; quantity: string; unit_cost: string };

export function PurchaseOrderForm({ action, branches, suppliers, items, order }: {
  action: Action; branches: Branch[]; suppliers: Supplier[]; items: InventoryItem[]; order?: PurchaseOrder;
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [lines, setLines] = useState<Line[]>(
    order?.lines.map((l, i) => ({ key: i, item_id: l.item_id, quantity: String(l.quantity_ordered), unit_cost: l.unit_cost })) ?? [{ key: 0, item_id: "", quantity: "", unit_cost: "" }],
  );
  const nextKey = () => Math.max(-1, ...lines.map((l) => l.key)) + 1;
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="po-branch" label="Deliver to" required>
          <Select id="po-branch" name="branch_id" defaultValue={order?.branch_id} required className="w-48">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
        </Field>
        <Field id="po-supplier" label="Supplier" required>
          <Select id="po-supplier" name="supplier_id" defaultValue={order?.supplier_id ?? ""} required className="w-64"><option value="">Choose…</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
        </Field>
        <Field id="po-expected" label="Expected"><Input id="po-expected" name="expected_on" type="date" defaultValue={order?.expected_on ?? ""} className="w-40" /></Field>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Lines</legend>
        {lines.map((line, index) => (
          <div key={line.key} className="flex flex-wrap items-end gap-3">
            <Field id={`l-item-${line.key}`} label={`Item ${index + 1}`}>
              <Select id={`l-item-${line.key}`} name={`line.${line.key}.item_id`} defaultValue={line.item_id} className="w-72">
                <option value="">Choose…</option>
                {items.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.unit})</option>)}
              </Select>
            </Field>
            <Field id={`l-qty-${line.key}`} label="Quantity"><Input id={`l-qty-${line.key}`} name={`line.${line.key}.quantity`} type="number" min={1} defaultValue={line.quantity} className="w-24 text-right font-mono" /></Field>
            <Field id={`l-cost-${line.key}`} label="Unit cost (N$)"><Input id={`l-cost-${line.key}`} name={`line.${line.key}.unit_cost`} inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" defaultValue={line.unit_cost} className="w-28 text-right font-mono" /></Field>
            {lines.length > 1 && (
              <Button variant="ghost" size="sm" onClick={() => setLines((ls) => ls.filter((l) => l.key !== line.key))} aria-label={`Remove item ${index + 1}`}>
                <X size={16} strokeWidth={1.5} aria-hidden />
              </Button>
            )}
          </div>
        ))}
        <div>
          <Button variant="ghost" size="sm" onClick={() => setLines((ls) => [...ls, { key: nextKey(), item_id: "", quantity: "", unit_cost: "" }])}>
            <Plus size={16} strokeWidth={1.5} aria-hidden /> Add line
          </Button>
        </div>
      </fieldset>
      <Field id="po-notes" label="Notes"><Textarea id="po-notes" name="notes" rows={2} defaultValue={order?.notes ?? ""} /></Field>
      <div><SubmitButton>{order ? "Save draft" : "Create draft order"}</SubmitButton></div>
    </ActionForm>
  );
}
