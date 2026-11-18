"use client";

import { useActionState, useEffect, useState } from "react";

import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { cn } from "@/lib/cn";
import { type FormState, initialFormState } from "@/lib/form";

/**
 * A server-action form whose fields are passed as children (they can be rendered on the
 * server). With `reset`, the form remounts after a successful submission so entries such as
 * stock receipts or shifts can't be submitted twice by accident.
 */
export function QuickForm({
  action,
  children,
  submit,
  pendingLabel,
  variant = "primary",
  reset = false,
  className,
}: {
  action: (state: FormState, form: FormData) => Promise<FormState>;
  children?: React.ReactNode;
  submit?: React.ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "secondary" | "danger";
  reset?: boolean;
  className?: string;
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [key, setKey] = useState(0);
  useEffect(() => {
    if (reset && state.success) setKey((k) => k + 1);
  }, [state, reset]);
  return (
    <div className="flex flex-col gap-2">
      <FormMessage state={state} />
      <ActionForm key={key} action={formAction} pending={pending} className={cn("flex flex-wrap items-end gap-3", className)}>
        {children}
        {submit && <SubmitButton variant={variant} pendingLabel={pendingLabel}>{submit}</SubmitButton>}
      </ActionForm>
    </div>
  );
}
