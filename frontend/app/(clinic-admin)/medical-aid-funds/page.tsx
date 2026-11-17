import type { Metadata } from "next";

import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { saveFund } from "@/features/billing/actions";
import { FundForm } from "@/features/billing/forms";
import { api } from "@/lib/api";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Fund } from "@/types/api";

export const metadata: Metadata = { title: "Medical aid funds" };

export default async function FundsPage() {
  const { access } = await requirePermission("patients.read");
  const funds = await api<Fund[]>("/medical-aid/funds", { query: { include_inactive: true } });
  const canEdit = hasOrgWide(access, "medical_aid.manage");
  return (
    <>
      <PageHeader title="Medical aid funds" description="Funds your practice claims from, and where to send claims." />
      <div className="flex max-w-5xl flex-col gap-3">
        {canEdit ? (
          <>
            {funds.map((f) => <Panel key={f.id}><FundForm action={saveFund.bind(null, f.id)} item={f} /></Panel>)}
            <Panel title="Add fund"><FundForm action={saveFund.bind(null, null)} /></Panel>
          </>
        ) : funds.length === 0 ? <EmptyState message="No funds recorded." /> : (
          <Table>
            <THead><tr><TH>Fund</TH><TH>Administrator</TH><TH>Phone</TH><TH>Claims email</TH></tr></THead>
            <tbody>{funds.map((f) => <TR key={f.id}><TD>{f.name}</TD><TD>{f.administrator ?? "—"}</TD><TD>{f.phone ?? "—"}</TD><TD>{f.email ?? "—"}</TD></TR>)}</tbody>
          </Table>
        )}
      </div>
    </>
  );
}
