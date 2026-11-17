import "server-only";

import { notFound } from "next/navigation";

import { api, ApiError } from "@/lib/api";

/** Load a clinical resource; 403/404 render as not found (never reveal existence). */
export async function loadClinical<T>(path: string): Promise<T> {
  try {
    return await api<T>(path);
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
}
