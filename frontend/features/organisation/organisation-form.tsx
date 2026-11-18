"use client";

import { useActionState } from "react";

import { Checkbox, describedBy, Field, Input } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { initialFormState } from "@/lib/form";
import type { Organisation } from "@/types/api";

import { updateOrganisation } from "./actions";

export function OrganisationForm({ organisation, publicUrl }: { organisation: Organisation; publicUrl: string }) {
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
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Patient portal and online booking</legend>
        <Checkbox name="settings.portal_enabled" defaultChecked={s.portal_enabled} label="Patients can book online" description="Only practitioners and appointment types marked for online booking are offered." className="sm:col-span-2" />
        <Field id="slug" label="Portal address" required hint={`${publicUrl}/book/${organisation.slug ?? "…"}`} error={err("slug")}>
          <Input id="slug" name="slug" required defaultValue={organisation.slug ?? ""} pattern="[a-z0-9][a-z0-9\-]{1,58}[a-z0-9]" className="font-mono" aria-describedby={describedBy("slug", err("slug"), "x")} />
        </Field>
        <Checkbox name="settings.online_auto_confirm" defaultChecked={s.online_auto_confirm} label="Confirm online bookings automatically" description="Otherwise they arrive as requests for reception to confirm." className="pt-6" />
        {input("settings.online_min_notice_hours", "Minimum notice (hours)", s.online_min_notice_hours, { required: true, type: "number", min: 0, max: 168 })}
        {input("settings.online_max_days_ahead", "Bookable up to (days ahead)", s.online_max_days_ahead, { required: true, type: "number", min: 1, max: 365 })}
        {input("settings.online_cancel_cutoff_hours", "Online changes close (hours before)", s.online_cancel_cutoff_hours, { required: true, type: "number", min: 0, max: 168 })}
        {input("settings.online_max_upcoming", "Most upcoming online bookings per patient", s.online_max_upcoming, { required: true, type: "number", min: 1, max: 20 })}
      </fieldset>
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Billing</legend>
        <Checkbox name="settings.vat_registered" defaultChecked={s.vat_registered} label="Practice is VAT-registered" description="Confirm with your accountant which services are VAT-exempt; set each service’s VAT category." className="sm:col-span-2" />
        {input("settings.vat_rate", "VAT rate (%)", s.vat_rate, { required: true, mono: true })}
        {input("settings.vat_number", "VAT number", s.vat_number, { mono: true })}
        {input("settings.invoice_due_days", "Invoices due after (days)", s.invoice_due_days, { required: true, type: "number", min: 0, max: 365 })}
      </fieldset>
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Reminders</legend>
        <Checkbox name="settings.reminders_enabled" defaultChecked={s.reminders_enabled} label="Send appointment reminders" description="Messages contain only the practice, branch, date, time and reference — never clinical details." className="sm:col-span-2" />
        {input("settings.reminder_hours_before", "Send reminder (hours before)", s.reminder_hours_before, { required: true, type: "number", min: 1, max: 168 })}
      </fieldset>
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">Specialty modules</legend>
        <Checkbox name="settings.specialty_modules" value="dental" defaultChecked={s.specialty_modules?.includes("dental")} label="Dental" description="Tooth chart, treatment plans and quotations." />
        <Checkbox name="settings.specialty_modules" value="physiotherapy" defaultChecked={s.specialty_modules?.includes("physiotherapy")} label="Physiotherapy" description="Episodes of care, sessions and outcome measures." />
      </fieldset>
      <div>
        <SubmitButton>Save organisation</SubmitButton>
      </div>
    </ActionForm>
  );
}
