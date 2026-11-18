import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { MOVEMENT_LABEL, signed } from "@/lib/inventory";
import { requirePermission } from "@/lib/session";
import type { MovementType, Page, StockMovement } from "@/types/api";

export const metadata: Metadata = { title: "Stock history" };

export default async function StockHistory({ searchParams }: { searchParams: Promise<{ type?: string; offset?: string }> }) {
  await requirePermission("inventory.read");
  const params = await searchParams;
  const type = params.type && params.type in MOVEMENT_LABEL ? (params.type as MovementType) : undefined;
  const offset = Number(params.offset ?? 0) || 0;
  const page = await api<Page<StockMovement>>("/inventory/movements", { query: { movement_type: type, offset, limit: 50 } });
  const link = (t?: string) => `/stock/history${t ? `?type=${t}` : "?"}`;
  const chip = (on: boolean) => cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", on ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted");
  return (
    <>
      <PageHeader title="Stock history" description="Every receipt, use, count, write-off and transfer. Entries can't be changed." back={{ href: "/stock", label: "Stock" }} />
      <nav aria-label="Filter movements" className="mb-3 flex flex-wrap gap-1">
        <Link href={link()} aria-current={!type ? "page" : undefined} className={chip(!type)}>All</Link>
        {Object.entries(MOVEMENT_LABEL).map(([k, label]) => <Link key={k} href={link(k)} aria-current={k === type ? "page" : undefined} className={chip(k === type)}>{label}</Link>)}
      </nav>
      {page.items.length === 0 ? <EmptyState message="No movements." /> : (
        <Table>
          <THead><tr><TH>When</TH><TH>Item</TH><TH>Branch</TH><TH>Movement</TH><TH align="right">Quantity</TH><TH>Reason or reference</TH><TH>By</TH></tr></THead>
          <tbody>
            {page.items.map((m) => (
              <TR key={m.id}>
                <TD className="tabular">{formatDateTime(m.occurred_at)}</TD>
                <TD><Link className="text-primary hover:underline" href={`/stock/items/${m.item_id}`}>{m.item_name}</Link></TD>
                <TD className="text-text-muted">{m.branch_name}</TD>
                <TD>{MOVEMENT_LABEL[m.movement_type]}</TD>
                <TD align="right" mono>{signed(m.quantity)}</TD>
                <TD className="text-text-muted">{[m.reason, m.reference].filter(Boolean).join(" · ") || "—"}</TD>
                <TD className="text-text-muted">{m.performed_by_name}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `${link(type)}&offset=${o}`} />
    </>
  );
}
