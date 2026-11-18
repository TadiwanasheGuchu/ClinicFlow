import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { adjustBatch, transferBatch } from "@/features/inventory/actions";
import { api, ApiError } from "@/lib/api";
import { nad } from "@/lib/billing";
import { formatDate, formatDateTime } from "@/lib/format";
import { MOVEMENT_LABEL, signed } from "@/lib/inventory";
import { requirePermission } from "@/lib/session";
import type { Branch, ItemStock, Page, StockMovement } from "@/types/api";

export const metadata: Metadata = { title: "Stock item" };

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("inventory.read");
  let stock: ItemStock;
  try {
    stock = await api<ItemStock>(`/inventory/items/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && [404, 422].includes(error.status)) notFound();
    throw error;
  }
  const [history, branches] = await Promise.all([
    api<Page<StockMovement>>("/inventory/movements", { query: { item_id: id, limit: 50 } }),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
  ]);
  const { item, batches } = stock;
  const branchName = Object.fromEntries(branches.items.map((b) => [b.id, b.name]));
  const can = (p: string, branch: string) => access.grants.some((g) => g.permission === p && (g.branch_id === null || g.branch_id === branch));

  return (
    <>
      <PageHeader title={item.name} description={`${item.sku} · counted in ${item.unit}s · reorder at ${item.reorder_level}${item.track_expiry ? " · batch and expiry tracked" : ""}`} back={{ href: "/stock", label: "Stock" }} />
      <div className="flex max-w-5xl flex-col gap-4">
        <Panel title="Batches in stock">
          {batches.length === 0 ? <p className="text-text-muted">None in stock.</p> : (
            <div className="flex flex-col gap-3">
              {batches.map((b) => (
                <article key={b.id} className="rounded border border-border p-3">
                  <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                    <span>
                      <span className="font-medium">{branchName[b.branch_id]}</span>
                      <span className="ml-2 font-mono text-sm">{b.batch_number ?? "No batch number"}</span>
                      {b.expiry_date && (
                        <span className={b.expired ? "ml-2 text-sm font-semibold text-danger-text" : "ml-2 text-sm text-text-muted"}>
                          {b.expired ? "Expired" : "Expires"} {formatDate(b.expiry_date)}
                        </span>
                      )}
                    </span>
                    <span className="font-mono">{b.quantity_remaining} <span className="font-sans text-sm text-text-muted">of {b.quantity_received} · {nad(b.unit_cost)} each</span></span>
                  </header>
                  <p className="mb-2 text-sm text-text-muted">Received {formatDate(b.received_at)}{b.supplier_name && ` from ${b.supplier_name}`}</p>
                  <div className="flex flex-col gap-3">
                    {can("inventory.adjust", b.branch_id) && (
                      <QuickForm action={adjustBatch.bind(null, item.id, b.id)} submit="Adjust" variant="secondary">
                        <Field id={`k-${b.id}`} label="Adjustment">
                          <Select id={`k-${b.id}`} name="kind" defaultValue={b.expired ? "write_off" : "count"} className="w-44">
                            <option value="count">Stock count (enter counted)</option>
                            <option value="write_off">Write off (enter removed)</option>
                          </Select>
                        </Field>
                        <Field id={`q-${b.id}`} label="Quantity"><Input id={`q-${b.id}`} name="quantity" type="number" min={0} required className="w-24 text-right font-mono" /></Field>
                        <Field id={`r-${b.id}`} label="Reason" required><Input id={`r-${b.id}`} name="reason" required minLength={3} placeholder={b.expired ? "Expired" : "Monthly count"} className="w-56" /></Field>
                      </QuickForm>
                    )}
                    {!b.expired && can("inventory.manage", b.branch_id) && branches.items.length > 1 && (
                      <QuickForm action={transferBatch.bind(null, item.id, b.id)} submit="Transfer" variant="secondary">
                        <Field id={`to-${b.id}`} label="To branch">
                          <Select id={`to-${b.id}`} name="to_branch_id" required className="w-44">
                            {branches.items.filter((x) => x.id !== b.branch_id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                          </Select>
                        </Field>
                        <Field id={`tq-${b.id}`} label="Quantity"><Input id={`tq-${b.id}`} name="quantity" type="number" min={1} max={b.quantity_remaining} required className="w-24 text-right font-mono" /></Field>
                      </QuickForm>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="History">
          {history.items.length === 0 ? <EmptyState message="No stock movements yet." /> : (
            <Table>
              <THead><tr><TH>When</TH><TH>Branch</TH><TH>Movement</TH><TH align="right">Quantity</TH><TH>Batch</TH><TH>Reason or reference</TH><TH>By</TH></tr></THead>
              <tbody>
                {history.items.map((m) => (
                  <TR key={m.id}>
                    <TD className="tabular">{formatDateTime(m.occurred_at)}</TD>
                    <TD className="text-text-muted">{m.branch_name}</TD>
                    <TD>{MOVEMENT_LABEL[m.movement_type]}</TD>
                    <TD align="right" mono>{signed(m.quantity)}</TD>
                    <TD mono className="text-text-muted">{m.batch_number ?? "—"}</TD>
                    <TD className="text-text-muted">{[m.reason, m.reference].filter(Boolean).join(" · ") || "—"}</TD>
                    <TD className="text-text-muted">{m.performed_by_name}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
