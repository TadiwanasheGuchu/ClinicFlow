"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { CONDITION_LABEL } from "@/lib/dental";
import { type FormState, initialFormState } from "@/lib/form";
import type { Branch, DentalPlan, Service } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

function useRows(initial: number[], reset: number) {
  const [rows, setRows] = useState<number[]>(initial);
  useEffect(() => {
    if (reset) setRows([0]);
  }, [reset]);
  return {
    rows,
    add: () => setRows((r) => [...r, Math.max(-1, ...r) + 1]),
    remove: (k: number) => setRows((r) => r.filter((x) => x !== k)),
  };
}

/** Findings for one or more teeth, recorded against the open consultation. */
export function ChartEntryForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (state.success) setKey((k) => k + 1);
  }, [state]);
  const { rows, add, remove } = useRows([0], key);
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      {rows.map((r, i) => (
        <div key={r} className="flex flex-wrap items-end gap-3">
          <Field id={`ct-${r}`} label={`Tooth ${i + 1}`} hint="FDI, e.g. 16"><Input id={`ct-${r}`} name={`chart.${r}.tooth`} inputMode="numeric" pattern="[1-8][1-8]" className="w-20 text-right font-mono" /></Field>
          <Field id={`cs-${r}`} label="Surfaces" hint="M O D B L P I"><Input id={`cs-${r}`} name={`chart.${r}.surfaces`} pattern="[MODBLPImodblpi]{0,7}" className="w-24 font-mono uppercase" /></Field>
          <Field id={`cc-${r}`} label="Finding">
            <Select id={`cc-${r}`} name={`chart.${r}.condition`} defaultValue="caries" className="w-48">{Object.entries(CONDITION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          </Field>
          <Field id={`cn-${r}`} label="Note"><Input id={`cn-${r}`} name={`chart.${r}.note`} className="w-56" /></Field>
          {rows.length > 1 && <Button variant="ghost" size="sm" onClick={() => remove(r)} aria-label={`Remove tooth ${i + 1}`}><X size={16} strokeWidth={1.5} aria-hidden /></Button>}
        </div>
      ))}
      <div><Button variant="ghost" size="sm" onClick={add}><Plus size={16} strokeWidth={1.5} aria-hidden /> Add another tooth</Button></div>
      <div><SubmitButton>Record on chart</SubmitButton></div>
    </ActionForm>
  );
}

export function PlanForm({ action, branches, services, plan }: { action: Action; branches: Branch[]; services: Service[]; plan?: DentalPlan }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const initial = plan?.items.map((_, i) => i) ?? [0];
  const { rows, add, remove } = useRows(initial, 0);
  const item = (r: number) => plan?.items[r];
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="pl-title" label="Plan" required className="min-w-64 flex-1"><Input id="pl-title" name="title" required minLength={2} defaultValue={plan?.title ?? ""} placeholder="e.g. Restorative treatment" /></Field>
        <Field id="pl-branch" label="Branch"><Select id="pl-branch" name="branch_id" defaultValue={plan?.branch_id} className="w-44">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Treatment</legend>
        {rows.map((r, i) => (
          <div key={r} className="flex flex-wrap items-end gap-3 rounded border border-border p-2">
            <Field id={`it-${r}`} label="Tooth"><Input id={`it-${r}`} name={`item.${r}.tooth`} defaultValue={item(r)?.tooth ?? ""} inputMode="numeric" pattern="[1-8][1-8]" className="w-20 text-right font-mono" /></Field>
            <Field id={`is-${r}`} label="Surfaces"><Input id={`is-${r}`} name={`item.${r}.surfaces`} defaultValue={item(r)?.surfaces ?? ""} className="w-24 font-mono uppercase" /></Field>
            <Field id={`isv-${r}`} label="From price list">
              <Select id={`isv-${r}`} name={`item.${r}.service_id`} defaultValue={item(r)?.service_id ?? ""} className="w-60">
                <option value="">—</option>
                {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
            <Field id={`ip-${r}`} label="Procedure" hint="Optional with a price-list item"><Input id={`ip-${r}`} name={`item.${r}.procedure`} defaultValue={item(r)?.procedure ?? ""} className="w-56" /></Field>
            <Field id={`if-${r}`} label="Fee (N$)" hint="Blank: list price"><Input id={`if-${r}`} name={`item.${r}.fee`} defaultValue={item(r)?.fee ?? ""} inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" className="w-28 text-right font-mono" /></Field>
            {rows.length > 1 && <Button variant="ghost" size="sm" onClick={() => remove(r)} aria-label={`Remove treatment ${i + 1}`}><X size={16} strokeWidth={1.5} aria-hidden /></Button>}
          </div>
        ))}
        <div><Button variant="ghost" size="sm" onClick={add}><Plus size={16} strokeWidth={1.5} aria-hidden /> Add treatment</Button></div>
      </fieldset>
      <Field id="pl-notes" label="Notes for the quotation"><Textarea id="pl-notes" name="notes" rows={2} defaultValue={plan?.notes ?? ""} /></Field>
      <div><SubmitButton>{plan ? "Save draft" : "Create draft plan"}</SubmitButton></div>
    </ActionForm>
  );
}
