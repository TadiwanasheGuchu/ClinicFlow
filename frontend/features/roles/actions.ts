"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Role } from "@/types/api";

const body = (form: FormData) => ({
  name: required(form, "name"),
  description: optional(form, "description"),
  permissions: form.getAll("permissions").map(String),
});

export async function createRole(_: FormState, form: FormData): Promise<FormState> {
  let created: Role | undefined;
  const state = await attempt(async () => {
    created = await api<Role>("/roles", { method: "POST", body: body(form) });
  });
  if (created) {
    revalidatePath("/roles");
    redirect(`/roles/${created.id}`);
  }
  return state;
}

export async function updateRole(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () => api(`/roles/${encodeURIComponent(id)}`, { method: "PATCH", body: body(form) }),
    "Role saved. Changes apply to everyone holding it.",
  );
  revalidatePath(`/roles/${id}`);
  return state;
}

export async function deleteRole(id: string): Promise<void> {
  await api(`/roles/${encodeURIComponent(id)}`, { method: "DELETE" });
  revalidatePath("/roles");
  redirect("/roles");
}
