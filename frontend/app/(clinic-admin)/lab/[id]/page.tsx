import type { Metadata } from "next";
import Link from "next/link";

import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { ReasonAction } from "@/features/clinical/forms";
import { loadClinical } from "@/features/clinical/load";
import { cancelOrder, markResultError, progressOrder, recordResults, reviewOrder } from "@/features/lab/actions";
import { ProgressForm, ResultForm, ReviewForm } from "@/features/lab/forms";
import { FlagText, LabStatus } from "@/features/lab/status";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { LAB_STATUS_LABEL, NEXT_STEPS, RESULTABLE } from "@/lib/lab";
import { requirePermission } from "@/lib/session";
import type { AllergySummary, Laboratory, LabOrderDetail, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Laboratory order" };

export default async function LabOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("lab.read");
  const order = await loadClinical<LabOrderDetail>(`/lab-orders/${encodeURIComponent(id)}`);
  const inBranch = (p: string) => access.grants.some((g) => g.permission === p && (g.branch_id === null || g.branch_id === order.branch_id));
  const canProcess = inBranch("lab.process");
  const canReview = inBranch("clinical.sign");
  const clinicalReader = inBranch("clinical.read");
  const canCancel = (canProcess || inBranch("clinical.write")) && ["requested", "collected", "sent", "processing"].includes(order.status);
  const [patient, allergies, laboratories] = await Promise.all([
    api<Patient>(`/patients/${order.patient_id}`),
    clinicalReader ? api<AllergySummary>(`/patients/${order.patient_id}/allergies`) : Promise.resolve(undefined),
    canProcess ? api<Laboratory[]>("/laboratories") : Promise.resolve([] as Laboratory[]),
  ]);
  const name = `${patient.first_name} ${patient.last_name}`;
  const hasFinal = order.items.some((i) => i.resulted);

  return (
    <>
      <PatientIdentityBanner
        patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }}
        allergies={allergies}
        allergiesHiddenLabel="Allergies: in the clinical record"
      />
      <PageHeader
        title={order.order_number}
        description={`Requested by ${order.requested_by_name} · ${formatDateTime(order.requested_at)}${order.laboratory_name ? ` · ${order.laboratory_name}` : ""}`}
        back={{ href: "/lab", label: "Laboratory" }}
        actions={order.status !== "cancelled" && (
          <Link className="inline-flex h-9 items-center rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted" href={`/print/lab-orders/${order.id}`} target="_blank">Print request form</Link>
        )}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <LabStatus status={order.status} />
          {order.urgency === "urgent" && <span className="text-sm font-semibold text-danger-text">Urgent</span>}
          {order.external_reference && <span className="text-sm">Laboratory reference <span className="font-mono">{order.external_reference}</span></span>}
          {clinicalReader && <Link className="text-sm text-primary hover:underline" href={`/consultations/${order.encounter_id}`}>Consultation</Link>}
        </div>
        {order.status === "cancelled" && <Notice tone="error">Cancelled {formatDateTime(order.cancelled_at)}: {order.cancel_reason}</Notice>}
        {order.clinical_information && (
          <Panel title="Clinical information for the laboratory"><p className="text-base whitespace-pre-wrap">{order.clinical_information}</p></Panel>
        )}

        <Panel title="Tests and results">
          <div className="flex flex-col gap-4">
            {order.items.map((item) => (
              <section key={item.id} aria-labelledby={`item-${item.id}`}>
                <h3 id={`item-${item.id}`} className="mb-2 text-base font-medium">
                  {item.test_name}
                  {item.test_code && <span className="ml-2 font-mono text-sm text-text-muted">{item.test_code}</span>}
                  {item.specimen_type && <span className="ml-2 text-sm font-normal text-text-muted">· {item.specimen_type}</span>}
                  {!item.resulted && <span className="ml-2 text-sm font-normal text-text-muted">· awaiting result</span>}
                </h3>
                {item.results.length > 0 && (
                  <Table>
                    <THead><tr><TH>Analyte</TH><TH align="right">Result</TH><TH>Reference range</TH><TH>Flag</TH><TH>Recorded</TH>{canProcess && <TH align="right">Actions</TH>}</tr></THead>
                    <tbody>
                      {item.results.map((r) => {
                        const error = r.status === "entered_in_error";
                        return (
                          <TR key={r.id}>
                            <TD className={cn(error && "text-text-muted line-through")}>
                              {r.analyte}
                              {r.comment && <span className="block text-sm text-text-muted no-underline">{r.comment}</span>}
                            </TD>
                            <TD align="right" mono className={cn(error && "text-text-muted line-through")}>{r.value}{r.unit && ` ${r.unit}`}</TD>
                            <TD mono className="text-text-muted">{r.reference_range ?? "—"}</TD>
                            <TD>{error ? <span className="text-sm text-text-muted">Entered in error: {r.status_reason}</span> : <FlagText flag={r.flag} />}</TD>
                            <TD className="text-sm">{formatDateTime(r.recorded_at)}<span className="block text-text-muted">{r.recorded_by_name}</span></TD>
                            {canProcess && <TD align="right">{!error && <ReasonAction action={markResultError.bind(null, order.id, r.id)} label="Entered in error" />}</TD>}
                          </TR>
                        );
                      })}
                    </tbody>
                  </Table>
                )}
              </section>
            ))}
          </div>
        </Panel>

        {canProcess && RESULTABLE.includes(order.status) && (
          <Panel title="Record results" description={order.status === "reviewed" ? "Adding a result sends this order back for review." : undefined}>
            <ResultForm action={recordResults.bind(null, order.id)} order={order} />
          </Panel>
        )}
        {canProcess && order.status === "requested" && (
          <Notice>Record the specimen collection (or that the patient went to the laboratory) before entering results.</Notice>
        )}

        {canProcess && (NEXT_STEPS[order.status]?.length ?? 0) > 0 && (
          <Panel title="Progress">
            {!hasFinal && order.status !== "requested" && <p className="mb-2 text-sm text-text-muted">“All results in” becomes available once results are recorded.</p>}
            <ProgressForm action={progressOrder.bind(null, order.id)} order={order} laboratories={laboratories} />
          </Panel>
        )}

        {order.status === "completed" && (
          <Panel title="Review">
            {canReview ? (
              <ReviewForm action={reviewOrder.bind(null, order.id)} patientName={name} abnormal={order.abnormal_results} />
            ) : (
              <p className="text-text-muted">Waiting for a clinician to review these results.</p>
            )}
          </Panel>
        )}
        {order.status === "reviewed" && (
          <Panel title="Review">
            <p>Reviewed by {order.reviewed_by_name} · {formatDateTime(order.reviewed_at)}</p>
            {order.review_comment && <p className="mt-1 whitespace-pre-wrap text-text-muted">“{order.review_comment}”</p>}
          </Panel>
        )}

        {canCancel && (
          <Panel title="Cancel order">
            <p className="mb-2 text-sm text-text-muted">Only possible before any results are recorded. The order and its history are kept.</p>
            <ReasonAction action={cancelOrder.bind(null, order.id)} label={`Cancel ${order.order_number} for ${name}`} danger />
          </Panel>
        )}

        <Panel title="History">
          <ol className="flex flex-col gap-1 text-sm">
            {order.events.map((e, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className="tabular text-text-muted">{formatDateTime(e.occurred_at)}</span>
                <span className="font-medium">{LAB_STATUS_LABEL[e.to_status]}</span>
                <span className="text-text-muted">· {e.actor_name}</span>
                {e.note && <span className="text-text-muted">· “{e.note}”</span>}
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </>
  );
}
