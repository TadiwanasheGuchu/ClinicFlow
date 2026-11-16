"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { attempt } from "@/lib/actions";
import { api } from "@/lib/api";
import { type FormState, optional, required } from "@/lib/form";
import type { Branch, TimeInterval, Weekday } from "@/types/api";

const WEEKDAYS: { key: Weekday; label: string }[] = [
  { key: "mon", label: "Monday" },
  { key: "tue", label: "Tuesday" },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" },
  { key: "sat", label: "Saturday" },
  { key: "sun", label: "Sunday" },
];

function readHours(form: FormData): Partial<Record<Weekday, TimeInterval[]>> {
  const hours: Partial<Record<Weekday, TimeInterval[]>> = {};
  for (const { key } of WEEKDAYS) {
    if (form.get(`hours.${key}.open_day`) !== "on") continue;
    hours[key] = [{ open: required(form, `hours.${key}.open`), close: required(form, `hours.${key}.close`) }];
  }
  return hours;
}

const contact = (form: FormData) => ({
  address: optional(form, "address"),
  phone: optional(form, "phone"),
  email: optional(form, "email"),
});

export async function createBranch(_: FormState, form: FormData): Promise<FormState> {
  let created: Branch | undefined;
  const state = await attempt(async () => {
    created = await api<Branch>("/branches", {
      method: "POST",
      body: {
        name: required(form, "name"),
        branch_code: required(form, "branch_code").toUpperCase(),
        operating_hours: readHours(form),
        ...contact(form),
      },
    });
  });
  if (created) {
    revalidatePath("/branches");
    redirect(`/branches/${created.id}`);
  }
  return state;
}

export async function updateBranch(id: string, _: FormState, form: FormData): Promise<FormState> {
  const state = await attempt(
    () =>
      api(`/branches/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { name: required(form, "name"), operating_hours: readHours(form), ...contact(form) },
      }),
    "Branch saved.",
  );
  revalidatePath(`/branches/${id}`);
  return state;
}

export async function setBranchActive(id: string, active: boolean): Promise<void> {
  await api(`/branches/${encodeURIComponent(id)}`, { method: "PATCH", body: { is_active: active } });
  revalidatePath(`/branches/${id}`);
  revalidatePath("/branches");
}
