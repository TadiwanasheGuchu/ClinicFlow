"use client";

import { useActionState, useState } from "react";

import { describedBy, Field, Input, Textarea } from "@/components/ui/field";
import { FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";
import type { Branch, Weekday } from "@/types/api";

const DAYS: { key: Weekday; label: string }[] = [
  { key: "mon", label: "Monday" },
  { key: "tue", label: "Tuesday" },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" },
  { key: "sat", label: "Saturday" },
  { key: "sun", label: "Sunday" },
];

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function BranchForm({ action, branch }: { action: Action; branch?: Branch }) {
  const [state, formAction] = useActionState(action, initialFormState);
  const err = (key: string) => state.fieldErrors?.[key];
  const hoursError = Object.entries(state.fieldErrors ?? {}).find(([k]) => k.startsWith("operating_hours"))?.[1];

  const [openDays, setOpenDays] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      DAYS.map(({ key }) => [key, branch ? !!branch.operating_hours[key]?.length : !["sat", "sun"].includes(key)]),
    ),
  );

  return (
    <form action={formAction} className="flex max-w-3xl flex-col gap-5">
      <FormMessage state={state} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="name" label="Branch name" required error={err("name")}>
          <Input id="name" name="name" required defaultValue={branch?.name} aria-invalid={!!err("name")} aria-describedby={describedBy("name", err("name"))} />
        </Field>
        <Field id="branch_code" label="Branch code" required={!branch} hint={branch ? "Codes can’t be changed." : "2–20 capital letters, digits or hyphens."} error={err("branch_code")}>
          <Input id="branch_code" name="branch_code" required={!branch} disabled={!!branch} defaultValue={branch?.branch_code} className="font-mono uppercase" aria-invalid={!!err("branch_code")} aria-describedby={describedBy("branch_code", err("branch_code"), "x")} />
        </Field>
        <Field id="phone" label="Phone" error={err("phone")}>
          <Input id="phone" name="phone" type="tel" defaultValue={branch?.phone ?? ""} placeholder="+264 64 000 000" aria-invalid={!!err("phone")} aria-describedby={describedBy("phone", err("phone"))} />
        </Field>
        <Field id="email" label="Email" error={err("email")}>
          <Input id="email" name="email" type="email" defaultValue={branch?.email ?? ""} aria-invalid={!!err("email")} aria-describedby={describedBy("email", err("email"))} />
        </Field>
        <Field id="address" label="Physical address" error={err("address")} className="sm:col-span-2">
          <Textarea id="address" name="address" rows={2} defaultValue={branch?.address ?? ""} />
        </Field>
      </div>

      <fieldset className="border-t border-border pt-4">
        <legend className="mb-1 text-sm font-medium text-text">Opening hours</legend>
        <p className="mb-3 text-xs text-text-muted">24-hour time. Bookings are only offered inside these hours.</p>
        {hoursError && <p className="mb-2 text-xs text-danger-text">{hoursError}</p>}
        <table className="text-base">
          <tbody>
            {DAYS.map(({ key, label }) => {
              const interval = branch?.operating_hours[key]?.[0];
              const open = openDays[key];
              return (
                <tr key={key} className="h-10">
                  <td className="pr-4">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        name={`hours.${key}.open_day`}
                        checked={open}
                        onChange={(e) => setOpenDays((d) => ({ ...d, [key]: e.target.checked }))}
                        className="size-4 accent-primary"
                      />
                      <span className="w-24">{label}</span>
                    </label>
                  </td>
                  {open ? (
                    <td className="flex items-center gap-2 pt-1.5">
                      <Input type="time" aria-label={`${label} opens`} name={`hours.${key}.open`} defaultValue={interval?.open ?? "08:00"} className="w-32 font-mono" required />
                      <span className="text-text-muted">to</span>
                      <Input type="time" aria-label={`${label} closes`} name={`hours.${key}.close`} defaultValue={interval?.close ?? "17:00"} className="w-32 font-mono" required />
                    </td>
                  ) : (
                    <td className="text-text-muted">Closed</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </fieldset>

      <div>
        <SubmitButton>{branch ? "Save branch" : "Create branch"}</SubmitButton>
      </div>
    </form>
  );
}
