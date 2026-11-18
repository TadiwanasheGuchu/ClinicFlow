import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Input } from "@/components/ui/field";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { ReasonAction } from "@/features/clinical/forms";
import { cancelPurchaseOrder, placePurchaseOrder, receivePurchaseOrder, savePurchaseOrder } from "@/features/inventory/actions";
import { PurchaseOrderForm } from "@/features/inventory/forms";
import { api, ApiError } from "@/lib/api";
import { nad } from "@/lib/billing";
import { formatDate, formatDateTime } from "@/lib/format";
import { PO_STATUS } from "@/lib/inventory";
import { requirePermission } from "@/lib/session";
import type { Branch, InventoryItem, Page, PurchaseOrder, Supplier } from "@/types/api";

export const metadata: Metadata = { title: "Purchase order" };

export default async function PurchaseOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("inventory.read");
  let po: PurchaseOrder;
  try {
    po = await api<PurchaseOrder>(`/inventory/purchase-orders/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
  const canManage = access.grants.some((g) => g.permission === "inventory.manage" && (g.branch_id === null || g.branch_id === po.branch_id));
  const draft = po.status === "draft";
  const receiving = po.status === "ordered" || po.status === "partially_received";
  const nothingReceived = po.lines.every((l) => l.quantity_received === 0);
  const [branches, suppliers, items] = draft && canManage
    ? await Promise.all([api<Page<Branch>>("/branches", { query: { limit: 200 } }), api<Supplier[]>("/inventory/suppliers"), api<InventoryItem[]>("/inventory/items")])
    : [null, [], []];

  return (
    <>
      <PageHeader
        title={po.order_number}
        description={`${po.supplier_name} · deliver to ${po.branch_name} · ${PO_STATUS[po.status]}${po.expected_on ? ` · expected ${formatDate(po.expected_on)}` : ""}`}
        back={{ href: "/stock/purchase-orders", label: "Purchase orders" }}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        {po.status === "cancelled" && <Notice tone="error">Cancelled {formatDateTime(po.cancelled_at)}: {po.cancel_reason}</Notice>}
        <Panel title="Lines">
          <Table>
            <THead><tr><TH>Item</TH><TH align="right">Ordered</TH><TH align="right">Received</TH><TH align="right">Unit cost</TH><TH align="right">Line total</TH></tr></THead>
            <tbody>
              {po.lines.map((l) => (
                <TR key={l.id}>
                  <TD>{l.item_name} <span className="font-mono text-xs text-text-muted">{l.sku}</span></TD>
                  <TD align="right" mono>{l.quantity_ordered}</TD>
                  <TD align="right" mono>{l.quantity_received}</TD>
                  <TD align="right" mono>{nad(l.unit_cost)}</TD>
                  <TD align="right" mono>{nad(l.line_total)}</TD>
                </TR>
              ))}
              <TR><TD className="font-medium">Total</TD><TD /><TD /><TD /><TD align="right" mono className="font-semibold">{nad(po.total)}</TD></TR>
            </tbody>
          </Table>
          {po.notes && <p className="mt-3 text-sm whitespace-pre-wrap text-text-muted">{po.notes}</p>}
        </Panel>

        {canManage && draft && branches && (
          <>
            <Panel title="Place order" description="Send the order to the supplier yourself (email or phone), then mark it placed. Placed orders can't be edited.">
              <QuickForm action={placePurchaseOrder.bind(null, po.id)} submit={`Mark ${po.order_number} as placed`} />
            </Panel>
            <Panel title="Edit draft">
              <PurchaseOrderForm action={savePurchaseOrder.bind(null, po.id)} branches={branches.items} suppliers={suppliers} items={items} order={po} />
            </Panel>
          </>
        )}

        {canManage && receiving && (
          <Panel title="Receive delivery" description="Enter what arrived. Each line becomes a stock batch; medicines need a batch number and expiry date.">
            <QuickForm action={receivePurchaseOrder.bind(null, po.id)} submit="Receive into stock" reset className="flex-col items-stretch">
              <Table>
                <THead><tr><TH>Item</TH><TH align="right">Outstanding</TH><TH>Received now</TH><TH>Batch number</TH><TH>Expiry date</TH></tr></THead>
                <tbody>
                  {po.lines.filter((l) => l.quantity_received < l.quantity_ordered).map((l) => (
                    <TR key={l.id}>
                      <TD>{l.item_name}</TD>
                      <TD align="right" mono>{l.quantity_ordered - l.quantity_received}</TD>
                      <TD><label className="sr-only" htmlFor={`rq-${l.id}`}>Quantity received of {l.item_name}</label><Input id={`rq-${l.id}`} name={`recv.${l.id}.quantity`} type="number" min={0} max={l.quantity_ordered - l.quantity_received} className="w-24 text-right font-mono" /></TD>
                      <TD><label className="sr-only" htmlFor={`rb-${l.id}`}>Batch number of {l.item_name}</label><Input id={`rb-${l.id}`} name={`recv.${l.id}.batch_number`} required={l.track_expiry} className="w-36 font-mono" /></TD>
                      <TD><label className="sr-only" htmlFor={`re-${l.id}`}>Expiry date of {l.item_name}</label><Input id={`re-${l.id}`} name={`recv.${l.id}.expiry_date`} type="date" required={l.track_expiry} className="w-40" /></TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
              <div className="flex items-end gap-3">
                <label className="flex flex-col gap-1 text-sm font-medium">Delivery note<Input name="reference" className="w-48" /></label>
              </div>
            </QuickForm>
          </Panel>
        )}

        {canManage && (draft || (po.status === "ordered" && nothingReceived)) && (
          <Panel title="Cancel order">
            <ReasonAction action={cancelPurchaseOrder.bind(null, po.id)} label={`Cancel ${po.order_number}`} danger />
          </Panel>
        )}
      </div>
    </>
  );
}
