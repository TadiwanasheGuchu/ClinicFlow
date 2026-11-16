import { cn } from "@/lib/cn";
import { ChevronLeft, ChevronRight, CircleAlert, CircleCheck, Info } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {back && (
          <Link
            href={back.href}
            className="mb-1 inline-flex items-center gap-0.5 text-sm text-primary hover:underline"
          >
            <ChevronLeft size={16} strokeWidth={1.5} aria-hidden />
            {back.label}
          </Link>
        )}
        <h1 className="text-xl text-text">{title}</h1>
        {description && <p className="mt-1 text-base text-text-muted">{description}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  description,
  children,
  className,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded border border-border bg-surface", className)}>
      {title && (
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-md text-text">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-text-muted">{description}</p>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const noticeTone = {
  error: { cls: "border-danger bg-danger-subtle text-danger-text", icon: CircleAlert },
  success: { cls: "border-success bg-success-subtle text-success-text", icon: CircleCheck },
  info: { cls: "border-secondary bg-surface text-secondary-text", icon: Info },
};

export function Notice({
  tone = "info",
  children,
}: {
  tone?: keyof typeof noticeTone;
  children: ReactNode;
}) {
  const t = noticeTone[tone];
  const Icon = t.icon;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex items-start gap-2 rounded border px-3 py-2 text-base", t.cls)}
    >
      <Icon size={16} strokeWidth={1.5} className="mt-0.5 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-border bg-surface px-4 py-8 text-center">
      <p className="text-base text-text-muted">{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  href,
}: {
  total: number;
  limit: number;
  offset: number;
  href: (offset: number) => string;
}) {
  if (total <= limit) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  const link = "inline-flex h-8 items-center gap-1 rounded-sm border border-border bg-surface px-2.5 text-sm hover:bg-surface-muted";
  return (
    <nav aria-label="Pagination" className="mt-3 flex items-center justify-between text-sm text-text-muted">
      <span className="tabular">
        {from}–{to} of {total}
      </span>
      <span className="flex gap-2">
        {offset > 0 && (
          <Link className={link} href={href(Math.max(0, offset - limit))}>
            <ChevronLeft size={16} strokeWidth={1.5} aria-hidden /> Previous
          </Link>
        )}
        {to < total && (
          <Link className={link} href={href(offset + limit)}>
            Next <ChevronRight size={16} strokeWidth={1.5} aria-hidden />
          </Link>
        )}
      </span>
    </nav>
  );
}

/** Definition list for read-only detail. */
export function Details({ items }: { items: { label: string; value: ReactNode; mono?: boolean }[] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="text-xs text-text-muted">{item.label}</dt>
          <dd className={cn("text-base text-text", item.mono && "font-mono text-sm")}>
            {item.value ?? "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}
