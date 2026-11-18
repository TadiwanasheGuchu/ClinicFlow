import type { Metadata } from "next";

import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { savePurchaseOrder } from "@/features/inventory/actions";
import { PurchaseOrderForm } from "@/features/inventory/forms";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/session";
import type { Branch, InventoryItem, Page, Supplier } from "@/types/api";

export const metadata: Metadata = { title: "New purchase order" };

export default async function NewPurchaseOrder() {
  const { access } = await requirePermission("inventory.manage");
  const [branches, suppliers, items] = await Promise.all([
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
    api<Supplier[]>("/inventory/suppliers"),
    api<InventoryItem[]>("/inventory/items"),
  ]);
  const allowed = branches.items.filter((b) => access.grants.some((g) => g.permission === "inventory.manage" && (g.branch_id === null || g.branch_id === b.id)));
  return (
    <>
      <PageHeader title="New purchase order" back={{ href: "/stock/purchase-orders", label: "Purchase orders" }} />
      <div className="max-w-5xl">
        {suppliers.length === 0 || items.length === 0 ? (
          <Notice>Add items and suppliers first (Stock → Items and suppliers).</Notice>
        ) : (
          <Panel><PurchaseOrderForm action={savePurchaseOrder.bind(null, null)} branches={allowed} suppliers={suppliers} items={items} /></Panel>
        )}
      </div>
    </>
  );
}
