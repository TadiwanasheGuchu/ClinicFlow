"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { Notice } from "@/components/ui/layout";
import { NOTE_SECTIONS, NOTE_TYPE_LABEL, OBSERVATIONS } from "@/lib/clinical";
import { type FormState, initialFormState } from "@/lib/form";
import type { ClinicalNote } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

/** Remount (clear) a form after each successful submission so values can't be resubmitted
 *  by accident — important for clinical entries (no duplicate vitals or prescriptions). */
function useResetKey(state: FormState): number {
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (state.success) setKey((k) => k + 1);
  }, [state]);
  return key;
}

/** Draft editor for a new note, an existing draft, or an amendment of a signed note. */
export function NoteEditor({
  action,
  note,
  amending,
  patientName,
  canSign,
  onCancel,
}: {
  action: Action;
  note?: ClinicalNote;
  amending?: ClinicalNote;
  patientName: string;
  canSign: boolean;
  onCancel?: () => void;
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  // A new note or an amendment is created on the first successful submit; close the editor
  // so a second click can't create a duplicate. Existing drafts re-render from the server.
  useEffect(() => {
    if (state.success && onCancel) onCancel();
  }, [state, onCancel]);
  const source = note ?? amending;
  const [noteType, setNoteType] = useState(source?.note_type ?? "consultation");
  const [confirmSign, setConfirmSign] = useState(false);
  const sections = NOTE_SECTIONS[noteType] ?? [];

  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      {amending && (
        <Field id="reason" label="Reason for amendment" required hint="The signed original is kept and stays visible.">
          <Input id="reason" name="reason" required minLength={5} aria-describedby="reason-hint" />
        </Field>
      )}
      <Field id={`type-${source?.id ?? "new"}`} label="Note type">
        <Select id={`type-${source?.id ?? "new"}`} name="note_type" value={noteType} onChange={(e) => setNoteType(e.target.value)} className="w-56">
          {Object.entries(NOTE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </Field>
      {sections.map((s) => (
        <Field key={s.key} id={`${source?.id ?? "new"}-${s.key}`} label={s.label}>
          <Textarea id={`${source?.id ?? "new"}-${s.key}`} name={`section.${s.key}`} rows={s.key === "text" ? 6 : 3} defaultValue={source?.content[s.key] ?? ""} />
        </Field>
      ))}
      {confirmSign ? (
        <div className="flex flex-col gap-2 rounded border border-primary bg-primary-subtle p-3">
          <p className="text-base">Signing makes this note permanent for <strong>{patientName}</strong>. Later corrections will be recorded as amendments.</p>
          <div className="flex gap-2">
            <SubmitButton name="intent" value="sign" pendingLabel="Signing…">Sign note for {patientName}</SubmitButton>
            <Button variant="secondary" onClick={() => setConfirmSign(false)}>Not yet</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <SubmitButton name="intent" value="save" variant="secondary">Save draft</SubmitButton>
          {canSign && <Button onClick={() => setConfirmSign(true)}>Sign…</Button>}
          {note && <SubmitButton name="intent" value="discard" variant="secondary" pendingLabel="Discarding…">Discard draft</SubmitButton>}
          {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
        </div>
      )}
    </ActionForm>
  );
}

export function AmendButton(props: { action: Action; amending: ClinicalNote; patientName: string; canSign: boolean }) {
  const [open, setOpen] = useState(false);
  if (!open) return <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>Amend</Button>;
  return <div className="mt-3 border-t border-border pt-3"><NoteEditor {...props} onCancel={() => setOpen(false)} /></div>;
}

export function NewNote(props: { action: Action; patientName: string; canSign: boolean }) {
  const [open, setOpen] = useState(false);
  if (!open) return <Button variant="secondary" onClick={() => setOpen(true)}><Plus size={16} strokeWidth={1.5} aria-hidden /> New note</Button>;
  return <NoteEditor {...props} onCancel={() => setOpen(false)} />;
}

export function VitalsForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {OBSERVATIONS.map((o) => (
          <Field key={o.type} id={`obs-${o.type}`} label={`${o.label} (${o.unit})`}>
            <Input id={`obs-${o.type}`} name={`obs.${o.type}`} type="number" inputMode="decimal" step={o.step} min={o.min} max={o.max} className="text-right font-mono" />
          </Field>
        ))}
      </div>
      <div><SubmitButton>Record vital signs</SubmitButton></div>
    </ActionForm>
  );
}

export function DiagnosisForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="dx-description" label="Diagnosis" required className="min-w-72 flex-1"><Input id="dx-description" name="description" required minLength={2} /></Field>
        <Field id="dx-code" label="ICD-10 code" hint="Optional, e.g. J06.9"><Input id="dx-code" name="code" className="w-32 font-mono uppercase" pattern="[A-Ta-tV-Zv-z][0-9][0-9ABab](\.[0-9A-Za-z]{1,4})?" aria-describedby="dx-code-hint" /></Field>
        <SubmitButton>Add diagnosis</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function ReferralForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Field id="ref-to" label="Refer to" required><Input id="ref-to" name="receiving_provider" required placeholder="Practitioner or facility" /></Field>
        <Field id="ref-spec" label="Specialty"><Input id="ref-spec" name="receiving_specialty" /></Field>
        <Field id="ref-urg" label="Urgency"><Select id="ref-urg" name="urgency" defaultValue="routine"><option value="routine">Routine</option><option value="urgent">Urgent</option></Select></Field>
      </div>
      <Field id="ref-reason" label="Reason for referral" required><Textarea id="ref-reason" name="reason" rows={3} required minLength={5} /></Field>
      <div><SubmitButton>Issue referral</SubmitButton></div>
    </ActionForm>
  );
}

type Row = { key: number };

export function PrescriptionForm({ action, patientName }: { action: Action; patientName: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  const [rows, setRows] = useState<Row[]>([{ key: 0 }]);
  const [next, setNext] = useState(1);
  useEffect(() => {
    if (resetKey) setRows([{ key: 0 }]);
  }, [resetKey]);
  const matches = state.code === "allergy_warning" ? ((state.details?.matches ?? []) as { medication: string; allergy: string }[]) : [];

  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      {matches.length > 0 ? (
        <Notice tone="error">
          <p className="font-medium">Possible allergy for {patientName}</p>
          <ul className="list-inside list-disc">{matches.map((m) => <li key={m.medication + m.allergy}>{m.medication}: recorded allergy to {m.allergy}</li>)}</ul>
          <p className="mt-1 text-sm">This is a basic name check, not a drug-interaction database.</p>
          <p className="mt-1 text-sm">Change the medication, or confirm below to prescribe anyway. The check runs again on every submission.</p>
          <Checkbox className="mt-2" name="acknowledge_allergy_warning" label="I have reviewed this and still want to prescribe" />
          <Field id="ack-reason" label="Clinical reason (required to override)" className="mt-2"><Input id="ack-reason" name="acknowledgement_reason" minLength={5} /></Field>
        </Notice>
      ) : (
        <FormMessage state={state} />
      )}
      {rows.map((row, index) => (
        <fieldset key={row.key} className="grid gap-2 rounded border border-border p-3 sm:grid-cols-4">
          <legend className="px-1 text-sm font-medium">Item {index + 1}</legend>
          <Field id={`m-${row.key}`} label="Medication" required className="sm:col-span-2"><Input id={`m-${row.key}`} name={`item.${row.key}.medication`} required /></Field>
          <Field id={`s-${row.key}`} label="Strength"><Input id={`s-${row.key}`} name={`item.${row.key}.strength`} placeholder="500 mg" /></Field>
          <Field id={`r-${row.key}`} label="Route"><Input id={`r-${row.key}`} name={`item.${row.key}.route`} placeholder="Oral" /></Field>
          <Field id={`d-${row.key}`} label="Dose" required><Input id={`d-${row.key}`} name={`item.${row.key}.dose`} required placeholder="1 tablet" /></Field>
          <Field id={`f-${row.key}`} label="Frequency" required><Input id={`f-${row.key}`} name={`item.${row.key}.frequency`} required placeholder="three times daily" /></Field>
          <Field id={`du-${row.key}`} label="Duration"><Input id={`du-${row.key}`} name={`item.${row.key}.duration`} placeholder="5 days" /></Field>
          <Field id={`q-${row.key}`} label="Quantity"><Input id={`q-${row.key}`} name={`item.${row.key}.quantity`} placeholder="15" /></Field>
          <Field id={`i-${row.key}`} label="Instructions" className="sm:col-span-3"><Input id={`i-${row.key}`} name={`item.${row.key}.instructions`} placeholder="Take after meals" /></Field>
          {rows.length > 1 && (
            <div className="flex items-end"><Button variant="ghost" size="sm" onClick={() => setRows((r) => r.filter((x) => x.key !== row.key))} aria-label={`Remove item ${index + 1}`}><X size={16} strokeWidth={1.5} aria-hidden /> Remove</Button></div>
          )}
        </fieldset>
      ))}
      <div className="flex gap-2">
        <Button variant="ghost" onClick={() => { setRows((r) => [...r, { key: next }]); setNext((n) => n + 1); }}><Plus size={16} strokeWidth={1.5} aria-hidden /> Add item</Button>
      </div>
      <div><SubmitButton pendingLabel="Issuing…">Issue prescription for {patientName}</SubmitButton></div>
    </ActionForm>
  );
}

/** Small "reason" form for corrections and cancellations. */
export function ReasonAction({ action, label, hiddenName, hiddenValue, danger = false }: { action: Action; label: string; hiddenName?: string; hiddenValue?: string; danger?: boolean }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  if (!open) return (<><FormMessage state={state} /><Button size="sm" variant="secondary" onClick={() => setOpen(true)}>{label}</Button></>);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-wrap items-end justify-end gap-2">
      <FormMessage state={state} />
      {hiddenName && <input type="hidden" name={hiddenName} value={hiddenValue} />}
      <label className="sr-only" htmlFor={`reason-${label}`}>Reason</label>
      <Input id={`reason-${label}`} name="reason" required minLength={3} placeholder="Reason (recorded)" className="w-56" />
      <SubmitButton variant={danger ? "danger" : "primary"}>{label}</SubmitButton>
      <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
    </ActionForm>
  );
}

export function SimpleAction({ action, label, pendingLabel, variant = "primary" }: { action: (state: FormState) => Promise<FormState>; label: string; pendingLabel?: string; variant?: "primary" | "secondary" | "danger" }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={() => formAction()} pending={pending} className="flex flex-col items-start gap-2">
      <FormMessage state={state} />
      <SubmitButton variant={variant} pendingLabel={pendingLabel}>{label}</SubmitButton>
    </ActionForm>
  );
}

export function AllergyForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const resetKey = useResetKey(state);
  return (
    <ActionForm key={resetKey} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id="al-substance" label="Substance" required><Input id="al-substance" name="substance" required minLength={2} className="w-56" /></Field>
        <Field id="al-reaction" label="Reaction"><Input id="al-reaction" name="reaction" className="w-56" /></Field>
        <Field id="al-severity" label="Severity"><Select id="al-severity" name="severity" defaultValue="unknown" className="w-40"><option value="mild">Mild</option><option value="moderate">Moderate</option><option value="severe">Severe</option><option value="unknown">Unknown</option></Select></Field>
        <SubmitButton>Record allergy</SubmitButton>
      </div>
    </ActionForm>
  );
}
