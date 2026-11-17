"use server";

import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api, setActiveOrgId } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Organisation } from "@/types/api";

export async function registerOrganisation(_: FormState, form: FormData): Promise<FormState> {
  let created: Organisation | undefined;
  const state = await attempt(async () => {
    created = await api<Organisation>("/organisations", {
      method: "POST",
      tenant: false,
      body: {
        name: required(form, "name"),
        legal_name: optional(form, "legal_name"),
        registration_number: optional(form, "registration_number"),
        email: optional(form, "email"),
        phone: optional(form, "phone"),
        first_branch_name: required(form, "first_branch_name"),
        first_branch_code: required(form, "first_branch_code").toUpperCase(),
      },
    });
  });
  if (created) {
    await setActiveOrgId(created.id);
    redirect("/organisation");
  }
  return state;
}

export async function acceptInvitation(organisationId: string): Promise<void> {
  await api(`/me/invitations/${encodeURIComponent(organisationId)}/accept`, {
    method: "POST",
    tenant: false,
  });
  await setActiveOrgId(organisationId);
  redirect("/");
}
