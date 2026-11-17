import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { CLAIM_STATUS, nad } from "@/lib/billing";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { Claim, Page } from "@/types/api";

export const metadata: Metadata = { title: "Claims" };

const FILTERS: [string, string, string[]][] = [
  ["open", "Needs action", ["draft", "ready", "rejected", "resubmission_required"]],
  ["waiting", "With fund", ["submitted", "processing", "accepted", "partially_paid"]],
  ["closed", "Closed", ["paid", "cancelled"]],
];

export default async function ClaimsPage({ searchParams }: { searchParams: Promise<{ view?: string; offset?: string }> }) {
  await requirePermission("billing.read");
  const params = await searchParams;
  const view = FILTERS.find(([k]) => k === params.view) ?? FILTERS[0]!;
  const offset = Number(params.offset ?? 0) || 0;
  const query = new URLSearchParams({ offset: String(offset), limit: "50" });
  for (const s of view[2]) query.append("status", s);
  const page = await api<Page<Claim>>(`/claims?${query}`);

  return (
    <>
      <PageHeader title="Medical aid claims" description="Prepared and tracked here; submitted to funds by email, fund portal or paper." />
      <nav aria-label="Filter claims" className="mb-3 flex flex-wrap gap-1">
        {FILTERS.map(([key, label]) => (
          <Link key={key} href={`/claims?view=${key}`} aria-current={key === view[0] ? "page" : undefined}
            className={cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", key === view[0] ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted")}>{label}</Link>
        ))}
      </nav>
      {page.items.length === 0 ? <EmptyState message="No claims here." /> : (
        <Table>
          <THead><tr><TH>Claim</TH><TH>Patient</TH><TH>Fund</TH><TH>Invoice</TH><TH>Prepared</TH><TH align="right">Claimed</TH><TH align="right">Paid</TH><TH>Status</TH></tr></THead>
          <tbody>
            {page.items.map((c) => (
              <TR key={c.id}>
                <TD mono><Link className="text-primary hover:underline" href={`/claims/${c.id}`}>{c.claim_number}</Link></TD>
                <TD>{c.patient_name}</TD>
                <TD>{c.fund_name}</TD>
                <TD mono>{c.invoice_number}</TD>
                <TD className="tabular">{formatDate(c.created_at)}</TD>
                <TD align="right" mono>{nad(c.claimed_amount)}</TD>
                <TD align="right" mono>{nad(c.paid_amount)}</TD>
                <TD className={c.status === "rejected" || c.status === "resubmission_required" ? "font-medium text-danger-text" : undefined}>{CLAIM_STATUS[c.status]}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `/claims?view=${view[0]}&offset=${o}`} />
    </>
  );
}
