"use server";

import { revalidatePath } from "next/cache";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, required } from "@/lib/form";

export async function setTenantStatus(
  id: string,
  status: "active" | "suspended",
  _: FormState,
  form: FormData,
): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/platform/organisations/${encodeURIComponent(id)}`, {
        method: "PATCH",
        tenant: false,
        body: { status, reason: required(form, "reason") },
      }),
    status === "suspended" ? "Organisation suspended." : "Organisation is active.",
  );
  revalidatePath("/platform");
  return state;
}
