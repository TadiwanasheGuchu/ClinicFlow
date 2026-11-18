import type { Metadata } from "next";
import Link from "next/link";

import { loadPatientFor } from "@/components/clinical/patient-context";
import { ToothChart } from "@/components/clinical/tooth-chart";
import { PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { ReasonAction } from "@/features/clinical/forms";
import { chartError, savePlan } from "@/features/dental/actions";
import { PlanForm } from "@/features/dental/forms";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { CONDITION_LABEL, PLAN_STATUS } from "@/lib/dental";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Branch, DentalChart, DentalPlan, Page, Service } from "@/types/api";

export const metadata: Metadata = { title: "Dental" };

export default async function DentalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("clinical.read");
  const { patient, name, banner } = await loadPatientFor("dental", id);
  const [chart, plans] = await Promise.all([
    api<DentalChart>(`/patients/${patient.id}/dental-chart`),
    api<DentalPlan[]>(`/patients/${patient.id}/dental-plans`),
  ]);
  const canWrite = hasPermission(access, "clinical.write");
  const [branches, services] = canWrite
    ? await Promise.all([api<Page<Branch>>("/branches", { query: { limit: 200 } }), api<Service[]>("/services")])
    : [null, [] as Service[]];
  const writable = branches?.items.filter((b) => access.grants.some((g) => g.permission === "clinical.write" && (g.branch_id === null || g.branch_id === b.id))) ?? [];
  const hasPrimary = Object.keys(chart.teeth).some((t) => Number(t) >= 51);

  return (
    <>
      {banner}
      <PageHeader title="Dental" description={name} back={{ href: `/patients/${patient.id}/clinical`, label: "Clinical record" }} />
      <div className="flex max-w-5xl flex-col gap-4">
        <Panel title="Tooth chart" description="Findings are recorded during a consultation. Corrections are kept as “entered in error”.">
          <ToothChart teeth={chart.teeth} />
          {hasPrimary && <div className="mt-4"><ToothChart teeth={chart.teeth} primary /></div>}
        </Panel>
        <Panel title="Chart history">
          {chart.history.length === 0 ? <p className="text-text-muted">Nothing recorded yet.</p> : (
            <Table>
              <THead><tr><TH>Recorded</TH><TH>Tooth</TH><TH>Finding</TH><TH>Note</TH><TH>By</TH>{canWrite && <TH align="right">Actions</TH>}</tr></THead>
              <tbody>
                {chart.history.map((e) => (
                  <TR key={e.id} className={e.status !== "recorded" ? "text-text-muted line-through" : undefined}>
                    <TD className="tabular">{formatDateTime(e.recorded_at)}</TD>
                    <TD mono>{e.tooth}{e.surfaces && ` ${e.surfaces}`}</TD>
                    <TD className="no-underline">{CONDITION_LABEL[e.condition]}{e.status !== "recorded" && <span className="block text-sm">Entered in error: {e.status_reason}</span>}</TD>
                    <TD>{e.note ?? "—"}</TD>
                    <TD className="text-text-muted">{e.recorded_by_name}</TD>
                    {canWrite && <TD align="right">{e.status === "recorded" && <ReasonAction action={chartError.bind(null, patient.id, e.id)} label="Entered in error" />}</TD>}
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        <Panel title="Treatment plans">
          {plans.length === 0 ? <p className="text-text-muted">No treatment plans.</p> : (
            <Table>
              <THead><tr><TH>Plan</TH><TH>Created</TH><TH>Status</TH><TH align="right">Total</TH><TH align="right">Done</TH></tr></THead>
              <tbody>
                {plans.map((p) => (
                  <TR key={p.id}>
                    <TD><Link className="text-primary hover:underline" href={`/dental-plans/${p.id}`}><span className="font-mono">{p.plan_number}</span> {p.title}</Link></TD>
                    <TD className="tabular">{formatDate(p.created_at)}</TD>
                    <TD>{PLAN_STATUS[p.status]}</TD>
                    <TD align="right" mono>{nad(p.total)}</TD>
                    <TD align="right" mono>{nad(p.done_total)}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        {canWrite && writable.length > 0 && (
          <Panel title="New treatment plan" description="Draft it, then issue it as a quotation for the patient to accept.">
            <PlanForm action={savePlan.bind(null, patient.id, null)} branches={writable} services={services} />
          </Panel>
        )}
      </div>
    </>
  );
}
