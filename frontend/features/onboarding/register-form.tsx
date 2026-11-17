"use client";

import { useActionState } from "react";

import { describedBy, Field, Input } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { initialFormState } from "@/lib/form";

import { registerOrganisation } from "./actions";

export function RegisterOrganisationForm() {
  const [state, action, pending] = useActionState(registerOrganisation, initialFormState);
  const err = (key: string) => state.fieldErrors?.[key];

  const text = (id: string, label: string, opts: { required?: boolean; hint?: string; type?: string; defaultValue?: string; placeholder?: string } = {}) => (
    <Field id={id} label={label} required={opts.required} hint={opts.hint} error={err(id)}>
      <Input
        id={id}
        name={id}
        type={opts.type ?? "text"}
        required={opts.required}
        defaultValue={opts.defaultValue}
        placeholder={opts.placeholder}
        aria-invalid={!!err(id)}
        aria-describedby={describedBy(id, err(id), opts.hint)}
      />
    </Field>
  );

  return (
    <ActionForm action={action} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <div className="grid gap-4 sm:grid-cols-2">
        {text("name", "Practice name", { required: true })}
        {text("legal_name", "Registered business name")}
        {text("registration_number", "Business registration number")}
        {text("phone", "Practice phone", { type: "tel", placeholder: "+264 64 000 000" })}
        {text("email", "Practice email", { type: "email" })}
      </div>
      <fieldset className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-text">First branch</legend>
        {text("first_branch_name", "Branch name", { required: true, defaultValue: "Main branch" })}
        {text("first_branch_code", "Branch code", {
          required: true,
          defaultValue: "MAIN",
          hint: "2–20 capital letters, digits or hyphens. Used on references.",
        })}
      </fieldset>
      <div>
        <SubmitButton pendingLabel="Creating…">Create practice</SubmitButton>
      </div>
    </ActionForm>
  );
}
