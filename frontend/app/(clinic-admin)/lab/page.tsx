import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { LabStatus } from "@/features/lab/status";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { LAB_GROUPS } from "@/lib/lab";
import { requirePermission } from "@/lib/session";
import type { LabOrderSummary, Page } from "@/types/api";

export const metadata: Metadata = { title: "Laboratory" };

const DESCRIPTIONS: Record<string, string> = {
  outstanding: "Requested tests still waiting for results. Urgent first, then oldest.",
  to_review: "Results are in and need a clinician to review them.",
  reviewed: "Results a clinician has reviewed.",
  cancelled: "Orders cancelled before results.",
  all: "Every laboratory order you can see.",
};

const daysSince = (iso: string) => Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);

export default async function LabPage({ searchParams }: { searchParams: Promise<{ group?: string; mine?: string; offset?: string }> }) {
  await requirePermission("lab.read");
  const params = await searchParams;
  const group = LAB_GROUPS.some(([k]) => k === params.group) ? params.group! : "outstanding";
  const mine = params.mine === "1";
  const offset = Number(params.offset ?? 0) || 0;
  const page = await api<Page<LabOrderSummary>>("/lab-orders", { query: { group, mine: mine || undefined, offset, limit: 50 } });
  const link = (g: string, m = mine) => `/lab?${new URLSearchParams({ group: g, ...(m && { mine: "1" }) })}`;
  const chip = (active: boolean) =>
    cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", active ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted");

  return (
    <>
      <PageHeader title="Laboratory" description={DESCRIPTIONS[group]} />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <nav aria-label="Filter laboratory orders" className="flex flex-wrap gap-1">
          {LAB_GROUPS.map(([key, label]) => (
            <Link key={key} href={link(key)} aria-current={key === group ? "page" : undefined} className={chip(key === group)}>{label}</Link>
          ))}
        </nav>
        <nav aria-label="Requested by" className="flex gap-1">
          <Link href={link(group, false)} aria-current={!mine ? "page" : undefined} className={chip(!mine)}>Everyone’s</Link>
          <Link href={link(group, true)} aria-current={mine ? "page" : undefined} className={chip(mine)}>Requested by me</Link>
        </nav>
      </div>
      {page.items.length === 0 ? (
        <EmptyState message={group === "to_review" ? "Nothing waiting for review." : "No laboratory orders here."} />
      ) : (
        <Table>
          <THead>
            <tr><TH>Order</TH><TH>Patient</TH><TH>Tests</TH><TH>Requested</TH><TH>Laboratory</TH><TH>Status</TH><TH>Flags</TH></tr>
          </THead>
          <tbody>
            {page.items.map((o) => (
              <TR key={o.id}>
                <TD mono className="whitespace-nowrap">
                  <Link className="text-primary hover:underline" href={`/lab/${o.id}`}>{o.order_number}</Link>
                  {o.urgency === "urgent" && <span className="ml-2 font-sans text-sm font-semibold text-danger-text">Urgent</span>}
                </TD>
                <TD>{o.patient_name} <span className="font-mono text-sm text-text-muted">{o.patient_number}</span></TD>
                <TD className="max-w-72 truncate" title={o.tests.join(", ")}>{o.tests.join(", ")}</TD>
                <TD className="tabular">
                  {formatDateTime(o.requested_at)}
                  <span className="block text-sm text-text-muted">
                    {o.requested_by_name}
                    {group === "outstanding" && daysSince(o.requested_at) > 0 && ` · ${daysSince(o.requested_at)} d waiting`}
                  </span>
                </TD>
                <TD>{o.laboratory_name ?? <span className="text-text-muted">—</span>}</TD>
                <TD><LabStatus status={o.status} /></TD>
                <TD>{o.abnormal_results > 0 ? <span className="font-semibold text-warning-text">{o.abnormal_results} flagged</span> : <span className="text-text-muted">—</span>}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `${link(group)}&offset=${o}`} />
    </>
  );
}
