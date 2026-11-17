import type { Metadata } from "next";

import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { saveService } from "@/features/billing/actions";
import { ServiceForm } from "@/features/billing/forms";
import { api } from "@/lib/api";
import { nad, TAX_CATEGORY } from "@/lib/billing";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Service } from "@/types/api";

export const metadata: Metadata = { title: "Services and prices" };

export default async function ServicesPage() {
  const { access } = await requirePermission("billing.read");
  const services = await api<Service[]>("/services", { query: { include_inactive: true } });
  const canEdit = hasOrgWide(access, "billing.adjust");
  return (
    <>
      <PageHeader title="Services and prices" description="Billable services. Tariff codes are the medical aid codes your practice uses." />
      <div className="flex max-w-5xl flex-col gap-3">
        {canEdit ? (
          <>
            {services.map((s) => <Panel key={s.id}><ServiceForm action={saveService.bind(null, s.id)} item={s} /></Panel>)}
            <Panel title="Add service"><ServiceForm action={saveService.bind(null, null)} /></Panel>
          </>
        ) : services.length === 0 ? <EmptyState message="No services yet." /> : (
          <Table>
            <THead><tr><TH>Code</TH><TH>Service</TH><TH>Tariff</TH><TH>VAT</TH><TH align="right">Price</TH></tr></THead>
            <tbody>{services.map((s) => <TR key={s.id}><TD mono>{s.code}</TD><TD>{s.name}{!s.is_active && <span className="text-text-muted"> (not offered)</span>}</TD><TD mono>{s.tariff_code ?? "—"}</TD><TD>{TAX_CATEGORY[s.tax_category]}</TD><TD align="right" mono>{nad(s.unit_price)}</TD></TR>)}</tbody>
          </Table>
        )}
      </div>
    </>
  );
}
