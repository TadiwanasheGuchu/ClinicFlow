"use server";

import { revalidatePath } from "next/cache";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";

export async function saveProfile(membershipId: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/members/${encodeURIComponent(membershipId)}/profile`, {
        method: "PUT",
        body: {
          profession: required(form, "profession"),
          specialty: optional(form, "specialty"),
          registration_body: optional(form, "registration_body"),
          professional_number: optional(form, "professional_number"),
          licence_expiry_date: optional(form, "licence_expiry_date"),
        },
      }),
    "Professional details saved.",
  );
  revalidatePath(`/staff/${membershipId}`);
  return state;
}

export async function verifyProfile(membershipId: string, _: FormState, form: FormData): Promise<FormState> {
  const decision = required(form, "decision");
  const state = await attempt(
    () =>
      api(`/members/${encodeURIComponent(membershipId)}/profile/verify`, {
        method: "POST",
        body: { decision, note: required(form, "note") },
      }),
    decision === "verified" ? "Registration verified." : "Registration marked as rejected.",
  );
  revalidatePath(`/staff/${membershipId}`);
  return state;
}
