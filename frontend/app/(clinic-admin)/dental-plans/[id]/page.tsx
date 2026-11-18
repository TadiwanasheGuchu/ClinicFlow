import type { Metadata } from "next";
import Link from "next/link";

import { loadPatientFor } from "@/components/clinical/patient-context";
import { SubmitButton } from "@/components/ui/form";
import { Field, Input, Select } from "@/components/ui/field";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { ReasonAction } from "@/features/clinical/forms";
import { loadClinical } from "@/features/clinical/load";
import { cancelPlan, decidePlan, invoicePlan, itemCancel, itemDone, proposePlan, savePlan } from "@/features/dental/actions";
import { PlanForm } from "@/features/dental/forms";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { PLAN_STATUS } from "@/lib/dental";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Branch, ClinicalSummary, DentalPlan, Page, Service } from "@/types/api";

export const metadata: Metadata = { title: "Treatment plan" };

const ITEM_STATUS = { planned: "Planned", done: "Done", cancelled: "Cancelled" } as const;

export default async function PlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("clinical.read");
  const plan = await loadClinical<DentalPlan>(`/dental-plans/${encodeURIComponent(id)}`);
  const { name, banner } = await loadPatientFor("dental", plan.patient_id);
  const inBranch = (p: string) => access.grants.some((g) => g.permission === p && (g.branch_id === null || g.branch_id === plan.branch_id));
  const canWrite = inBranch("clinical.write");
  const canInvoice = canWrite && inBranch("billing.manage");
  const [branches, services, summary] = await Promise.all([
    canWrite && plan.status === "draft" ? api<Page<Branch>>("/branches", { query: { limit: 200 } }) : Promise.resolve(null),
    canWrite && plan.status === "draft" ? api<Service[]>("/services") : Promise.resolve([] as Service[]),
    canWrite && plan.status === "accepted" ? api<ClinicalSummary>(`/patients/${plan.patient_id}/clinical-summary`) : Promise.resolve(null),
  ]);
  const consultations = summary?.encounters.slice(0, 10) ?? [];

  return (
    <>
      {banner}
      <PageHeader
        title={`${plan.plan_number} · ${plan.title}`}
        description={`${PLAN_STATUS[plan.status]} · created by ${plan.created_by_name}, ${formatDate(plan.created_at)}${plan.quote_valid_until ? ` · quotation valid until ${formatDate(plan.quote_valid_until)}` : ""}`}
        back={{ href: `/patients/${plan.patient_id}/dental`, label: "Dental" }}
        actions={plan.status !== "draft" && (
          <Link className="inline-flex h-9 items-center rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted" href={`/print/dental-quotes/${plan.id}`} target="_blank">Print quotation</Link>
        )}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        {plan.status === "cancelled" && <Notice tone="error">Cancelled {formatDateTime(plan.closed_at)}: {plan.cancel_reason}</Notice>}
        {plan.decision_note && <Notice>Patient {plan.status === "declined" ? "declined" : "accepted"} {formatDateTime(plan.decided_at)}: {plan.decision_note}</Notice>}
        <Panel title="Treatment">
          <Table>
            <THead><tr><TH>Tooth</TH><TH>Procedure</TH><TH align="right">Fee</TH><TH>Status</TH>{canWrite && plan.status === "accepted" && <TH align="right">Actions</TH>}</tr></THead>
            <tbody>
              {plan.items.map((i) => (
                <TR key={i.id}>
                  <TD mono>{i.tooth ?? "—"}{i.surfaces && ` ${i.surfaces}`}</TD>
                  <TD className={i.status === "cancelled" ? "text-text-muted line-through" : undefined}>{i.procedure}</TD>
                  <TD align="right" mono>{nad(i.fee)}</TD>
                  <TD>{ITEM_STATUS[i.status]}{i.done_at && <span className="text-sm text-text-muted"> · {formatDate(i.done_at)}</span>}{i.invoice_id && <> · <Link className="text-sm text-primary hover:underline" href={`/invoices/${i.invoice_id}`}>invoiced</Link></>}</TD>
                  {canWrite && plan.status === "accepted" && (
                    <TD align="right">
                      {i.status === "planned" && (
                        <div className="flex flex-wrap justify-end gap-2">
                          <QuickForm action={itemDone.bind(null, plan.id, i.id)} className="justify-end">
                            <label className="sr-only" htmlFor={`enc-${i.id}`}>Consultation</label>
                            <Select id={`enc-${i.id}`} name="encounter_id" className="w-44">
                              <option value="">No consultation</option>
                              {consultations.map((c) => <option key={c.id} value={c.id}>{formatDate(c.started_at)} · {c.clinician_name}</option>)}
                            </Select>
                            <SubmitButton variant="secondary">Mark done</SubmitButton>
                          </QuickForm>
                          <QuickForm action={itemCancel.bind(null, plan.id, i.id)} submit="Won't do" variant="secondary" />
                        </div>
                      )}
                    </TD>
                  )}
                </TR>
              ))}
              <TR><TD /><TD className="font-medium">Total</TD><TD align="right" mono className="font-semibold">{nad(plan.total)}</TD><TD /></TR>
            </tbody>
          </Table>
          {plan.notes && <p className="mt-3 text-sm whitespace-pre-wrap text-text-muted">{plan.notes}</p>}
        </Panel>

        {canWrite && plan.status === "draft" && branches && (
          <>
            <Panel title="Issue quotation" description="Freezes the treatment and fees. Changes after this need a new plan.">
              <QuickForm action={proposePlan.bind(null, plan.id)} submit={`Issue quotation to ${name}`}>
                <Field id="valid" label="Valid for (days)"><Input id="valid" name="valid_days" type="number" min={1} max={365} defaultValue={30} className="w-24 text-right font-mono" /></Field>
              </QuickForm>
            </Panel>
            <Panel title="Edit draft"><PlanForm action={savePlan.bind(null, plan.patient_id, plan.id)} branches={branches.items} services={services} plan={plan} /></Panel>
          </>
        )}
        {canWrite && plan.status === "proposed" && (
          <Panel title="Patient’s decision">
            <QuickForm action={decidePlan.bind(null, plan.id)}>
              <Field id="dn" label="How it was given"><Input id="dn" name="note" placeholder="e.g. Signed quotation" className="w-64" /></Field>
              <SubmitButton name="decision" value="accepted">{name} accepted</SubmitButton>
              <SubmitButton name="decision" value="declined" variant="secondary">Declined</SubmitButton>
            </QuickForm>
          </Panel>
        )}
        {canInvoice && Number(plan.uninvoiced_done_total) > 0 && (
          <Panel title="Invoice completed treatment" description={`${nad(plan.uninvoiced_done_total)} of completed treatment is not yet invoiced. A draft invoice is created for you to check and issue.`}>
            <QuickForm action={invoicePlan.bind(null, plan.id)} submit="Create draft invoice" />
          </Panel>
        )}
        {canWrite && ["draft", "proposed", "accepted"].includes(plan.status) && !plan.items.some((i) => i.status === "done") && (
          <Panel title="Cancel plan"><ReasonAction action={cancelPlan.bind(null, plan.id)} label={`Cancel ${plan.plan_number} for ${name}`} danger /></Panel>
        )}
        {!hasPermission(access, "clinical.write") && <p className="text-sm text-text-muted">View only.</p>}
      </div>
    </>
  );
}
