"use server";

import { revalidatePath } from "next/cache";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import type { FormState } from "@/lib/form";

export async function retryMessage(id: string, returnTo: string): Promise<void> {
  await api(`/notifications/${encodeURIComponent(id)}/retry`, { method: "POST" });
  revalidatePath(returnTo);
}

export async function createLinkCode(patientId: string, _: FormState): Promise<FormState> {
  let message = "";
  const state = await attempt(async () => {
    const result = await api<{ code: string; expires_at: string }>(
      `/patients/${encodeURIComponent(patientId)}/portal-link-code`,
      { method: "POST" },
    );
    const until = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Africa/Windhoek" }).format(new Date(result.expires_at));
    message = `Link code ${result.code} — valid until ${until}. Give it to the patient after confirming who they are. It is shown only once.`;
  });
  return state.error ? state : { success: message };
}

export async function revokePortalAccess(patientId: string): Promise<void> {
  await api(`/patients/${encodeURIComponent(patientId)}/portal-account/revoke`, { method: "POST" });
  revalidatePath(`/patients/${patientId}`);
}
