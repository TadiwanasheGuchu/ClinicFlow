import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Details, Notice, PageHeader, Panel } from "@/components/ui/layout";
import { claimTransition, editClaim, recordRemittance } from "@/features/billing/actions";
import { ClaimEditForm, ClaimTransitionForm, RemittanceForm } from "@/features/billing/forms";
import { api, ApiError } from "@/lib/api";
import { CLAIM_ACTION, CLAIM_NEXT, CLAIM_STATUS, nad } from "@/lib/billing";
import { formatDateTime, humanise } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { ClaimDetail, ClaimStatus } from "@/types/api";

export const metadata: Metadata = { title: "Claim" };

const FIELDS: Partial<Record<ClaimStatus, ("fund_reference" | "submission_method" | "approved_amount" | "reason")[]>> = {
  submitted: ["submission_method", "fund_reference"], accepted: ["approved_amount", "fund_reference"],
  rejected: ["reason", "fund_reference"], resubmission_required: ["reason"], cancelled: ["reason"],
};

export default async function ClaimPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("billing.read");
  let claim: ClaimDetail;
  try { claim = await api<ClaimDetail>(`/claims/${encodeURIComponent(id)}`); } catch (e) { if (e instanceof ApiError && [403, 404, 422].includes(e.status)) notFound(); throw e; }
  const canManage = access.permissions.includes("medical_aid.manage");
  const s = claim.membership_snapshot;
  const remaining = Number(claim.approved_amount ?? 0) - Number(claim.paid_amount);

  return (
    <>
      <PageHeader title={`Claim ${claim.claim_number}`} description={`${claim.patient_name} · ${claim.fund_name}`} back={{ href: "/claims", label: "Claims" }} />
      <div className="flex max-w-4xl flex-col gap-4">
        <Notice>ClinicFlow does not send claims to funds. Submit it by email, the fund’s portal or on paper, then record what happened here.</Notice>
        <Panel>
          <p className="mb-3 text-md font-medium">{CLAIM_STATUS[claim.status]}{claim.rejection_reason && <span className="ml-2 text-base font-normal text-danger-text">— {claim.rejection_reason}</span>}</p>
          <Details items={[
            { label: "Invoice", value: <Link className="font-mono text-primary hover:underline" href={`/invoices/${claim.invoice_id}`}>{claim.invoice_number}</Link> },
            { label: "Membership", value: `${s.membership_number}${s.dependant_code ? ` / ${s.dependant_code}` : ""}${s.plan ? ` · ${s.plan}` : ""}`, mono: true },
            { label: "Principal member", value: s.principal_member },
            { label: "ICD-10 codes", value: claim.diagnosis_codes.join(", ") || "None — required before submission", mono: true },
            { label: "Claimed", value: nad(claim.claimed_amount), mono: true },
            { label: "Approved", value: nad(claim.approved_amount), mono: true },
            { label: "Paid by fund", value: nad(claim.paid_amount), mono: true },
            { label: "Patient’s share of the invoice", value: nad(claim.patient_portion), mono: true },
            { label: "Fund reference", value: claim.fund_reference, mono: true },
            { label: "Submitted", value: claim.submitted_at ? `${formatDateTime(claim.submitted_at)} (${claim.submission_method?.replace("_", " ")})` : null },
          ]} />
        </Panel>

        {canManage && claim.status === "draft" && (
          <Panel title="Edit draft"><ClaimEditForm action={editClaim.bind(null, claim.id)} codes={claim.diagnosis_codes} amount={claim.claimed_amount} /></Panel>
        )}

        {canManage && CLAIM_NEXT[claim.status].length > 0 && (
          <Panel title="Next step">
            <div className="flex flex-wrap items-start gap-2">
              {CLAIM_NEXT[claim.status].map((next) => (
                <ClaimTransitionForm key={next} action={claimTransition.bind(null, claim.id, next)} label={CLAIM_ACTION[next] ?? next} fields={FIELDS[next] ?? []} danger={next === "cancelled" || next === "rejected"} />
              ))}
            </div>
          </Panel>
        )}

        {canManage && (claim.status === "accepted" || claim.status === "partially_paid") && remaining > 0 && (
          <Panel title="Payment from the fund" description="Recorded as a medical aid payment on the invoice.">
            <RemittanceForm action={recordRemittance.bind(null, claim.id)} max={remaining.toFixed(2)} />
          </Panel>
        )}

        <Panel title="History">
          <ol className="flex flex-col gap-2">
            {claim.events.map((e) => (
              <li key={e.id} className="grid grid-cols-[150px_1fr] gap-3 text-base">
                <span className="tabular text-text-muted">{formatDateTime(e.created_at)}</span>
                <span>
                  {e.event_type === "status_changed" && e.previous_status ? `${CLAIM_STATUS[e.previous_status as ClaimStatus]} → ${CLAIM_STATUS[e.new_status as ClaimStatus]}` : humanise(e.event_type)}
                  {e.message && <span className="text-text-muted"> · “{e.message}”</span>}
                  {typeof e.details.amount === "string" && <span className="font-mono text-sm"> · {nad(e.details.amount)}</span>}
                </span>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </>
  );
}
