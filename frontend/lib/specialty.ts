import "server-only";

import { api } from "@/lib/api";
import type { Organisation } from "@/types/api";

/** Specialty modules switched on for the current organisation. */
export async function enabledModules(): Promise<Set<string>> {
  const org = await api<Organisation>("/organisation");
  return new Set(org.settings.specialty_modules ?? []);
}
