import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { InvoiceStatusText } from "@/features/billing/status";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { InvoiceSummary, Page } from "@/types/api";

export const metadata: Metadata = { title: "Invoices" };

const FILTERS = [["outstanding", "Outstanding"], ["draft", "Drafts"], ["paid", "Paid"], ["credited", "Credited"], ["", "All"]] as const;

export default async function InvoicesPage({ searchParams }: { searchParams: Promise<{ status?: string; q?: string; offset?: string }> }) {
  const { access } = await requirePermission("billing.read");
  const params = await searchParams;
  const status = FILTERS.some(([k]) => k === params.status) ? params.status! : "outstanding";
  const q = params.q ?? "";
  const offset = Number(params.offset ?? 0) || 0;
  const page = await api<Page<InvoiceSummary>>("/invoices", { query: { status: status || undefined, q: q || undefined, offset, limit: 50 } });
  const link = (s: string) => `/invoices?${new URLSearchParams({ status: s, ...(q && { q }) })}`;

  return (
    <>
      <PageHeader title="Invoices" actions={hasPermission(access, "billing.manage") && <ButtonLink href="/invoices/new">New invoice</ButtonLink>} />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <nav aria-label="Filter invoices" className="flex flex-wrap gap-1">
          {FILTERS.map(([key, label]) => (
            <Link key={key} href={link(key)} aria-current={key === status ? "page" : undefined}
              className={cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", key === status ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted")}>{label}</Link>
          ))}
        </nav>
        <form className="flex gap-2" role="search">
          <input type="hidden" name="status" value={status} />
          <label className="sr-only" htmlFor="q">Search invoices</label>
          <Input id="q" name="q" defaultValue={q} placeholder="Invoice number, surname or patient number" className="w-72" />
          <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Search</button>
        </form>
      </div>
      {page.items.length === 0 ? (
        <EmptyState message="No invoices match." />
      ) : (
        <Table>
          <THead><tr><TH>Invoice</TH><TH>Patient</TH><TH>Issued</TH><TH>Due</TH><TH align="right">Total</TH><TH align="right">Balance</TH><TH>Status</TH></tr></THead>
          <tbody>
            {page.items.map((i) => (
              <TR key={i.id}>
                <TD mono><Link className="text-primary hover:underline" href={`/invoices/${i.id}`}>{i.invoice_number ?? "Draft"}</Link></TD>
                <TD>{i.patient_name} <span className="font-mono text-sm text-text-muted">{i.patient_number}</span></TD>
                <TD className="tabular">{formatDate(i.issued_at)}</TD>
                <TD className="tabular">{formatDate(i.due_at)}</TD>
                <TD align="right" mono>{nad(i.total)}</TD>
                <TD align="right" mono>{nad(i.amount_due)}</TD>
                <TD><InvoiceStatusText status={i.status} /></TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `${link(status)}&offset=${o}`} />
    </>
  );
}
