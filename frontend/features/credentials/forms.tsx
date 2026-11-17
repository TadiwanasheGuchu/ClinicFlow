"use client";

import { useActionState } from "react";

import { describedBy, Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { PROFESSIONS } from "@/lib/appointments";
import { type FormState, initialFormState } from "@/lib/form";
import type { StaffProfile } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function ProfileForm({ action, profile }: { action: Action; profile: StaffProfile | null }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="profession" label="Profession" required error={err("profession")}>
          <Select id="profession" name="profession" required defaultValue={profile?.profession ?? ""}>
            <option value="">Choose</option>
            {Object.entries(PROFESSIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        <Field id="specialty" label="Specialty"><Input id="specialty" name="specialty" defaultValue={profile?.specialty ?? ""} /></Field>
        <Field id="registration_body" label="Registration body" hint="e.g. HPCNA">
          <Input id="registration_body" name="registration_body" defaultValue={profile?.registration_body ?? ""} aria-describedby="registration_body-hint" />
        </Field>
        <Field id="professional_number" label="Registration number" error={err("professional_number")}>
          <Input id="professional_number" name="professional_number" className="font-mono" defaultValue={profile?.professional_number ?? ""} aria-describedby={describedBy("professional_number", err("professional_number"))} />
        </Field>
        <Field id="licence_expiry_date" label="Licence valid until" error={err("licence_expiry_date")}>
          <Input id="licence_expiry_date" name="licence_expiry_date" type="date" defaultValue={profile?.licence_expiry_date ?? ""} />
        </Field>
      </div>
      <p className="text-xs text-text-muted">Changing the profession, body, number or expiry date resets verification.</p>
      <div><SubmitButton>Save professional details</SubmitButton></div>
    </ActionForm>
  );
}

export function VerifyForm({ action, personName }: { action: Action; personName: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-xl flex-col gap-3">
      <FormMessage state={state} />
      <Field id="note" label="How you checked" required hint="e.g. “Checked HPCNA public register on 17 Nov 2026”. Recorded in the audit log.">
        <Textarea id="note" name="note" required minLength={3} rows={2} aria-describedby="note-hint" />
      </Field>
      <div className="flex gap-2">
        <SubmitButton name="decision" value="verified">Verify registration of {personName}</SubmitButton>
        <SubmitButton name="decision" value="rejected" variant="secondary">Reject</SubmitButton>
      </div>
    </ActionForm>
  );
}
