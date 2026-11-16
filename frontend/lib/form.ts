export type FormState = {
  error?: string;
  success?: string;
  fieldErrors?: Record<string, string>;
};

export const initialFormState: FormState = {};

/** Trimmed string or null for empty optional fields. */
export const optional = (form: FormData, key: string): string | null => {
  const value = form.get(key);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

export const required = (form: FormData, key: string): string => optional(form, key) ?? "";
