"use client";

import Link from "next/link";
import { useActionState } from "react";

import { describedBy, Field, Input, Select, Textarea, Checkbox } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { Notice } from "@/components/ui/layout";
import { formatDate } from "@/lib/format";
import { type FormState, initialFormState } from "@/lib/form";
import type { Patient, PatientSummary } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function PatientForm({ action, patient, allowBookNext = false }: { action: Action; patient?: Patient; allowBookNext?: boolean }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  const candidates = (state.code === "possible_duplicate" ? (state.details?.candidates as PatientSummary[]) : null) ?? null;
  const c = patient?.emergency_contact;

  const text = (id: string, label: string, value: string | null | undefined, opts: { required?: boolean; type?: string; hint?: string; placeholder?: string; className?: string } = {}) => (
    <Field id={id} label={label} required={opts.required} hint={opts.hint} error={err(id)} className={opts.className}>
      <Input id={id} name={id} type={opts.type ?? "text"} required={opts.required} defaultValue={value ?? ""} placeholder={opts.placeholder} aria-invalid={!!err(id)} aria-describedby={describedBy(id, err(id), opts.hint)} />
    </Field>
  );

  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-3xl flex-col gap-5">
      {candidates ? (
        <Notice tone="error">
          <p className="font-medium">This person may already be registered.</p>
          <ul className="mt-2 flex flex-col gap-1">
            {candidates.map((p) => (
              <li key={p.id}>
                <Link href={`/patients/${p.id}`} className="underline" target="_blank">
                  {p.first_name} {p.last_name}
                </Link>{" "}
                · born {formatDate(p.date_of_birth)} · <span className="font-mono text-sm">{p.patient_number}</span>
                {p.phone && ` · ${p.phone}`}
              </li>
            ))}
          </ul>
          <Checkbox className="mt-3" name="confirm_not_duplicate" label="I have checked: this is a different person" required />
        </Notice>
      ) : (
        <FormMessage state={state} />
      )}

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Identity</legend>
        {text("first_name", "First name(s)", patient?.first_name, { required: true })}
        {text("last_name", "Surname", patient?.last_name, { required: true })}
        {text("date_of_birth", "Date of birth", patient?.date_of_birth, { required: true, type: "date" })}
        <Field id="sex" label="Sex" hint="Record where clinically relevant.">
          <Select id="sex" name="sex" defaultValue={patient?.sex ?? ""} aria-describedby="sex-hint">
            <option value="">Not recorded</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="intersex">Intersex</option>
            <option value="unknown">Unknown</option>
          </Select>
        </Field>
        {text("id_number", "ID or passport number", patient?.id_number)}
        {text("nationality", "Nationality", patient?.nationality)}
      </fieldset>

      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Contact</legend>
        {text("phone", "Mobile number", patient?.phone, { type: "tel", placeholder: "+264 81 000 0000" })}
        {text("email", "Email", patient?.email, { type: "email" })}
        <Field id="preferred_channel" label="Preferred reminders" hint="Reminders never contain clinical information.">
          <Select id="preferred_channel" name="preferred_channel" defaultValue={patient?.preferred_channel ?? "sms"} aria-describedby="preferred_channel-hint">
            <option value="sms">SMS</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="email">Email</option>
            <option value="phone">Phone call</option>
            <option value="none">No reminders</option>
          </Select>
        </Field>
        <Field id="address" label="Physical address" className="sm:col-span-2">
          <Textarea id="address" name="address" rows={2} defaultValue={patient?.address ?? ""} />
        </Field>
      </fieldset>

      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-3">
        <legend className="mb-2 text-sm font-medium text-text">Emergency contact</legend>
        {text("emergency_contact.name", "Name", c?.name)}
        {text("emergency_contact.phone", "Phone", c?.phone, { type: "tel" })}
        {text("emergency_contact.relationship", "Relationship", c?.relationship)}
        {err("emergency_contact") && <p className="text-xs text-danger-text sm:col-span-3">{err("emergency_contact")}</p>}
      </fieldset>

      <div className="flex gap-2">
        {patient ? (
          <SubmitButton>Save patient</SubmitButton>
        ) : (
          <>
            <SubmitButton name="next" value="view" pendingLabel="Registering…">Register patient</SubmitButton>
            {allowBookNext && (
              <SubmitButton name="next" value="book" variant="secondary" pendingLabel="Registering…">
                Register and book
              </SubmitButton>
            )}
          </>
        )}
      </div>
    </ActionForm>
  );
}
