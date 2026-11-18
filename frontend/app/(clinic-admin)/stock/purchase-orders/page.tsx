import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { PO_STATUS } from "@/lib/inventory";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Page, PurchaseOrder } from "@/types/api";

export const metadata: Metadata = { title: "Purchase orders" };

const GROUPS = [["open", "Awaiting delivery"], ["draft", "Drafts"], ["closed", "Closed"], ["all", "All"]] as const;

export default async function PurchaseOrders({ searchParams }: { searchParams: Promise<{ group?: string; offset?: string }> }) {
  const { access } = await requirePermission("inventory.read");
  const params = await searchParams;
  const group = GROUPS.some(([k]) => k === params.group) ? params.group! : "open";
  const offset = Number(params.offset ?? 0) || 0;
  const page = await api<Page<PurchaseOrder>>("/inventory/purchase-orders", { query: { group, offset, limit: 50 } });
  const chip = (on: boolean) => cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", on ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted");
  return (
    <>
      <PageHeader title="Purchase orders" back={{ href: "/stock", label: "Stock" }} actions={hasPermission(access, "inventory.manage") && <ButtonLink href="/stock/purchase-orders/new">New purchase order</ButtonLink>} />
      <nav aria-label="Filter purchase orders" className="mb-3 flex flex-wrap gap-1">
        {GROUPS.map(([k, label]) => <Link key={k} href={`/stock/purchase-orders?group=${k}`} aria-current={k === group ? "page" : undefined} className={chip(k === group)}>{label}</Link>)}
      </nav>
      {page.items.length === 0 ? <EmptyState message="No purchase orders here." /> : (
        <Table>
          <THead><tr><TH>Order</TH><TH>Supplier</TH><TH>Branch</TH><TH>Expected</TH><TH>Status</TH><TH align="right">Total</TH></tr></THead>
          <tbody>
            {page.items.map((p) => (
              <TR key={p.id}>
                <TD mono><Link className="text-primary hover:underline" href={`/stock/purchase-orders/${p.id}`}>{p.order_number}</Link></TD>
                <TD>{p.supplier_name}</TD>
                <TD className="text-text-muted">{p.branch_name}</TD>
                <TD className="tabular">{formatDate(p.expected_on)}</TD>
                <TD>{PO_STATUS[p.status]}</TD>
                <TD align="right" mono>{nad(p.total)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `/stock/purchase-orders?group=${group}&offset=${o}`} />
    </>
  );
}
