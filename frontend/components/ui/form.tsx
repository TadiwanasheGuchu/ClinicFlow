"use client";

import { type ComponentProps, createContext, useContext, useTransition } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/layout";
import type { FormState } from "@/lib/form";

const PendingContext = createContext<boolean | null>(null);

/**
 * Form that submits to a server action without React's automatic reset, so entered values
 * survive a validation error from the API. Pass `pending` from useActionState.
 */
export function ActionForm({
  action,
  pending,
  children,
  ...props
}: Omit<ComponentProps<"form">, "action" | "onSubmit"> & {
  action: (form: FormData) => void;
  pending: boolean;
}) {
  const [, startTransition] = useTransition();
  return (
    <PendingContext.Provider value={pending}>
      <form
        {...props}
        noValidate={false}
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
          if (submitter?.name) data.set(submitter.name, submitter.value);
          startTransition(() => action(data));
        }}
      >
        {children}
      </form>
    </PendingContext.Provider>
  );
}

export function SubmitButton({
  children,
  pendingLabel = "Saving…",
  variant = "primary",
  name,
  value,
  className,
}: {
  children: React.ReactNode;
  className?: string;
  pendingLabel?: string;
  variant?: "primary" | "danger" | "secondary";
  name?: string;
  value?: string;
}) {
  const contextPending = useContext(PendingContext);
  const { pending: formPending } = useFormStatus();
  const pending = contextPending ?? formPending;
  return (
    <Button type="submit" variant={variant} disabled={pending} aria-disabled={pending} name={name} value={value} className={className}>
      {pending ? pendingLabel : children}
    </Button>
  );
}

export function FormMessage({ state }: { state: FormState }) {
  if (state.error) return <Notice tone="error">{state.error}</Notice>;
  if (state.success) return <Notice tone="success">{state.success}</Notice>;
  return null;
}
