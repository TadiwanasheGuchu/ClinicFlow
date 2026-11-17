"use client";

import Link from "next/link";
import { useActionState, useEffect, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { Notice } from "@/components/ui/layout";
import { searchPatients } from "@/features/patients/actions";
import { VIOLATION_LABEL } from "@/lib/appointments";
import { formatDate } from "@/lib/format";
import { initialFormState } from "@/lib/form";
import type { AppointmentType, PatientSummary, Provider } from "@/types/api";

import { bookAppointment } from "./actions";
import { SlotPicker } from "./slot-picker";

type Option = { id: string; name: string };

function PatientPicker({ initial }: { initial: PatientSummary | null }) {
  const [selected, setSelected] = useState<PatientSummary | null>(initial);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PatientSummary[]>([]);
  const [, startTransition] = useTransition();

  useEffect(() => {
    const handle = setTimeout(() => {
      startTransition(async () => setResults(await searchPatients(q)));
    }, 250);
    return () => clearTimeout(handle);
  }, [q]);

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-muted px-3 py-2">
        <input type="hidden" name="patient_id" value={selected.id} />
        <span>
          <span className="font-medium">{selected.first_name} {selected.last_name}</span>
          <span className="text-text-muted"> · born {formatDate(selected.date_of_birth)} · </span>
          <span className="font-mono text-sm">{selected.patient_number}</span>
        </span>
        <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Change</Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Input aria-label="Search patients" placeholder="Name, patient number, date of birth or phone" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {results.length > 0 && (
        <ul className="rounded-sm border border-border bg-surface" role="listbox" aria-label="Matching patients">
          {results.map((p) => (
            <li key={p.id}>
              <button type="button" className="flex w-full justify-between gap-3 px-3 py-2 text-left hover:bg-primary-subtle" onClick={() => setSelected(p)}>
                <span><span className="font-medium">{p.last_name}, {p.first_name}</span> <span className="text-text-muted">· born {formatDate(p.date_of_birth)}</span></span>
                <span className="font-mono text-sm">{p.patient_number}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim().length >= 2 && results.length === 0 && <p className="text-sm text-text-muted">No match. <Link href="/patients/new" className="text-primary underline">Register a new patient</Link></p>}
    </div>
  );
}

export function BookingForm({
  patient,
  providers,
  branches,
  types,
  defaults,
  canOverride,
}: {
  patient: PatientSummary | null;
  providers: Provider[];
  branches: Option[];
  types: AppointmentType[];
  defaults: { branchId: string; providerId: string; date: string; today: string };
  canOverride: boolean;
}) {
  const [state, formAction, pending] = useActionState(bookAppointment, initialFormState);
  const [branchId, setBranchId] = useState(defaults.branchId);
  const [providerId, setProviderId] = useState(defaults.providerId);
  const [typeId, setTypeId] = useState(types[0]?.id ?? "");
  const [date, setDate] = useState(defaults.date);
  const [source, setSource] = useState("reception");
  const [override, setOverride] = useState(false);
  const branchProviders = providers.filter((p) => p.branch_ids.includes(branchId));
  const violations = (state.details?.violations as string[] | undefined) ?? [];

  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-3xl flex-col gap-5">
      {state.error && (
        <Notice tone="error">
          {state.error}
          {violations.length > 0 && canOverride && !override && <span> You can book anyway as an override, with a reason.</span>}
        </Notice>
      )}
      {!state.error && <FormMessage state={state} />}

      <Field id="patient" label="Patient" required>
        <PatientPicker initial={patient} />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="branch_id" label="Branch" required>
          <Select id="branch_id" name="branch_id" value={branchId} onChange={(e) => { setBranchId(e.target.value); setProviderId(""); }} required>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
        </Field>
        <Field id="provider_id" label="Practitioner" required hint={branchProviders.length ? undefined : "No bookable practitioners work at this branch."}>
          <Select id="provider_id" name="provider_id" value={providerId} onChange={(e) => setProviderId(e.target.value)} required>
            <option value="">Choose</option>
            {branchProviders.map((p) => <option key={p.id} value={p.id}>{p.display_name}{p.specialty ? ` — ${p.specialty}` : ""}</option>)}
          </Select>
        </Field>
        <Field id="appointment_type_id" label="Appointment type" required>
          <Select id="appointment_type_id" name="appointment_type_id" value={typeId} onChange={(e) => setTypeId(e.target.value)} required>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.duration_minutes} min)</option>)}
          </Select>
        </Field>
        <Field id="booking_source" label="Booked via">
          <Select id="booking_source" name="booking_source" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="reception">At reception</option>
            <option value="phone">Phone</option>
            <option value="walk_in">Walk-in (now, checked in)</option>
          </Select>
        </Field>
      </div>

      {source !== "walk_in" && (
        <div className="flex flex-col gap-3 border-t border-border pt-4">
          <Field id="date" label="Date" required>
            <Input id="date" name="date" type="date" min={defaults.today} value={date} onChange={(e) => setDate(e.target.value)} required className="w-44" />
          </Field>
          {!override && <SlotPicker providerId={providerId} branchId={branchId} typeId={typeId} date={date} />}
          {canOverride && (
            <Checkbox label="Book outside the free times (override)" description="For urgent cases. Needs a reason; recorded in the audit log." checked={override} onChange={(e) => setOverride(e.target.checked)} />
          )}
          {override && (
            <div className="flex flex-wrap items-end gap-3">
              <Field id="manual_time" label="Time" required><Input id="manual_time" name="manual_time" type="time" required className="w-36 font-mono" /></Field>
              <Field id="override_reason" label="Reason for override" required className="min-w-72 flex-1"><Input id="override_reason" name="override_reason" required minLength={3} /></Field>
            </div>
          )}
          {violations.length > 0 && (
            <ul className="list-inside list-disc text-sm text-danger-text">
              {violations.map((v) => <li key={v}>{VIOLATION_LABEL[v] ?? v}</li>)}
            </ul>
          )}
        </div>
      )}

      <Field id="booking_note" label="Note for reception" hint="Administrative only, e.g. “needs wheelchair access”. Never clinical details.">
        <Textarea id="booking_note" name="booking_note" rows={2} maxLength={500} aria-describedby="booking_note-hint" />
      </Field>

      <div><SubmitButton pendingLabel="Booking…">{source === "walk_in" ? "Check in walk-in" : "Book appointment"}</SubmitButton></div>
    </ActionForm>
  );
}
