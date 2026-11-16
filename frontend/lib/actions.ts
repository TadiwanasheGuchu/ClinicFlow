import "server-only";

import { ApiError } from "@/lib/api";
import type { FormState } from "@/lib/form";

/** Run an API mutation in a server action and turn API errors into form state.
 *  Anything that is not an ApiError (including Next.js redirects) is re-thrown. */
export async function attempt(fn: () => Promise<unknown>, success?: string): Promise<FormState> {
  try {
    await fn();
    return success ? { success } : {};
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message, fieldErrors: error.fieldErrors };
    }
    throw error;
  }
}
