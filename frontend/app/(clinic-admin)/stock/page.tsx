import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { receiveStock, recordUsage } from "@/features/inventory/actions";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { hasOrgWide, hasPermission, requirePermission } from "@/lib/session";
import type { Branch, InventoryItem, Page, StockOverview, Supplier } from "@/types/api";

export const metadata: Metadata = { title: "Stock" };

const FILTERS = [["all", "All stock"], ["reorder", "To reorder"], ["expiry", "Expiring or expired"]] as const;

export default async function StockPage({ searchParams }: { searchParams: Promise<{ view?: string; branch?: string }> }) {
  const { access } = await requirePermission("inventory.read");
  const params = await searchParams;
  const view = FILTERS.some(([k]) => k === params.view) ? params.view! : "all";
  const canManage = hasPermission(access, "inventory.manage");
  const [overview, branches, items, suppliers] = await Promise.all([
    api<StockOverview>("/inventory/stock", { query: { branch_id: params.branch || undefined, include_empty: view === "reorder" || undefined } }),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
    canManage ? api<InventoryItem[]>("/inventory/items") : Promise.resolve([] as InventoryItem[]),
    canManage ? api<Supplier[]>("/inventory/suppliers") : Promise.resolve([] as Supplier[]),
  ]);
  const manageable = branches.items.filter((b) => access.grants.some((g) => g.permission === "inventory.manage" && (g.branch_id === null || g.branch_id === b.id)));
  const levels = overview.levels.filter((lv) => view === "all" || (view === "reorder" ? lv.below_reorder : lv.expired > 0 || lv.expiring_soon > 0));
  const link = (v: string, b = params.branch) => `/stock?${new URLSearchParams({ view: v, ...(b && { branch: b }) })}`;
  const chip = (on: boolean) => cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", on ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted");
  const branchSelect = (id: string) => (
    <Select id={id} name="branch_id" required className="w-44">{manageable.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
  );
  const itemSelect = (id: string) => (
    <Select id={id} name="item_id" required className="w-64"><option value="">Choose…</option>{items.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.unit})</option>)}</Select>
  );

  return (
    <>
      <PageHeader
        title="Stock"
        description={`Stock value ${nad(overview.total_value)} at cost. “Expiring” means within ${overview.expiry_window_days} days.`}
        actions={<>
          <ButtonLink variant="secondary" href="/stock/history">History</ButtonLink>
          <ButtonLink variant="secondary" href="/stock/purchase-orders">Purchase orders</ButtonLink>
        </>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <nav aria-label="Filter stock" className="flex flex-wrap gap-1">
          {FILTERS.map(([k, label]) => <Link key={k} href={link(k)} aria-current={k === view ? "page" : undefined} className={chip(k === view)}>{label}</Link>)}
        </nav>
        {branches.items.length > 1 && (
          <form className="flex items-center gap-2">
            <input type="hidden" name="view" value={view} />
            <label htmlFor="branch" className="text-sm text-text-muted">Branch</label>
            <Select id="branch" name="branch" defaultValue={params.branch ?? ""} className="w-44">
              <option value="">All branches</option>
              {branches.items.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
            <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Show</button>
          </form>
        )}
      </div>
      {levels.length === 0 ? (
        <EmptyState message={view === "all" ? "No stock recorded yet." : "Nothing here."} />
      ) : (
        <Table>
          <THead><tr><TH>Item</TH><TH>Branch</TH><TH align="right">In date</TH><TH align="right">Reorder at</TH><TH>Expiry</TH><TH align="right">Value</TH></tr></THead>
          <tbody>
            {levels.map((lv) => (
              <TR key={`${lv.item_id}-${lv.branch_id}`}>
                <TD><Link className="text-primary hover:underline" href={`/stock/items/${lv.item_id}`}>{lv.name}</Link> <span className="font-mono text-xs text-text-muted">{lv.sku}</span></TD>
                <TD className="text-text-muted">{lv.branch_name}</TD>
                <TD align="right" mono>
                  {lv.usable} <span className="font-sans text-xs text-text-muted">{lv.unit}</span>
                  {lv.below_reorder && <span className="block font-sans text-sm font-semibold text-warning-text">Reorder</span>}
                </TD>
                <TD align="right" mono className="text-text-muted">{lv.reorder_level}</TD>
                <TD>
                  {lv.expired > 0 && <span className="block text-sm font-semibold text-danger-text">{lv.expired} expired — write off</span>}
                  {lv.expiring_soon > 0 && <span className="block text-sm font-medium text-warning-text">{lv.expiring_soon} expiring by {formatDate(lv.next_expiry)}</span>}
                  {!lv.expired && !lv.expiring_soon && <span className="text-sm text-text-muted">{lv.next_expiry ? `Next ${formatDate(lv.next_expiry)}` : "—"}</span>}
                </TD>
                <TD align="right" mono>{nad(lv.value)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}

      {canManage && manageable.length > 0 && items.length > 0 && (
        <div className="mt-6 flex max-w-5xl flex-col gap-4">
          <Panel title="Record usage" description="Taken from the batch that expires first. Expired stock is never used.">
            <QuickForm action={recordUsage} submit="Record usage" reset>
              <Field id="use-branch" label="Branch">{branchSelect("use-branch")}</Field>
              <Field id="use-item" label="Item" required>{itemSelect("use-item")}</Field>
              <Field id="use-qty" label="Quantity" required><Input id="use-qty" name="quantity" type="number" min={1} required className="w-24 text-right font-mono" /></Field>
              <Field id="use-reason" label="Used for"><Input id="use-reason" name="reason" placeholder="e.g. Treatment room" className="w-56" /></Field>
            </QuickForm>
          </Panel>
          <Panel title="Receive stock" description="Deliveries without a purchase order. Medicines need a batch number and expiry date.">
            <QuickForm action={receiveStock} submit="Receive into stock" reset>
              <Field id="rc-branch" label="Branch">{branchSelect("rc-branch")}</Field>
              <Field id="rc-item" label="Item" required>{itemSelect("rc-item")}</Field>
              <Field id="rc-qty" label="Quantity" required><Input id="rc-qty" name="quantity" type="number" min={1} required className="w-24 text-right font-mono" /></Field>
              <Field id="rc-cost" label="Unit cost (N$)"><Input id="rc-cost" name="unit_cost" inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" className="w-28 text-right font-mono" /></Field>
              <Field id="rc-batch" label="Batch number"><Input id="rc-batch" name="batch_number" className="w-36 font-mono" /></Field>
              <Field id="rc-expiry" label="Expiry date"><Input id="rc-expiry" name="expiry_date" type="date" className="w-40" /></Field>
              <Field id="rc-supplier" label="Supplier"><Select id="rc-supplier" name="supplier_id" className="w-56"><option value="">—</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
              <Field id="rc-ref" label="Delivery note / invoice"><Input id="rc-ref" name="reference" className="w-40" /></Field>
            </QuickForm>
          </Panel>
        </div>
      )}
      {hasOrgWide(access, "inventory.adjust") && (
        <p className="mt-4 text-sm"><Link className="text-primary hover:underline" href="/stock/setup">Items and suppliers</Link></p>
      )}
    </>
  );
}
