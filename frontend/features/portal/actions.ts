"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { type FormState, optional, required } from "@/lib/form";
import { portalApi, validSlug } from "@/lib/portal";
import type { Slot } from "@/types/api";

function slugOrThrow(slug: string): string {
  if (!validSlug(slug)) throw new Error("Invalid practice address.");
  return slug;
}

export async function loadPortalSlots(
  slug: string,
  p: { providerId: string; branchId: string; typeId: string; date: string },
): Promise<Slot[]> {
  return portalApi<Slot[]>(slugOrThrow(slug), "/slots", {
    query: { provider_id: p.providerId, branch_id: p.branchId, appointment_type_id: p.typeId, date: p.date },
  });
}

export async function registerSelf(slug: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() =>
    portalApi(slugOrThrow(slug), "/register", {
      method: "POST",
      body: {
        first_name: required(form, "first_name"),
        last_name: required(form, "last_name"),
        date_of_birth: required(form, "date_of_birth"),
        phone: required(form, "phone"),
        preferred_channel: optional(form, "preferred_channel") ?? "sms",
      },
    }),
  );
  if (!state.error) {
    revalidatePath(`/book/${slug}`);
    redirect(`/book/${slug}`);
  }
  return state;
}

export async function linkAccount(slug: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(() =>
    portalApi(slugOrThrow(slug), "/link", {
      method: "POST",
      body: { code: required(form, "code"), date_of_birth: required(form, "date_of_birth") },
    }),
  );
  if (!state.error) {
    revalidatePath(`/book/${slug}`);
    redirect(`/book/${slug}`);
  }
  return state;
}

export async function bookOnline(slug: string, _: FormState, form: FormData): Promise<FormState> {
  if (!optional(form, "slot")) return { error: "Choose a time." };
  let id: string | undefined;
  const state = await attempt(async () => {
    const created = await portalApi<{ id: string }>(slugOrThrow(slug), "/appointments", {
      method: "POST",
      body: {
        provider_id: required(form, "provider_id"),
        branch_id: required(form, "branch_id"),
        appointment_type_id: required(form, "appointment_type_id"),
        start_at: required(form, "slot"),
      },
    });
    id = created.id;
  });
  if (id) redirect(`/book/${slug}/appointments/${id}?booked=1`);
  return state;
}

export async function rescheduleOnline(slug: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  if (!optional(form, "slot")) return { error: "Choose a new time." };
  const state = await attempt(
    () =>
      portalApi(slugOrThrow(slug), `/appointments/${encodeURIComponent(id)}/reschedule`, {
        method: "POST",
        body: { start_at: required(form, "slot") },
      }),
    "Your appointment has been moved.",
  );
  revalidatePath(`/book/${slug}/appointments/${id}`);
  return state;
}

export async function cancelOnline(slug: string, id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      portalApi(slugOrThrow(slug), `/appointments/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
        body: { reason: optional(form, "reason") },
      }),
    "Your appointment has been cancelled.",
  );
  revalidatePath(`/book/${slug}/appointments/${id}`);
  return state;
}

export async function updateContact(slug: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      portalApi(slugOrThrow(slug), "/me", {
        method: "PATCH",
        body: {
          phone: optional(form, "phone"),
          email: optional(form, "email"),
          address: optional(form, "address"),
          preferred_channel: required(form, "preferred_channel"),
        },
      }),
    "Your details have been saved.",
  );
  revalidatePath(`/book/${slug}/profile`);
  return state;
}
