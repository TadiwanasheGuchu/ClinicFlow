"use client";

import { useActionState } from "react";

import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";

export function LinkCodeButton({ action }: { action: (state: FormState) => Promise<FormState> }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={() => formAction()} pending={pending} className="flex flex-col items-start gap-3">
      {state.success ? (
        <div role="status" className="rounded border border-primary bg-primary-subtle px-3 py-2 text-base text-text">
          {state.success}
        </div>
      ) : (
        <FormMessage state={state} />
      )}
      <SubmitButton variant="secondary" pendingLabel="Creating…">{state.success ? "Create a new code" : "Create link code"}</SubmitButton>
    </ActionForm>
  );
}
