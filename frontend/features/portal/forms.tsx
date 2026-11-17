"use client";

import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { SlotPicker } from "@/features/appointments/slot-picker";
import { formatNAD } from "@/lib/format";
import { type FormState, initialFormState } from "@/lib/form";
import type { PortalInfo, PortalPatient } from "@/lib/portal";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

// Patient-facing controls: 16px text and 44px targets (docs/DESIGN.md §5).
const big = "h-11 text-md";

const CHANNELS = (
  <>
    <option value="sms">SMS</option>
    <option value="whatsapp">WhatsApp</option>
    <option value="email">Email</option>
    <option value="none">No reminders</option>
  </>
);

export function RegisterSelfForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <Field id="first_name" label="First name(s)" required error={err("first_name")}>
        <Input id="first_name" name="first_name" required autoComplete="given-name" className={big} />
      </Field>
      <Field id="last_name" label="Surname" required error={err("last_name")}>
        <Input id="last_name" name="last_name" required autoComplete="family-name" className={big} />
      </Field>
      <Field id="date_of_birth" label="Date of birth" required error={err("date_of_birth")}>
        <Input id="date_of_birth" name="date_of_birth" type="date" required autoComplete="bday" className={big} />
      </Field>
      <Field id="phone" label="Mobile number" required error={err("phone")}>
        <Input id="phone" name="phone" type="tel" required autoComplete="tel" placeholder="+264 81 000 0000" className={big} />
      </Field>
      <Field id="preferred_channel" label="Send appointment reminders by" hint="Reminders only include the date, time and place — never medical details.">
        <Select id="preferred_channel" name="preferred_channel" defaultValue="sms" className={big} aria-describedby="preferred_channel-hint">{CHANNELS}</Select>
      </Field>
      <SubmitButton className={big} pendingLabel="Saving…">Continue</SubmitButton>
    </ActionForm>
  );
}

export function LinkForm({ action }: { action: Action }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <Field id="code" label="Link code from the practice" required hint="8 letters and numbers, e.g. ABCD-2345.">
        <Input id="code" name="code" required autoComplete="one-time-code" className={`${big} font-mono uppercase`} aria-describedby="code-hint" />
      </Field>
      <Field id="link_dob" label="Your date of birth" required>
        <Input id="link_dob" name="date_of_birth" type="date" required className={big} />
      </Field>
      <SubmitButton className={big} pendingLabel="Checking…">Connect my record</SubmitButton>
    </ActionForm>
  );
}

export function BookingWizard({ action, info, slug, today, maxDate }: { action: Action; info: PortalInfo; slug: string; today: string; maxDate: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [branchId, setBranchId] = useState(info.branches.find((b) => info.providers.some((p) => p.branch_ids.includes(b.id)))?.id ?? "");
  const providers = info.providers.filter((p) => p.branch_ids.includes(branchId));
  const [providerId, setProviderId] = useState(providers[0]?.id ?? "");
  const [typeId, setTypeId] = useState(info.appointment_types[0]?.id ?? "");
  const [date, setDate] = useState(today);

  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-5">
      <FormMessage state={state} />
      {info.branches.length > 1 && (
        <Field id="branch_id" label="Where" required>
          <Select id="branch_id" name="branch_id" value={branchId} onChange={(e) => { setBranchId(e.target.value); setProviderId(""); }} className={big}>
            {info.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
        </Field>
      )}
      {info.branches.length <= 1 && <input type="hidden" name="branch_id" value={branchId} />}
      <Field id="provider_id" label="Who would you like to see?" required>
        <Select id="provider_id" name="provider_id" value={providerId} onChange={(e) => setProviderId(e.target.value)} required className={big}>
          <option value="">Choose</option>
          {providers.map((p) => <option key={p.id} value={p.id}>{p.display_name}{p.specialty ? ` — ${p.specialty}` : ""}</option>)}
        </Select>
      </Field>
      <Field id="appointment_type_id" label="Type of appointment" required>
        <Select id="appointment_type_id" name="appointment_type_id" value={typeId} onChange={(e) => setTypeId(e.target.value)} className={big}>
          {info.appointment_types.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.duration_minutes} min · {formatNAD(Number(t.fee))}</option>)}
        </Select>
      </Field>
      <Field id="date" label="Date" required>
        <Input id="date" type="date" min={today} max={maxDate} value={date} onChange={(e) => setDate(e.target.value)} className={big} />
      </Field>
      <div>
        <p className="mb-2 text-md font-medium">Available times</p>
        <SlotPicker providerId={providerId} branchId={branchId} typeId={typeId} date={date} portalSlug={slug} large />
      </div>
      <SubmitButton className={big} pendingLabel="Booking…">Book this time</SubmitButton>
    </ActionForm>
  );
}

export function ChangeAppointment({
  reschedule,
  cancel,
  slug,
  providerId,
  branchId,
  typeId,
  today,
  maxDate,
}: {
  reschedule: Action;
  cancel: Action;
  slug: string;
  providerId: string | null;
  branchId: string | null;
  typeId: string | null;
  today: string;
  maxDate: string;
}) {
  const [mode, setMode] = useState<"none" | "move" | "cancel">("none");
  const [rState, rAction, rPending] = useActionState(reschedule, initialFormState);
  const [cState, cAction, cPending] = useActionState(cancel, initialFormState);
  const [date, setDate] = useState(today);

  if (mode === "none") {
    return (
      <div className="flex flex-col gap-2">
        <FormMessage state={rState.success ? rState : cState} />
        {providerId && <Button variant="secondary" className={big} onClick={() => setMode("move")}>Change date or time</Button>}
        <Button variant="secondary" className={big} onClick={() => setMode("cancel")}>Cancel appointment</Button>
      </div>
    );
  }
  if (mode === "move" && providerId && branchId && typeId) {
    return (
      <ActionForm action={rAction} pending={rPending} className="flex flex-col gap-4">
        <FormMessage state={rState} />
        <Field id="new_date" label="New date" required>
          <Input id="new_date" type="date" min={today} max={maxDate} value={date} onChange={(e) => setDate(e.target.value)} className={big} />
        </Field>
        <SlotPicker providerId={providerId} branchId={branchId} typeId={typeId} date={date} portalSlug={slug} large />
        <SubmitButton className={big}>Move my appointment</SubmitButton>
        <Button variant="secondary" className={big} onClick={() => setMode("none")}>Keep current time</Button>
      </ActionForm>
    );
  }
  return (
    <ActionForm action={cAction} pending={cPending} className="flex flex-col gap-4">
      <FormMessage state={cState} />
      <Field id="reason" label="Reason (optional)">
        <Textarea id="reason" name="reason" rows={2} maxLength={300} className="text-md" />
      </Field>
      <SubmitButton className={big} variant="danger" pendingLabel="Cancelling…">Yes, cancel this appointment</SubmitButton>
      <Button variant="secondary" className={big} onClick={() => setMode("none")}>Keep my appointment</Button>
    </ActionForm>
  );
}

export function ContactForm({ action, patient }: { action: Action; patient: PortalPatient }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <Field id="phone" label="Mobile number" error={err("phone")}>
        <Input id="phone" name="phone" type="tel" defaultValue={patient.phone ?? ""} className={big} />
      </Field>
      <Field id="email" label="Email" error={err("email")}>
        <Input id="email" name="email" type="email" defaultValue={patient.email ?? ""} className={big} />
      </Field>
      <Field id="address" label="Physical address">
        <Textarea id="address" name="address" rows={2} defaultValue={patient.address ?? ""} className="text-md" />
      </Field>
      <Field id="preferred_channel" label="Send appointment reminders by" hint="Reminders never include medical details.">
        <Select id="preferred_channel" name="preferred_channel" defaultValue={patient.preferred_channel === "phone" ? "none" : patient.preferred_channel} className={big} aria-describedby="preferred_channel-hint">{CHANNELS}</Select>
      </Field>
      <SubmitButton className={big}>Save my details</SubmitButton>
      <p className="text-sm text-text-muted">To change your name or date of birth, please contact the practice.</p>
    </ActionForm>
  );
}
