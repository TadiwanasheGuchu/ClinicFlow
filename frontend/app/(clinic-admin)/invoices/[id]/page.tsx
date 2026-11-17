import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { Button } from "@/components/ui/button";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { creditInvoice, discardInvoice, issueInvoice, prepareClaim, refundInvoice, reversePayment, saveDraft, takePayment } from "@/features/billing/actions";
import { AdjustForm, ClaimPrepareForm, ConfirmAction, DraftEditor, PaymentForm } from "@/features/billing/forms";
import { InvoiceStatusText } from "@/features/billing/status";
import { ReasonAction } from "@/features/clinical/forms";
import { api, ApiError } from "@/lib/api";
import { CLAIM_STATUS, METHOD, nad } from "@/lib/billing";
import { formatDate, formatDateTime } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { AidMembership, ClaimStatus, Invoice, Patient, Service } from "@/types/api";

export const metadata: Metadata = { title: "Invoice" };

export default async function InvoicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("billing.read");
  let inv: Invoice;
  try {
    inv = await api<Invoice>(`/invoices/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && [403, 404, 422].includes(e.status)) notFound();
    throw e;
  }
  const inBranch = (p: string) => access.grants.some((g) => g.permission === p && (g.branch_id === null || g.branch_id === inv.branch_id));
  const canManage = inBranch("billing.manage");
  const canAdjust = inBranch("billing.adjust");
  const canClaim = inBranch("medical_aid.manage");
  const [patient, services, memberships] = await Promise.all([
    api<Patient>(`/patients/${inv.patient_id}`),
    inv.status === "draft" && canManage ? api<Service[]>("/services") : Promise.resolve([] as Service[]),
    canClaim ? api<AidMembership[]>(`/patients/${inv.patient_id}/medical-aid`) : Promise.resolve([] as AidMembership[]),
  ]);
  const name = `${patient.first_name} ${patient.last_name}`;
  const draft = inv.status === "draft";
  const owed = Number(inv.total) - Number(inv.amount_credited);
  const openClaim = inv.claims.find((c) => !["cancelled", "rejected", "paid"].includes(c.status));

  return (
    <>
      <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth }} />
      <PageHeader
        title={draft ? "Draft invoice" : `Invoice ${inv.invoice_number}`}
        description={draft ? "Not yet issued. Numbers are assigned when issued." : `Issued ${formatDate(inv.issued_at)} · due ${formatDate(inv.due_at)}`}
        back={{ href: "/invoices", label: "Invoices" }}
        actions={!draft && <Link href={`/print/invoices/${inv.id}`} target="_blank" className="inline-flex h-9 items-center rounded border border-border bg-surface px-3.5 hover:bg-surface-muted">Print</Link>}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        <Panel>
          <div className="mb-3 flex flex-wrap items-center gap-4">
            <InvoiceStatusText status={inv.status} />
            <span className="text-base">Balance due <span className="font-mono font-semibold">{nad(inv.amount_due)}</span></span>
            {Number(inv.credit_balance) > 0 && <span className="text-base text-warning-text">In credit <span className="font-mono">{nad(inv.credit_balance)}</span> (refund due)</span>}
          </div>
          <Table>
            <THead><tr><TH>Description</TH><TH>Code</TH><TH align="right">Qty</TH><TH align="right">Unit</TH><TH align="right">VAT</TH><TH align="right">Amount</TH></tr></THead>
            <tbody>
              {inv.items.map((i) => (
                <TR key={i.position}>
                  <TD>{i.description}</TD>
                  <TD mono className="text-text-muted">{[i.code, i.tariff_code].filter(Boolean).join(" · ") || "—"}</TD>
                  <TD align="right" mono>{Number(i.quantity)}</TD>
                  <TD align="right" mono>{nad(i.unit_price)}</TD>
                  <TD align="right" mono>{Number(i.tax_rate) ? `${Number(i.tax_rate)}%` : "—"}</TD>
                  <TD align="right" mono>{nad(i.line_total)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
          <dl className="mt-3 ml-auto grid w-72 grid-cols-2 gap-y-1 text-base">
            <dt className="text-text-muted">Subtotal</dt><dd className="text-right font-mono">{nad(inv.subtotal)}</dd>
            <dt className="text-text-muted">VAT</dt><dd className="text-right font-mono">{nad(inv.tax_amount)}</dd>
            <dt className="font-medium">Total</dt><dd className="text-right font-mono font-semibold">{nad(inv.total)}</dd>
            {Number(inv.amount_credited) > 0 && (<><dt className="text-text-muted">Credited</dt><dd className="text-right font-mono">−{nad(inv.amount_credited)}</dd></>)}
            <dt className="text-text-muted">Paid</dt><dd className="text-right font-mono">−{nad(Number(inv.amount_paid) - Number(inv.amount_refunded))}</dd>
            <dt className="font-medium">Balance due</dt><dd className="text-right font-mono font-semibold">{nad(inv.amount_due)}</dd>
          </dl>
          {inv.notes && <p className="mt-3 text-base text-text-muted">{inv.notes}</p>}
        </Panel>

        {draft && canManage && (
          <Panel title="Edit draft">
            <DraftEditor action={saveDraft.bind(null, inv.id)} services={services} items={inv.items} notes={inv.notes} />
            <div className="mt-4 flex flex-wrap items-start gap-3 border-t border-border pt-4">
              <ConfirmAction action={issueInvoice.bind(null, inv.id)} label={`Issue invoice to ${name}`} confirm={`Issue this invoice for ${nad(inv.total)} to ${name}? After issue it can't be edited; corrections are made with credit notes.`} />
              <form action={discardInvoice.bind(null, inv.id)}><Button type="submit" variant="secondary">Discard draft</Button></form>
            </div>
          </Panel>
        )}

        {!draft && canManage && Number(inv.amount_due) > 0 && (
          <Panel title="Take payment"><PaymentForm action={takePayment.bind(null, inv.id)} due={inv.amount_due} /></Panel>
        )}

        {!draft && (
          <Panel title="Payments and adjustments">
            {inv.payments.length + inv.credit_notes.length + inv.refunds.length === 0 ? <p className="text-text-muted">None yet.</p> : (
              <Table>
                <THead><tr><TH>Date</TH><TH>Reference</TH><TH>Type</TH><TH align="right">Amount</TH><TH>Details</TH>{canAdjust && <TH align="right">Actions</TH>}</tr></THead>
                <tbody>
                  {inv.payments.map((p) => (
                    <TR key={p.id} className={p.status === "reversed" ? "text-text-muted" : undefined}>
                      <TD className="tabular">{formatDateTime(p.received_at)}</TD>
                      <TD mono>{p.receipt_number}</TD>
                      <TD>{METHOD[p.method] ?? p.method} payment{p.status === "reversed" && <span className="ml-1 text-danger-text">· reversed</span>}</TD>
                      <TD align="right" mono>{nad(p.amount)}</TD>
                      <TD className="text-sm">{p.reference}{p.reversal_reason && ` · ${p.reversal_reason}`}</TD>
                      {canAdjust && <TD align="right">{p.status === "completed" && <ReasonAction action={reversePayment.bind(null, inv.id, p.id)} label={`Reverse ${p.receipt_number}`} danger />}</TD>}
                    </TR>
                  ))}
                  {inv.credit_notes.map((c) => (
                    <TR key={c.id}><TD className="tabular">{formatDateTime(c.issued_at)}</TD><TD mono>{c.credit_note_number}</TD><TD>Credit note</TD><TD align="right" mono>{nad(c.amount)}</TD><TD className="text-sm">{c.reason}</TD>{canAdjust && <TD />}</TR>
                  ))}
                  {inv.refunds.map((r) => (
                    <TR key={r.id}><TD className="tabular">{formatDateTime(r.refunded_at)}</TD><TD mono>{r.refund_number}</TD><TD>Refund ({METHOD[r.method]})</TD><TD align="right" mono>{nad(r.amount)}</TD><TD className="text-sm">{r.reason}</TD>{canAdjust && <TD />}</TR>
                  ))}
                </tbody>
              </Table>
            )}
            {canAdjust && (
              <div className="mt-3 flex flex-wrap gap-3">
                {owed > 0 && <AdjustForm action={creditInvoice.bind(null, inv.id)} kind="credit" max={owed.toFixed(2)} />}
                {Number(inv.credit_balance) > 0 && <AdjustForm action={refundInvoice.bind(null, inv.id)} kind="refund" max={inv.credit_balance} />}
              </div>
            )}
          </Panel>
        )}

        {!draft && (inv.claims.length > 0 || canClaim) && (
          <Panel title="Medical aid">
            {inv.claims.map((c) => (
              <p key={c.id} className="mb-2 text-base">
                <Link className="font-mono text-primary hover:underline" href={`/claims/${c.id}`}>{c.claim_number}</Link> · {CLAIM_STATUS[c.status as ClaimStatus]} · claimed {nad(c.claimed_amount)}{c.approved_amount && ` · approved ${nad(c.approved_amount)}`} · paid {nad(c.paid_amount)}
              </p>
            ))}
            {canClaim && !openClaim && inv.status !== "credited" && (memberships.filter((m) => m.is_active).length ? (
              <ClaimPrepareForm action={prepareClaim.bind(null, inv.id)} memberships={memberships.filter((m) => m.is_active)} />
            ) : (
              <Notice>No active medical aid recorded. <Link className="underline" href={`/patients/${inv.patient_id}`}>Add it on the patient’s page</Link>.</Notice>
            ))}
          </Panel>
        )}
      </div>
    </>
  );
}
