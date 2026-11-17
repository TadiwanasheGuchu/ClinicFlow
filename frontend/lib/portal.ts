import "server-only";

import { api, ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

const API_URL = process.env.CLINICFLOW_API_URL ?? "http://localhost:8000";

export type PortalInfo = {
  name: string;
  phone: string | null;
  email: string | null;
  branches: { id: string; name: string; address: string | null; phone: string | null; operating_hours: Record<string, { open: string; close: string }[]> }[];
  providers: { id: string; display_name: string; specialty: string | null; branch_ids: string[] }[];
  appointment_types: { id: string; name: string; duration_minutes: number; fee: string }[];
  policy: { min_notice_hours: number; max_days_ahead: number; cancel_cutoff_hours: number; auto_confirm: boolean };
};

export type PortalPatient = {
  first_name: string;
  last_name: string;
  patient_number: string;
  date_of_birth: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  preferred_channel: string;
};

export type PortalMe = { email: string; linked: boolean; patient: PortalPatient | null };

export type PortalAppointment = {
  id: string;
  reference: string;
  status: string;
  start_at: string;
  end_at: string;
  provider_id: string;
  branch_id: string;
  appointment_type_id: string;
  provider_name: string;
  branch_name: string;
  branch_address: string | null;
  appointment_type: string;
  can_change: boolean;
};

export const validSlug = (slug: string) => /^[a-z0-9-]{3,60}$/.test(slug);

/** Public practice information; null if the practice has no portal. No sign-in needed. */
export async function portalInfo(slug: string): Promise<PortalInfo | null> {
  if (!validSlug(slug)) return null;
  const response = await fetch(new URL(`/api/v1/portal/${slug}`, API_URL), { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Portal info failed: ${response.status}`);
  return response.json();
}

/** The signed-in patient's link status, or null when not signed in. */
export async function portalMe(slug: string): Promise<PortalMe | null> {
  if (!(await getAccessToken())) return null;
  try {
    return await api<PortalMe>(`/portal/${slug}/me`, { tenant: false });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Authenticated portal call (no staff organisation header). */
export const portalApi = <T,>(slug: string, path: string, options: Parameters<typeof api>[1] = {}) =>
  api<T>(`/portal/${slug}${path}`, { ...options, tenant: false });
