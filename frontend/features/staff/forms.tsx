"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useState } from "react";

import { Button } from "@/components/ui/button";
import { describedBy, Field, Input, Select, Textarea } from "@/components/ui/field";
import { FormMessage, SubmitButton } from "@/components/ui/form";
import { type FormState, initialFormState } from "@/lib/form";

type Option = { id: string; name: string };
type Assignment = { role_id: string; branch_id: string | null };
type Action = (state: FormState, form: FormData) => Promise<FormState>;

function AssignmentsEditor({
  roles,
  branches,
  initial,
}: {
  roles: Option[];
  branches: Option[];
  initial: Assignment[];
}) {
  const [rows, setRows] = useState(() =>
    (initial.length ? initial : [{ role_id: "", branch_id: null }]).map((a, i) => ({ ...a, key: i })),
  );
  const [nextKey, setNextKey] = useState(rows.length);

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium text-text">Roles</legend>
      <p className="mb-1 text-xs text-text-muted">
        A role can apply to the whole organisation or to one branch. You can only grant
        permissions you hold yourself.
      </p>
      {rows.map((row, index) => (
        <div key={row.key} className="flex flex-wrap items-center gap-2">
          <Select
            aria-label={`Role ${index + 1}`}
            name={`assignment.${row.key}.role`}
            defaultValue={row.role_id}
            required
            className="w-56"
          >
            <option value="">Choose a role</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
          <Select
            aria-label={`Branch for role ${index + 1}`}
            name={`assignment.${row.key}.branch`}
            defaultValue={row.branch_id ?? ""}
            className="w-56"
          >
            <option value="">All branches</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} only
              </option>
            ))}
          </Select>
          {rows.length > 1 && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Remove role ${index + 1}`}
              onClick={() => setRows((r) => r.filter((x) => x.key !== row.key))}
            >
              <X size={16} strokeWidth={1.5} aria-hidden />
            </Button>
          )}
        </div>
      ))}
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setRows((r) => [...r, { role_id: "", branch_id: null, key: nextKey }]);
            setNextKey((k) => k + 1);
          }}
        >
          <Plus size={16} strokeWidth={1.5} aria-hidden /> Add another role
        </Button>
      </div>
    </fieldset>
  );
}

export function InviteForm({ action, roles, branches }: { action: Action; roles: Option[]; branches: Option[] }) {
  const [state, formAction] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  return (
    <form action={formAction} className="flex max-w-2xl flex-col gap-4">
      <FormMessage state={state} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="full_name" label="Full name" required error={err("full_name")}>
          <Input id="full_name" name="full_name" required aria-invalid={!!err("full_name")} aria-describedby={describedBy("full_name", err("full_name"))} />
        </Field>
        <Field id="email" label="Email address" required hint="They sign in with this address." error={err("email")}>
          <Input id="email" name="email" type="email" required aria-invalid={!!err("email")} aria-describedby={describedBy("email", err("email"), "x")} />
        </Field>
      </div>
      <AssignmentsEditor roles={roles} branches={branches} initial={[]} />
      <div>
        <SubmitButton pendingLabel="Sending…">Invite</SubmitButton>
      </div>
    </form>
  );
}

export function RolesForm({
  action,
  roles,
  branches,
  initial,
}: {
  action: Action;
  roles: Option[];
  branches: Option[];
  initial: Assignment[];
}) {
  const [state, formAction] = useActionState(action, initialFormState);
  return (
    <form action={formAction} className="flex flex-col gap-4">
      <FormMessage state={state} />
      <AssignmentsEditor roles={roles} branches={branches} initial={initial} />
      <div>
        <SubmitButton>Save roles</SubmitButton>
      </div>
    </form>
  );
}

/** Suspend / reactivate with a mandatory reason; the button names the person. */
export function StatusForm({
  action,
  personName,
  mode,
}: {
  action: Action;
  personName: string;
  mode: "suspend" | "reactivate";
}) {
  const [state, formAction] = useActionState(action, initialFormState);
  const [confirming, setConfirming] = useState(false);
  const label = mode === "suspend" ? `Suspend ${personName}` : `Reactivate ${personName}`;

  if (!confirming && !state.error) {
    return (
      <>
        <FormMessage state={state} />
        <Button variant={mode === "suspend" ? "danger" : "secondary"} onClick={() => setConfirming(true)} className="mt-2">
          {label}
        </Button>
      </>
    );
  }
  return (
    <form action={formAction} className="flex max-w-lg flex-col gap-3">
      <FormMessage state={state} />
      <p className="text-base text-text">
        {mode === "suspend"
          ? `${personName} will lose access to this organisation immediately.`
          : `${personName} will regain access with their current roles.`}
      </p>
      <Field id="reason" label="Reason" required hint="Recorded in the audit log.">
        <Textarea id="reason" name="reason" required minLength={3} rows={2} aria-describedby="reason-hint" />
      </Field>
      <div className="flex gap-2">
        <SubmitButton variant={mode === "suspend" ? "danger" : "primary"}>{label}</SubmitButton>
        <Button variant="secondary" onClick={() => setConfirming(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
