import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { MessagesTable } from "@/features/messages/messages-table";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Notification, Page } from "@/types/api";

export const metadata: Metadata = { title: "Messages" };

const FILTERS = [
  ["failed", "Failed"],
  ["pending", "Queued"],
  ["sent", "Sent"],
  ["skipped", "Not sent"],
  ["", "All"],
] as const;

export default async function MessagesPage({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string }> }) {
  const { access } = await requirePermission("appointments.read");
  const params = await searchParams;
  const status = FILTERS.some(([k]) => k === params.status) ? params.status! : "failed";
  const offset = Number(params.offset ?? 0) || 0;
  const page = await api<Page<Notification>>("/notifications", { query: { status: status || undefined, offset, limit: 50 } });
  const returnTo = `/messages?status=${status}`;

  return (
    <>
      <PageHeader title="Messages" description="Confirmations and reminders sent to patients. Failed messages can be retried once the problem is fixed." />
      <nav aria-label="Filter messages" className="mb-3 flex flex-wrap gap-1">
        {FILTERS.map(([key, label]) => (
          <Link key={key} href={`/messages?status=${key}`} aria-current={key === status ? "page" : undefined}
            className={cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", key === status ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted")}>
            {label}
          </Link>
        ))}
      </nav>
      {page.items.length === 0 ? (
        <EmptyState message={status === "failed" ? "No failed messages." : "No messages."} />
      ) : (
        <MessagesTable items={page.items} canRetry={hasPermission(access, "appointments.manage")} returnTo={returnTo} showBody />
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `/messages?status=${status}&offset=${o}`} />
    </>
  );
}
