"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, describedBy, Field, Input, Select } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";
import { WEEKDAYS } from "@/lib/time";
import type { AppointmentType, AvailabilityWindow, Provider } from "@/types/api";

type Action = (state: FormState, form: FormData) => Promise<FormState>;
type Option = { id: string; name: string };

export function AddProviderForm({ action, members }: { action: Action; members: Option[] }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-xl flex-col gap-4">
      <FormMessage state={state} />
      <Field id="membership_id" label="Staff member" required hint="Their professional registration must already be verified on their staff page.">
        <Select id="membership_id" name="membership_id" required defaultValue="" aria-describedby="membership_id-hint">
          <option value="">Choose a person</option>
          {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </Select>
      </Field>
      <Field id="display_name" label="Name shown on the calendar" hint="Defaults to their full name, e.g. “Dr N. Shikongo”.">
        <Input id="display_name" name="display_name" aria-describedby="display_name-hint" />
      </Field>
      <div><SubmitButton>Add practitioner</SubmitButton></div>
    </ActionForm>
  );
}

export function ProviderSettingsForm({ action, provider }: { action: Action; provider: Provider }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-xl flex-col gap-3">
      <FormMessage state={state} />
      <Field id="display_name" label="Name shown on the calendar" required>
        <Input id="display_name" name="display_name" required defaultValue={provider.display_name} />
      </Field>
      <Checkbox name="booking_enabled" defaultChecked={provider.booking_enabled} label="Accepts bookings" description="Only possible while registration is verified and current." />
      <Checkbox name="online_booking_enabled" defaultChecked={provider.online_booking_enabled} label="Offer online booking to patients" description="Takes effect when the patient portal launches." />
      <div><SubmitButton>Save</SubmitButton></div>
    </ActionForm>
  );
}

type Row = { key: number; weekday: number; branch_id: string; start: string; end: string };

export function AvailabilityEditor({ action, windows, branches }: { action: Action; windows: AvailabilityWindow[]; branches: Option[] }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const [rows, setRows] = useState<Row[]>(() =>
    windows.map((w, i) => ({ key: i, weekday: w.weekday, branch_id: w.branch_id, start: w.start_time.slice(0, 5), end: w.end_time.slice(0, 5) })),
  );
  const [nextKey, setNextKey] = useState(rows.length);
  const add = (weekday: number) => {
    setRows((r) => [...r, { key: nextKey, weekday, branch_id: branches[0]?.id ?? "", start: "08:00", end: "17:00" }]);
    setNextKey((k) => k + 1);
  };
  const copyMondayToWeekdays = () => {
    const monday = rows.filter((r) => r.weekday === 0);
    let k = nextKey;
    const copies = [1, 2, 3, 4].flatMap((d) => monday.map((m) => ({ ...m, weekday: d, key: k++ })));
    setRows((r) => [...r.filter((x) => x.weekday === 0 || x.weekday > 4), ...copies]);
    setNextKey(k);
  };

  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <table className="text-base">
        <tbody>
          {WEEKDAYS.map((day, weekday) => {
            const dayRows = rows.filter((r) => r.weekday === weekday);
            return (
              <tr key={day} className="border-b border-border align-top last:border-b-0">
                <th scope="row" className="w-28 py-2 pr-4 text-left font-medium">{day}</th>
                <td className="py-1.5">
                  <div className="flex flex-col gap-1.5">
                    {dayRows.length === 0 && <span className="py-1.5 text-text-muted">Not working</span>}
                    {dayRows.map((r) => (
                      <div key={r.key} className="flex flex-wrap items-center gap-2">
                        <input type="hidden" name={`row.${r.key}.weekday`} value={weekday} />
                        <Input type="time" name={`row.${r.key}.start`} aria-label={`${day} start`} defaultValue={r.start} required className="w-36 font-mono" onChange={(e) => setRows((rs) => rs.map((x) => (x.key === r.key ? { ...x, start: e.target.value } : x)))} />
                        <span className="text-text-muted">to</span>
                        <Input type="time" name={`row.${r.key}.end`} aria-label={`${day} end`} defaultValue={r.end} required className="w-36 font-mono" onChange={(e) => setRows((rs) => rs.map((x) => (x.key === r.key ? { ...x, end: e.target.value } : x)))} />
                        <span className="text-text-muted">at</span>
                        <Select name={`row.${r.key}.branch`} aria-label={`${day} branch`} defaultValue={r.branch_id} className="w-48" onChange={(e) => setRows((rs) => rs.map((x) => (x.key === r.key ? { ...x, branch_id: e.target.value } : x)))}>
                          {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                        </Select>
                        <Button variant="ghost" size="sm" aria-label={`Remove ${day} ${r.start}–${r.end}`} onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}>
                          <X size={16} strokeWidth={1.5} aria-hidden />
                        </Button>
                      </div>
                    ))}
                  </div>
                </td>
                <td className="py-1.5 pl-2 text-right">
                  <Button variant="ghost" size="sm" onClick={() => add(weekday)} aria-label={`Add hours on ${day}`}>
                    <Plus size={16} strokeWidth={1.5} aria-hidden /> Add
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex gap-2">
        <SubmitButton>Save working hours</SubmitButton>
        <Button variant="secondary" onClick={copyMondayToWeekdays} disabled={!rows.some((r) => r.weekday === 0)}>
          Copy Monday to Tuesday–Friday
        </Button>
      </div>
    </ActionForm>
  );
}

export function LeaveForm({ action, today }: { action: Action; today: string }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-2">
        <Field id="start_date" label="From" required><Input id="start_date" name="start_date" type="date" required defaultValue={today} className="w-40" /></Field>
        <Field id="start_time" label="Time" required><Input id="start_time" name="start_time" type="time" required defaultValue="08:00" className="w-36 font-mono" /></Field>
        <Field id="end_date" label="Until" required><Input id="end_date" name="end_date" type="date" required defaultValue={today} className="w-40" /></Field>
        <Field id="end_time" label="Time" required><Input id="end_time" name="end_time" type="time" required defaultValue="17:00" className="w-36 font-mono" /></Field>
        <Field id="reason" label="Reason"><Input id="reason" name="reason" placeholder="e.g. Annual leave" className="w-56" /></Field>
        <SubmitButton>Block time</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function AppointmentTypeForm({ action, item }: { action: Action; item?: AppointmentType }) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  const id = (k: string) => `${item?.id ?? "new"}-${k}`;
  return (
    <ActionForm action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <Field id={id("name")} label="Name" required error={err("name")}>
          <Input id={id("name")} name="name" required defaultValue={item?.name} className="w-56" aria-invalid={!!err("name")} aria-describedby={describedBy(id("name"), err("name"))} />
        </Field>
        <Field id={id("duration")} label="Minutes" required error={err("duration_minutes")}>
          <Input id={id("duration")} name="duration_minutes" type="number" min={5} max={480} step={5} required defaultValue={item?.duration_minutes ?? 15} className="w-24 font-mono" />
        </Field>
        <Field id={id("buffer")} label="Buffer after" error={err("booking_buffer_minutes")}>
          <Input id={id("buffer")} name="booking_buffer_minutes" type="number" min={0} max={120} step={5} defaultValue={item?.booking_buffer_minutes ?? 0} className="w-24 font-mono" />
        </Field>
        <Field id={id("fee")} label="Fee (N$)" required error={err("fee")}>
          <Input id={id("fee")} name="fee" inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" required defaultValue={item?.fee ?? "0.00"} className="w-28 text-right font-mono" />
        </Field>
        {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="Offered" className="pb-2" />}
        <SubmitButton>{item ? "Save" : "Add type"}</SubmitButton>
      </div>
    </ActionForm>
  );
}
