"use client";

import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";

import { SlotPicker } from "./slot-picker";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function RescheduleForm({
  action,
  providerId,
  branchId,
  typeId,
  initialDate,
  today,
  canOverride,
}: {
  action: Action;
  providerId: string;
  branchId: string;
  typeId: string;
  initialDate: string;
  today: string;
  canOverride: boolean;
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(initialDate);
  const [override, setOverride] = useState(false);
  if (!open) return (<><FormMessage state={state} /><Button variant="secondary" onClick={() => setOpen(true)} className="mt-1">Reschedule</Button></>);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <Field id="r-date" label="New date" required>
        <Input id="r-date" name="date" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} className="w-44" required />
      </Field>
      {!override && <SlotPicker providerId={providerId} branchId={branchId} typeId={typeId} date={date} />}
      {canOverride && <Checkbox label="Choose a time outside the free times (override)" checked={override} onChange={(e) => setOverride(e.target.checked)} />}
      {override && (
        <div className="flex flex-wrap items-end gap-3">
          <Field id="r-time" label="Time" required><Input id="r-time" name="manual_time" type="time" required className="w-36 font-mono" /></Field>
          <Field id="r-override" label="Reason for override" required className="min-w-72 flex-1"><Input id="r-override" name="override_reason" required minLength={3} /></Field>
        </div>
      )}
      <Field id="r-reason" label="Reason for the change" required>
        <Input id="r-reason" name="reason" required minLength={3} placeholder="e.g. Patient asked for a later time" />
      </Field>
      <div className="flex gap-2">
        <SubmitButton>Move appointment</SubmitButton>
        <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </ActionForm>
  );
}

export function CancelForm({ action, label }: { action: Action; label: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [open, setOpen] = useState(false);
  if (!open) return (<><FormMessage state={state} /><Button variant="secondary" onClick={() => setOpen(true)} className="mt-1">Cancel appointment</Button></>);
  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-lg flex-col gap-3">
      <FormMessage state={state} />
      <Field id="c-reason" label="Reason" required hint="Recorded on the appointment history.">
        <Textarea id="c-reason" name="reason" rows={2} required minLength={3} aria-describedby="c-reason-hint" />
      </Field>
      <div className="flex gap-2">
        <SubmitButton variant="danger" pendingLabel="Cancelling…">{label}</SubmitButton>
        <Button variant="secondary" onClick={() => setOpen(false)}>Keep appointment</Button>
      </div>
    </ActionForm>
  );
}
