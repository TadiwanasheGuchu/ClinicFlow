"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { FLAG_LABEL, NEXT_STEPS, STEP_LABEL } from "@/lib/lab";
import { type FormState, initialFormState } from "@/lib/form";
import type { Laboratory, LabOrderDetail, LabOrderStatus, LabTest } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

/** Remount (clear) after a successful submission so an order or result can't be sent twice. */
function useResetKey(state: FormState): number {
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (state.success) setKey((k) => k + 1);
  }, [state]);
  return key;
}

function LabSelect({ id, laboratories, defaultValue }: { id: string; laboratories: Laboratory[]; defaultValue?: string | null }) {
  return (
    <Select id={id} name="laboratory_id" defaultValue={defaultValue ?? ""} className="w-64">
      <option value="">Not decided</option>
      {laboratories.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
    </Select>
  );
}

export function LabOrderForm({ action, tests, laboratories, patientName }: { action: Action; tests: LabTest[]; laboratories: Laboratory[]; patientName: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  const [others, setOthers] = useState<number[]>([0]);
  useEffect(() => {
    if (resetKey) setOthers([0]);
  }, [resetKey]);
  const groups = new Map<string, LabTest[]>();
  for (const t of tests) groups.set(t.category ?? "Other", [...(groups.get(t.category ?? "Other") ?? []), t]);

  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      {tests.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[...groups.entries()].map(([category, list]) => (
            <fieldset key={category} className="rounded border border-border p-3">
              <legend className="px-1 text-sm font-medium">{category}</legend>
              <div className="flex flex-col gap-1.5">
                {list.map((t) => (
                  <Checkbox key={t.id} name="test_id" value={t.id} label={<>{t.name} <span className="font-mono text-xs text-text-muted">{t.code}</span></>} />
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      )}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{tests.length ? "Other tests" : "Tests"}</legend>
        {others.map((key, index) => (
          <div key={key} className="flex items-center gap-2">
            <label className="sr-only" htmlFor={`other-${key}`}>Test name {index + 1}</label>
            <Input id={`other-${key}`} name="other_test" placeholder="Test name, e.g. Lipogram" className="w-80" />
            {others.length > 1 && (
              <Button variant="ghost" size="sm" onClick={() => setOthers((o) => o.filter((k) => k !== key))} aria-label={`Remove test ${index + 1}`}>
                <X size={16} strokeWidth={1.5} aria-hidden />
              </Button>
            )}
          </div>
        ))}
        <div>
          <Button variant="ghost" size="sm" onClick={() => setOthers((o) => [...o, Math.max(...o) + 1])}>
            <Plus size={16} strokeWidth={1.5} aria-hidden /> Add another test
          </Button>
        </div>
      </fieldset>
      <div className="flex flex-wrap items-end gap-3">
        <Field id="lab-laboratory" label="Laboratory"><LabSelect id="lab-laboratory" laboratories={laboratories} /></Field>
        <Field id="lab-urgency" label="Urgency">
          <Select id="lab-urgency" name="urgency" defaultValue="routine" className="w-36"><option value="routine">Routine</option><option value="urgent">Urgent</option></Select>
        </Field>
      </div>
      <Field id="lab-info" label="Clinical information for the laboratory" hint="Printed on the request form.">
        <Textarea id="lab-info" name="clinical_information" rows={2} maxLength={2000} aria-describedby="lab-info-hint" />
      </Field>
      <div><SubmitButton pendingLabel="Requesting…">Request tests for {patientName}</SubmitButton></div>
    </ActionForm>
  );
}

export function ProgressForm({ action, order, laboratories }: { action: Action; order: LabOrderDetail; laboratories: Laboratory[] }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const steps = NEXT_STEPS[order.status as LabOrderStatus] ?? [];
  const [step, setStep] = useState<string>(steps[0] ?? "");
  useEffect(() => setStep(steps[0] ?? ""), [order.status]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!steps.length) return null;
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="next-step" label="Next step">
          <Select id="next-step" name="status" value={step} onChange={(e) => setStep(e.target.value)} className="w-56">
            {steps.map((s) => <option key={s} value={s}>{STEP_LABEL[s]}</option>)}
          </Select>
        </Field>
        {(step === "sent" || step === "processing") && (
          <>
            <Field id="ext-ref" label="Laboratory reference"><Input id="ext-ref" name="external_reference" defaultValue={order.external_reference ?? ""} className="w-44 font-mono" /></Field>
            <Field id="send-lab" label="Laboratory"><LabSelect id="send-lab" laboratories={laboratories} defaultValue={order.laboratory_id} /></Field>
          </>
        )}
        <SubmitButton pendingLabel="Saving…">Update {order.order_number}</SubmitButton>
      </div>
    </ActionForm>
  );
}

type Row = { key: number; itemId: string; analyte: string };

export function ResultForm({ action, order }: { action: Action; order: LabOrderDetail }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  const initial = (): Row[] => {
    const pending = order.items.filter((i) => !i.resulted);
    return (pending.length ? pending : order.items.slice(0, 1)).map((i, n) => ({ key: n, itemId: i.id, analyte: "" }));
  };
  const [rows, setRows] = useState<Row[]>(initial);
  useEffect(() => {
    if (resetKey) setRows(initial());
  }, [resetKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const nextKey = () => Math.max(-1, ...rows.map((r) => r.key)) + 1;

  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <p className="text-sm text-text-muted">For a panel (for example a full blood count), add a value for each analyte. Values are kept exactly as entered.</p>
      {rows.map((row, index) => (
        <fieldset key={row.key} className="grid gap-2 rounded border border-border p-3 sm:grid-cols-6">
          <legend className="px-1 text-sm font-medium">Value {index + 1}</legend>
          <Field id={`t-${row.key}`} label="Test" className="sm:col-span-2">
            <Select id={`t-${row.key}`} name={`row.${row.key}.item_id`} defaultValue={row.itemId}>
              {order.items.map((i) => <option key={i.id} value={i.id}>{i.test_name}</option>)}
            </Select>
          </Field>
          <Field id={`a-${row.key}`} label="Analyte" hint="If different from the test" className="sm:col-span-2"><Input id={`a-${row.key}`} name={`row.${row.key}.analyte`} placeholder="e.g. Haemoglobin" /></Field>
          <Field id={`v-${row.key}`} label="Result" required><Input id={`v-${row.key}`} name={`row.${row.key}.value`} className="font-mono" /></Field>
          <Field id={`u-${row.key}`} label="Unit"><Input id={`u-${row.key}`} name={`row.${row.key}.unit`} className="font-mono" placeholder="g/dL" /></Field>
          <Field id={`r-${row.key}`} label="Reference range" className="sm:col-span-2"><Input id={`r-${row.key}`} name={`row.${row.key}.reference_range`} className="font-mono" placeholder="12.0–15.5" /></Field>
          <Field id={`f-${row.key}`} label="Flag">
            <Select id={`f-${row.key}`} name={`row.${row.key}.flag`} defaultValue="none">
              {Object.entries(FLAG_LABEL).map(([k, v]) => <option key={k} value={k}>{k === "none" ? "No flag" : v}</option>)}
            </Select>
          </Field>
          <Field id={`c-${row.key}`} label="Comment" className="sm:col-span-2"><Input id={`c-${row.key}`} name={`row.${row.key}.comment`} /></Field>
          {rows.length > 1 && (
            <div className="flex items-end"><Button variant="ghost" size="sm" onClick={() => setRows((r) => r.filter((x) => x.key !== row.key))} aria-label={`Remove value ${index + 1}`}><X size={16} strokeWidth={1.5} aria-hidden /> Remove</Button></div>
          )}
        </fieldset>
      ))}
      <div>
        <Button variant="ghost" size="sm" onClick={() => setRows((r) => [...r, { key: nextKey(), itemId: r[r.length - 1]?.itemId ?? order.items[0]!.id, analyte: "" }])}>
          <Plus size={16} strokeWidth={1.5} aria-hidden /> Add value
        </Button>
      </div>
      <div><SubmitButton pendingLabel="Saving…">Record results for {order.order_number}</SubmitButton></div>
    </ActionForm>
  );
}

export function ReviewForm({ action, patientName, abnormal }: { action: Action; patientName: string; abnormal: number }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      {abnormal > 0 && <p className="text-base font-medium text-warning-text">{abnormal} flagged result{abnormal === 1 ? "" : "s"} — check before marking reviewed.</p>}
      <Field id="review-comment" label="Comment or action taken" hint="For example: patient informed, follow-up booked.">
        <Textarea id="review-comment" name="comment" rows={2} maxLength={2000} aria-describedby="review-comment-hint" />
      </Field>
      <div><SubmitButton pendingLabel="Saving…">Mark results reviewed for {patientName}</SubmitButton></div>
    </ActionForm>
  );
}

export function LabTestForm({ action, item }: { action: Action; item?: LabTest }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  const id = (k: string) => `${item?.id ?? "new"}-${k}`;
  return (
    <ActionForm key={item ? undefined : key} action={formAction} pending={pending} className="flex flex-col gap-2">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={id("code")} label="Code" required><Input id={id("code")} name="code" required defaultValue={item?.code} className="w-28 font-mono uppercase" /></Field>
        <Field id={id("name")} label="Test" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required minLength={2} defaultValue={item?.name} /></Field>
        <Field id={id("category")} label="Category"><Input id={id("category")} name="category" defaultValue={item?.category ?? ""} className="w-40" placeholder="Haematology" /></Field>
        <Field id={id("specimen")} label="Specimen"><Input id={id("specimen")} name="specimen_type" defaultValue={item?.specimen_type ?? ""} className="w-40" placeholder="EDTA blood" /></Field>
        {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="Orderable" className="pb-2" />}
        <SubmitButton variant={item ? "secondary" : "primary"}>{item ? "Save" : "Add test"}</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function LaboratoryForm({ action, item }: { action: Action; item?: Laboratory }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  const id = (k: string) => `${item?.id ?? "newlab"}-${k}`;
  return (
    <ActionForm key={item ? undefined : key} action={formAction} pending={pending} className="flex flex-col gap-2">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={id("name")} label="Laboratory" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required minLength={2} defaultValue={item?.name} /></Field>
        <Field id={id("phone")} label="Phone"><Input id={id("phone")} name="phone" type="tel" defaultValue={item?.phone ?? ""} className="w-40" /></Field>
        <Field id={id("email")} label="Email"><Input id={id("email")} name="email" type="email" defaultValue={item?.email ?? ""} className="w-56" /></Field>
        {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="In use" className="pb-2" />}
        <SubmitButton variant={item ? "secondary" : "primary"}>{item ? "Save" : "Add laboratory"}</SubmitButton>
      </div>
    </ActionForm>
  );
}
