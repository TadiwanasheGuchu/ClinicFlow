"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Member } from "@/types/api";

/** Assignments are posted as assignment.<n>.role / assignment.<n>.branch. */
function readAssignments(form: FormData) {
  const indexes = new Set<string>();
  for (const key of form.keys()) {
    const match = /^assignment\.(\d+)\.role$/.exec(key);
    if (match) indexes.add(match[1]!);
  }
  return [...indexes]
    .map((i) => ({ role_id: required(form, `assignment.${i}.role`), branch_id: optional(form, `assignment.${i}.branch`) }))
    .filter((a) => a.role_id);
}

export async function inviteMember(_: FormState, form: FormData): Promise<FormState> {
  let created: Member | undefined;
  const state = await attempt(async () => {
    created = await api<Member>("/members", {
      method: "POST",
      body: {
        email: required(form, "email"),
        full_name: required(form, "full_name"),
        roles: readAssignments(form),
      },
    });
  });
  if (created) {
    revalidatePath("/staff");
    redirect(`/staff/${created.id}?invited=1`);
  }
  return state;
}

export async function updateMemberRoles(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/members/${encodeURIComponent(id)}/roles`, { method: "PUT", body: { roles: readAssignments(form) } }),
    "Roles updated. Changes apply to their next request.",
  );
  revalidatePath(`/staff/${id}`);
  return state;
}

export async function changeMemberStatus(
  id: string,
  action: "suspend" | "reactivate",
  _: FormState,
  form: FormData,
): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/members/${encodeURIComponent(id)}/${action}`, {
        method: "POST",
        body: { reason: required(form, "reason") },
      }),
    action === "suspend" ? "Access suspended." : "Access restored.",
  );
  revalidatePath(`/staff/${id}`);
  revalidatePath("/staff");
  return state;
}
