"use client";

import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function TenantStatusControl({ action, name, suspend }: { action: Action; name: string; suspend: boolean }) {
  const [state, formAction] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  const label = suspend ? `Suspend ${name}` : `Reactivate ${name}`;
  if (!open) {
    return (
      <div className="flex flex-col items-end gap-1">
        <FormMessage state={state} />
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          {suspend ? "Suspend" : "Reactivate"}
        </Button>
      </div>
    );
  }
  return (
    <form action={formAction} className="flex flex-col items-end gap-2">
      <FormMessage state={state} />
      <label className="sr-only" htmlFor={`reason-${name}`}>Reason</label>
      <Input id={`reason-${name}`} name="reason" required minLength={3} placeholder="Reason (audited)" className="w-56" />
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <SubmitButton variant={suspend ? "danger" : "primary"}>{label}</SubmitButton>
      </div>
    </form>
  );
}
