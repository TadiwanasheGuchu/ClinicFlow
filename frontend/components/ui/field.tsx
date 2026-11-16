import { cn } from "@/lib/cn";
import type { ComponentProps, ReactNode } from "react";

const control =
  "block w-full rounded-sm border border-border bg-surface px-2.5 text-base text-text " +
  "placeholder:text-text-muted disabled:bg-surface-muted disabled:text-text-muted " +
  "aria-[invalid=true]:border-danger";

type FieldProps = {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
};

/** Label above the control, always visible; hint and error linked via aria-describedby. */
export function Field({ id, label, hint, error, required, children, className }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
        {required && <span className="text-danger-text"> *</span>}
      </label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className="text-xs text-text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs text-danger-text">
          {error}
        </p>
      )}
    </div>
  );
}

export const describedBy = (id: string, error?: string, hint?: string) =>
  error ? `${id}-error` : hint ? `${id}-hint` : undefined;

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(control, "min-h-20 py-2", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(control, "h-9 pr-8", className)} {...props} />;
}

export function Checkbox({
  label,
  description,
  className,
  ...props
}: ComponentProps<"input"> & { label: string; description?: string }) {
  return (
    <label className={cn("flex items-start gap-2 text-base", className)}>
      <input type="checkbox" className="mt-0.5 size-4 accent-primary" {...props} />
      <span>
        <span className="text-text">{label}</span>
        {description && <span className="block text-xs text-text-muted">{description}</span>}
      </span>
    </label>
  );
}
