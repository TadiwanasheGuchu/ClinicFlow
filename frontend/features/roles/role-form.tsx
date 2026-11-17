"use client";

import { useActionState } from "react";

import { Checkbox, describedBy, Field, Input, Textarea } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { Tag } from "@/components/ui/status";
import { type FormState, initialFormState } from "@/lib/form";
import type { Permission, Role } from "@/types/api";

const AREAS: Record<string, string> = {
  organisation: "Organisation",
  branches: "Branches",
  members: "Staff",
  roles: "Roles",
  audit: "Audit",
  patients: "Patients",
  appointments: "Appointments",
  clinical: "Clinical records",
  prescriptions: "Prescriptions",
  billing: "Billing",
  medical_aid: "Medical aid",
  reports: "Reports",
};

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function RoleForm({
  action,
  permissions,
  role,
  readOnly = false,
}: {
  action: Action;
  permissions: Permission[];
  role?: Role;
  readOnly?: boolean;
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const err = (k: string) => state.fieldErrors?.[k];
  const groups = new Map<string, Permission[]>();
  for (const p of permissions) {
    const area = p.code.split(".")[0]!;
    groups.set(area, [...(groups.get(area) ?? []), p]);
  }

  return (
    <ActionForm action={formAction} pending={pending} className="flex max-w-3xl flex-col gap-4">
      <FormMessage state={state} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="name" label="Role name" required error={err("name")}>
          <Input id="name" name="name" required disabled={readOnly} defaultValue={role?.name} aria-invalid={!!err("name")} aria-describedby={describedBy("name", err("name"))} />
        </Field>
        <Field id="description" label="Description" className="sm:col-span-2">
          <Textarea id="description" name="description" rows={2} disabled={readOnly} defaultValue={role?.description ?? ""} />
        </Field>
      </div>
      <fieldset disabled={readOnly} className="border-t border-border pt-4">
        <legend className="mb-1 text-sm font-medium text-text">Permissions</legend>
        <p className="mb-3 text-xs text-text-muted">
          Marked “Sensitive” require multi-factor sign-in where enforced. Clinical permissions
          will also require verified professional registration.
        </p>
        <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {[...groups.entries()].map(([area, perms]) => (
            <div key={area}>
              <h3 className="mb-1.5 text-sm text-text-muted">{AREAS[area] ?? area}</h3>
              <div className="flex flex-col gap-1.5">
                {perms.map((p) => (
                  <div key={p.code} className="flex items-start gap-2">
                    <Checkbox
                      name="permissions"
                      value={p.code}
                      defaultChecked={role?.permissions.includes(p.code)}
                      label={p.description}
                      description={p.code}
                    />
                    {p.privileged && <Tag>Sensitive</Tag>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </fieldset>
      {!readOnly && (
        <div>
          <SubmitButton>{role ? "Save role" : "Create role"}</SubmitButton>
        </div>
      )}
    </ActionForm>
  );
}
