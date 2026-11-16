"use client";

import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/layout";
import type { FormState } from "@/lib/form";

export function SubmitButton({
  children,
  pendingLabel = "Saving…",
  variant = "primary",
}: {
  children: React.ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "danger" | "secondary";
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant={variant} disabled={pending} aria-disabled={pending}>
      {pending ? pendingLabel : children}
    </Button>
  );
}

export function FormMessage({ state }: { state: FormState }) {
  if (state.error) return <Notice tone="error">{state.error}</Notice>;
  if (state.success) return <Notice tone="success">{state.success}</Notice>;
  return null;
}
