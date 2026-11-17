"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useEffect, useState } from "react";

import { PatientPicker } from "@/components/patients/patient-picker";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { METHOD, nad, TAX_CATEGORY } from "@/lib/billing";
import { type FormState, initialFormState } from "@/lib/form";
import type { AidMembership, Fund, InvoiceItem, PatientSummary, Service } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

function useResetKey(state: FormState): number {
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (state.success) setKey((k) => k + 1);
  }, [state]);
  return key;
}

type Line = { key: number; service: string; description: string; price: string; quantity: string };

function LinesEditor({ services, initial }: { services: Service[]; initial: Line[] }) {
  const [lines, setLines] = useState<Line[]>(initial.length ? initial : [{ key: 0, service: "", description: "", price: "", quantity: "1" }]);
  const [next, setNext] = useState(lines.length);
  const update = (key: number, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const byId = new Map(services.map((s) => [s.id, s]));
  const estimate = lines.reduce((sum, l) => sum + Number(l.price || byId.get(l.service)?.unit_price || 0) * Number(l.quantity || 0), 0);

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">Lines</legend>
      {lines.map((l, index) => (
        <div key={l.key} className="grid items-end gap-2 sm:grid-cols-[2fr_2fr_1fr_0.6fr_auto]">
          <Field id={`svc-${l.key}`} label={index === 0 ? "Service" : ""}>
            <Select id={`svc-${l.key}`} name={`line.${l.key}.service`} value={l.service} aria-label={`Line ${index + 1} service`}
              onChange={(e) => { const s = byId.get(e.target.value); update(l.key, { service: e.target.value, description: s ? "" : l.description, price: s ? "" : l.price }); }}>
              <option value="">Other (describe)</option>
              {services.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.name} · {nad(s.unit_price)}</option>)}
            </Select>
          </Field>
          <Field id={`desc-${l.key}`} label={index === 0 ? "Description" : ""}>
            <Input id={`desc-${l.key}`} name={`line.${l.key}.description`} value={l.description} aria-label={`Line ${index + 1} description`}
              placeholder={l.service ? byId.get(l.service)?.name : "Description"} required={!l.service} onChange={(e) => update(l.key, { description: e.target.value })} />
          </Field>
          <Field id={`price-${l.key}`} label={index === 0 ? "Unit price (N$)" : ""}>
            <Input id={`price-${l.key}`} name={`line.${l.key}.unit_price`} value={l.price} inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" aria-label={`Line ${index + 1} unit price`}
              placeholder={l.service ? byId.get(l.service)?.unit_price : "0.00"} required={!l.service} className="text-right font-mono" onChange={(e) => update(l.key, { price: e.target.value })} />
          </Field>
          <Field id={`qty-${l.key}`} label={index === 0 ? "Qty" : ""}>
            <Input id={`qty-${l.key}`} name={`line.${l.key}.quantity`} value={l.quantity} inputMode="decimal" aria-label={`Line ${index + 1} quantity`} className="text-right font-mono" onChange={(e) => update(l.key, { quantity: e.target.value })} />
          </Field>
          <Button variant="ghost" size="sm" aria-label={`Remove line ${index + 1}`} disabled={lines.length === 1} onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}><X size={16} strokeWidth={1.5} aria-hidden /></Button>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => { setLines((ls) => [...ls, { key: next, service: "", description: "", price: "", quantity: "1" }]); setNext((n) => n + 1); }}>
          <Plus size={16} strokeWidth={1.5} aria-hidden /> Add line
        </Button>
        <span className="text-sm text-text-muted">Before VAT: <span className="font-mono text-text">{nad(estimate)}</span></span>
      </div>
    </fieldset>
  );
}

export function NewInvoiceForm({ action, services, branches, patient }: { action: Action; services: Service[]; branches: { id: string; name: string }[]; patient: PatientSummary | null }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-4xl flex-col gap-4">
      <FormMessage state={state} />
      <Field id="patient" label="Patient" required><PatientPicker initial={patient} /></Field>
      {branches.length > 1 ? (
        <Field id="branch_id" label="Branch" required><Select id="branch_id" name="branch_id" className="w-56">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
      ) : <input type="hidden" name="branch_id" value={branches[0]?.id} />}
      <LinesEditor services={services} initial={[]} />
      <Field id="notes" label="Note on invoice"><Textarea id="notes" name="notes" rows={2} maxLength={1000} /></Field>
      <div><SubmitButton pendingLabel="Saving…">Save draft</SubmitButton></div>
    </ActionForm>
  );
}

export function DraftEditor({ action, services, items, notes }: { action: Action; services: Service[]; items: InvoiceItem[]; notes: string | null }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const initial = items.map((i, k) => ({ key: k, service: i.service_id ?? "", description: i.service_id ? "" : i.description, price: i.service_id ? "" : i.unit_price, quantity: String(Number(i.quantity)) }));
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <LinesEditor services={services} initial={initial} />
      <Field id="notes" label="Note on invoice"><Textarea id="notes" name="notes" rows={2} defaultValue={notes ?? ""} maxLength={1000} /></Field>
      <div><SubmitButton variant="secondary">Save draft</SubmitButton></div>
    </ActionForm>
  );
}

export function PaymentForm({ action, due }: { action: Action; due: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="pay-amount" label="Amount (N$)" required><Input id="pay-amount" name="amount" required defaultValue={Number(due).toFixed(2)} inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" className="w-32 text-right font-mono" /></Field>
        <Field id="pay-method" label="Method" required>
          <Select id="pay-method" name="method" defaultValue="cash" className="w-40">{["cash", "card", "eft", "mobile"].map((m) => <option key={m} value={m}>{METHOD[m]}</option>)}</Select>
        </Field>
        <Field id="pay-ref" label="Reference" hint="Card slip, EFT or transaction number"><Input id="pay-ref" name="reference" className="w-56" aria-describedby="pay-ref-hint" /></Field>
        <SubmitButton>Record payment</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function AdjustForm({ action, kind, max }: { action: Action; kind: "credit" | "refund"; max: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  const [open, setOpen] = useState(false);
  const label = kind === "credit" ? "Issue credit note" : "Record refund";
  if (!open) return (<><FormMessage state={state} /><Button variant="secondary" size="sm" onClick={() => setOpen(true)}>{label}…</Button></>);
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-3 rounded border border-border p-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={`${kind}-amount`} label={`Amount (max ${nad(max)})`} required><Input id={`${kind}-amount`} name="amount" required defaultValue={Number(max).toFixed(2)} inputMode="decimal" className="w-32 text-right font-mono" /></Field>
        {kind === "refund" && (
          <>
            <Field id="refund-method" label="Paid out by" required><Select id="refund-method" name="method" className="w-40">{["cash", "card", "eft", "mobile"].map((m) => <option key={m} value={m}>{METHOD[m]}</option>)}</Select></Field>
            <Field id="refund-ref" label="Reference"><Input id="refund-ref" name="reference" className="w-48" /></Field>
          </>
        )}
        <Field id={`${kind}-reason`} label="Reason" required className="min-w-64 flex-1"><Input id={`${kind}-reason`} name="reason" required minLength={3} /></Field>
      </div>
      <div className="flex gap-2"><SubmitButton variant="danger">{label}</SubmitButton><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </ActionForm>
  );
}

export function ConfirmAction({ action, label, confirm, variant = "primary" }: { action: (state: FormState) => Promise<FormState>; label: string; confirm: string; variant?: "primary" | "danger" }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  if (!open) return (<div className="flex flex-col items-start gap-2"><FormMessage state={state} /><Button variant={variant} onClick={() => setOpen(true)}>{label}…</Button></div>);
  return (
    <ActionForm action={() => formAction()} pending={pending} className="flex flex-col gap-2 rounded border border-primary bg-primary-subtle p-3">
      <FormMessage state={state} />
      <p className="text-base">{confirm}</p>
      <div className="flex gap-2"><SubmitButton variant={variant}>{label}</SubmitButton><Button variant="secondary" onClick={() => setOpen(false)}>Not yet</Button></div>
    </ActionForm>
  );
}

export function ClaimPrepareForm({ action, memberships }: { action: Action; memberships: AidMembership[] }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-wrap items-end gap-3">
      <FormMessage state={state} />
      <Field id="membership_id" label="Medical aid">
        <Select id="membership_id" name="membership_id" className="w-72">{memberships.map((m) => <option key={m.id} value={m.id}>{m.fund_name} · {m.membership_number}{m.dependant_code ? ` (${m.dependant_code})` : ""}</option>)}</Select>
      </Field>
      <SubmitButton>Prepare claim</SubmitButton>
    </ActionForm>
  );
}

export function ClaimEditForm({ action, codes, amount }: { action: Action; codes: string[]; amount: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="codes" label="ICD-10 codes" hint="Separate with commas, e.g. J06.9, Z00.0"><Input id="codes" name="diagnosis_codes" defaultValue={codes.join(", ")} className="w-72 font-mono uppercase" aria-describedby="codes-hint" /></Field>
        <Field id="claimed" label="Claimed (N$)"><Input id="claimed" name="claimed_amount" defaultValue={amount} inputMode="decimal" className="w-32 text-right font-mono" /></Field>
        <SubmitButton variant="secondary">Save claim</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function ClaimTransitionForm({ action, label, fields, danger = false }: { action: Action; label: string; fields: ("fund_reference" | "submission_method" | "approved_amount" | "reason")[]; danger?: boolean }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  if (!fields.length) return (<ActionForm action={formAction} pending={pending} className="inline-flex flex-col gap-1"><FormMessage state={state} /><SubmitButton variant={danger ? "danger" : "secondary"}>{label}</SubmitButton></ActionForm>);
  if (!open) return (<div className="inline-flex flex-col gap-1"><FormMessage state={state} /><Button variant={danger ? "danger" : "secondary"} onClick={() => setOpen(true)}>{label}…</Button></div>);
  return (
    <ActionForm action={formAction} pending={pending} className="flex w-full flex-col gap-3 rounded border border-border p-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        {fields.includes("submission_method") && (
          <Field id="sub-method" label="Sent by" required><Select id="sub-method" name="submission_method" className="w-40"><option value="email">Email</option><option value="fund_portal">Fund portal</option><option value="paper">Paper</option><option value="other">Other</option></Select></Field>
        )}
        {fields.includes("fund_reference") && <Field id="fund-ref" label="Fund reference"><Input id="fund-ref" name="fund_reference" className="w-48" /></Field>}
        {fields.includes("approved_amount") && <Field id="approved" label="Approved (N$)" required><Input id="approved" name="approved_amount" required inputMode="decimal" className="w-32 text-right font-mono" /></Field>}
        {fields.includes("reason") && <Field id="t-reason" label="Reason" required className="min-w-64 flex-1"><Input id="t-reason" name="reason" required minLength={3} /></Field>}
      </div>
      <div className="flex gap-2"><SubmitButton variant={danger ? "danger" : "primary"}>{label}</SubmitButton><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </ActionForm>
  );
}

export function RemittanceForm({ action, max }: { action: Action; max: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="rem-amount" label={`Amount received (up to ${nad(max)})`} required><Input id="rem-amount" name="amount" required defaultValue={Number(max).toFixed(2)} inputMode="decimal" className="w-36 text-right font-mono" /></Field>
        <Field id="rem-ref" label="Remittance reference" required><Input id="rem-ref" name="reference" required className="w-56" /></Field>
        <SubmitButton>Record fund payment</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function ServiceForm({ action, item }: { action: Action; item?: Service }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  const id = (k: string) => `${item?.id ?? "new"}-${k}`;
  return (
    <ActionForm key={item ? undefined : key} action={formAction} pending={pending} className="flex flex-col gap-2">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={id("code")} label="Code" required><Input id={id("code")} name="code" required defaultValue={item?.code} className="w-28 font-mono uppercase" /></Field>
        <Field id={id("name")} label="Name" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required defaultValue={item?.name} /></Field>
        <Field id={id("tariff")} label="Tariff code"><Input id={id("tariff")} name="tariff_code" defaultValue={item?.tariff_code ?? ""} className="w-28 font-mono" /></Field>
        <Field id={id("price")} label="Price (N$)" required><Input id={id("price")} name="unit_price" required defaultValue={item?.unit_price} inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" className="w-28 text-right font-mono" /></Field>
        <Field id={id("tax")} label="VAT"><Select id={id("tax")} name="tax_category" defaultValue={item?.tax_category ?? "standard"} className="w-36">{Object.entries(TAX_CATEGORY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="Offered" className="pb-2" />}
        <SubmitButton variant={item ? "secondary" : "primary"}>{item ? "Save" : "Add service"}</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function FundForm({ action, item }: { action: Action; item?: Fund }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  const id = (k: string) => `${item?.id ?? "new"}-${k}`;
  return (
    <ActionForm key={item ? undefined : key} action={formAction} pending={pending} className="flex flex-col gap-2">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={id("name")} label="Fund" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required defaultValue={item?.name} /></Field>
        <Field id={id("admin")} label="Administrator"><Input id={id("admin")} name="administrator" defaultValue={item?.administrator ?? ""} className="w-48" /></Field>
        <Field id={id("phone")} label="Phone"><Input id={id("phone")} name="phone" defaultValue={item?.phone ?? ""} className="w-40" /></Field>
        <Field id={id("email")} label="Claims email"><Input id={id("email")} name="email" type="email" defaultValue={item?.email ?? ""} className="w-56" /></Field>
        {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="Active" className="pb-2" />}
        <SubmitButton variant={item ? "secondary" : "primary"}>{item ? "Save" : "Add fund"}</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function MembershipForm({ action, funds }: { action: Action; funds: Fund[] }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const key = useResetKey(state);
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-2">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="ma-fund" label="Fund" required><Select id="ma-fund" name="fund_id" required className="w-56">{funds.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</Select></Field>
        <Field id="ma-plan" label="Plan / option"><Input id="ma-plan" name="plan_name" className="w-40" /></Field>
        <Field id="ma-number" label="Membership number" required><Input id="ma-number" name="membership_number" required className="w-40 font-mono" /></Field>
        <Field id="ma-dep" label="Dependant code"><Input id="ma-dep" name="dependant_code" className="w-24 font-mono" /></Field>
        <Field id="ma-principal" label="Principal member"><Input id="ma-principal" name="principal_member_name" className="w-48" /></Field>
        <SubmitButton>Add medical aid</SubmitButton>
      </div>
    </ActionForm>
  );
}
