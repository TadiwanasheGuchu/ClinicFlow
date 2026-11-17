"use client";

import { useActionState } from "react";

import { describedBy, Field, Input } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { initialFormState } from "@/lib/form";
import type { Organisation } from "@/types/api";

import { updateOrganisation } from "./actions";

export function OrganisationForm({ organisation }: { organisation: Organisation }) {
  const [state, action, pending] = useActionState(updateOrganisation, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  const s = organisation.settings;

  const input = (
    id: string,
    label: string,
    value: string | number | null,
    opts: { required?: boolean; type?: string; hint?: string; mono?: boolean; min?: number; max?: number } = {},
  ) => (
    <Field id={id} label={label} required={opts.required} hint={opts.hint} error={err(id)}>
      <Input
        id={id}
        name={id}
        type={opts.type ?? "text"}
        required={opts.required}
        min={opts.min}
        max={opts.max}
        defaultValue={value ?? ""}
        className={opts.mono ? "font-mono" : undefined}
        aria-invalid={!!err(id)}
        aria-describedby={describedBy(id, err(id), opts.hint)}
      />
    </Field>
  );

  return (
    <ActionForm action={action} pending={pending} className="flex max-w-3xl flex-col gap-5">
      <FormMessage state={state} />
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Practice details</legend>
        {input("name", "Practice name", organisation.name, { required: true })}
        {input("legal_name", "Registered business name", organisation.legal_name)}
        {input("registration_number", "Business registration number", organisation.registration_number)}
        {input("phone", "Phone", organisation.phone, { type: "tel" })}
        {input("email", "Email", organisation.email, { type: "email" })}
      </fieldset>
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Numbering and scheduling defaults</legend>
        {input("settings.patient_number_prefix", "Patient number prefix", s.patient_number_prefix, { required: true, mono: true, hint: "1–5 capital letters, e.g. P → P-000231." })}
        {input("settings.invoice_number_prefix", "Invoice number prefix", s.invoice_number_prefix, { required: true, mono: true, hint: "1–5 capital letters." })}
        {input("settings.default_appointment_minutes", "Default appointment length (minutes)", s.default_appointment_minutes, { required: true, type: "number", min: 5, max: 240 })}
        {input("settings.booking_buffer_minutes", "Buffer between bookings (minutes)", s.booking_buffer_minutes, { required: true, type: "number", min: 0, max: 120 })}
      </fieldset>
      <div>
        <SubmitButton>Save organisation</SubmitButton>
      </div>
    </ActionForm>
  );
}
