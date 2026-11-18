import type { Metadata } from "next";

import { Checkbox, Field, Input } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { saveItem, saveSupplier } from "@/features/inventory/actions";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/session";
import type { InventoryItem, Supplier } from "@/types/api";

export const metadata: Metadata = { title: "Items and suppliers" };

function ItemFields({ item }: { item?: InventoryItem }) {
  const id = (k: string) => `${item?.id ?? "new"}-${k}`;
  return (
    <>
      <Field id={id("sku")} label="Code" required><Input id={id("sku")} name="sku" required defaultValue={item?.sku} className="w-28 font-mono uppercase" /></Field>
      <Field id={id("name")} label="Item" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required minLength={2} defaultValue={item?.name} /></Field>
      <Field id={id("category")} label="Category"><Input id={id("category")} name="category" defaultValue={item?.category ?? ""} className="w-36" placeholder="Medicines" /></Field>
      <Field id={id("unit")} label="Counted in" required><Input id={id("unit")} name="unit" required defaultValue={item?.unit} className="w-24" placeholder="tablet" /></Field>
      <Field id={id("reorder")} label="Reorder at"><Input id={id("reorder")} name="reorder_level" type="number" min={0} defaultValue={item?.reorder_level ?? 0} className="w-24 text-right font-mono" /></Field>
      <Checkbox name="track_expiry" defaultChecked={item?.track_expiry} label="Batch and expiry" className="pb-2" />
      {item && <Checkbox name="is_active" defaultChecked={item.is_active} label="Stocked" className="pb-2" />}
    </>
  );
}

function SupplierFields({ supplier }: { supplier?: Supplier }) {
  const id = (k: string) => `${supplier?.id ?? "newsup"}-${k}`;
  return (
    <>
      <Field id={id("name")} label="Supplier" required className="min-w-56 flex-1"><Input id={id("name")} name="name" required minLength={2} defaultValue={supplier?.name} /></Field>
      <Field id={id("contact")} label="Contact person"><Input id={id("contact")} name="contact_person" defaultValue={supplier?.contact_person ?? ""} className="w-44" /></Field>
      <Field id={id("phone")} label="Phone"><Input id={id("phone")} name="phone" type="tel" defaultValue={supplier?.phone ?? ""} className="w-40" /></Field>
      <Field id={id("email")} label="Email"><Input id={id("email")} name="email" type="email" defaultValue={supplier?.email ?? ""} className="w-56" /></Field>
      {supplier && <Checkbox name="is_active" defaultChecked={supplier.is_active} label="In use" className="pb-2" />}
    </>
  );
}

export default async function StockSetup() {
  await requirePermission("inventory.adjust");
  const [items, suppliers] = await Promise.all([
    api<InventoryItem[]>("/inventory/items", { query: { include_inactive: true } }),
    api<Supplier[]>("/inventory/suppliers", { query: { include_inactive: true } }),
  ]);
  return (
    <>
      <PageHeader title="Items and suppliers" description="Tick “Batch and expiry” for medicines and anything perishable." back={{ href: "/stock", label: "Stock" }} />
      <div className="flex max-w-5xl flex-col gap-6">
        <section className="flex flex-col gap-3" aria-labelledby="items-heading">
          <h2 id="items-heading" className="text-md font-medium">Items</h2>
          {items.map((i) => <Panel key={i.id}><QuickForm action={saveItem.bind(null, i.id)} submit="Save" variant="secondary"><ItemFields item={i} /></QuickForm></Panel>)}
          <Panel title="Add item"><QuickForm action={saveItem.bind(null, null)} submit="Add item" reset><ItemFields /></QuickForm></Panel>
        </section>
        <section className="flex flex-col gap-3" aria-labelledby="suppliers-heading">
          <h2 id="suppliers-heading" className="text-md font-medium">Suppliers</h2>
          {suppliers.map((s) => <Panel key={s.id}><QuickForm action={saveSupplier.bind(null, s.id)} submit="Save" variant="secondary"><SupplierFields supplier={s} /></QuickForm></Panel>)}
          <Panel title="Add supplier"><QuickForm action={saveSupplier.bind(null, null)} submit="Add supplier" reset><SupplierFields /></QuickForm></Panel>
        </section>
      </div>
    </>
  );
}
