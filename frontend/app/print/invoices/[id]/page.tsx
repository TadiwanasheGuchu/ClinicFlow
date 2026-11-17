import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { METHOD, nad } from "@/lib/billing";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { Invoice, Organisation, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Invoice" };

/** Printable tax invoice / statement of account for one invoice. */
export default async function PrintInvoice({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requirePermission("billing.read");
  let inv: Invoice;
  try { inv = await api<Invoice>(`/invoices/${encodeURIComponent(id)}`); } catch (e) { if (e instanceof ApiError) notFound(); throw e; }
  if (inv.status === "draft") notFound();
  const [patient, org] = await Promise.all([api<Patient>(`/patients/${inv.patient_id}`), api<Organisation>("/organisation")]);
  const vat = org.settings.vat_registered;
  return (
    <main className="mx-auto max-w-3xl bg-white p-8 text-sm text-text print:p-0">
      <header className="mb-6 flex justify-between border-b border-text pb-3">
        <div>
          <p className="text-lg font-semibold">{org.legal_name ?? org.name}</p>
          {org.registration_number && <p>Reg. {org.registration_number}</p>}
          {vat && org.settings.vat_number && <p>VAT no. {org.settings.vat_number}</p>}
          {org.phone && <p>{org.phone}</p>}{org.email && <p>{org.email}</p>}
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold">{vat ? "Tax invoice" : "Invoice"}</p>
          <p className="font-mono">{inv.invoice_number}</p>
          <p>Issued {formatDate(inv.issued_at)}</p><p>Due {formatDate(inv.due_at)}</p>
        </div>
      </header>
      <section className="mb-5">
        <p><strong>{patient.first_name} {patient.last_name}</strong> · <span className="font-mono">{patient.patient_number}</span></p>
        {patient.address && <p>{patient.address}</p>}
      </section>
      <table className="mb-4 w-full border-collapse">
        <thead><tr className="border-b border-text text-left"><th className="py-1">Description</th><th className="py-1">Code</th><th className="py-1 text-right">Qty</th><th className="py-1 text-right">Unit</th>{vat && <th className="py-1 text-right">VAT</th>}<th className="py-1 text-right">Amount</th></tr></thead>
        <tbody className="tabular">
          {inv.items.map((i) => (
            <tr key={i.position} className="border-b border-border">
              <td className="py-1">{i.description}</td><td className="py-1 font-mono">{i.tariff_code ?? i.code ?? ""}</td>
              <td className="py-1 text-right">{Number(i.quantity)}</td><td className="py-1 text-right font-mono">{nad(i.unit_price)}</td>
              {vat && <td className="py-1 text-right font-mono">{nad(i.tax_amount)}</td>}<td className="py-1 text-right font-mono">{nad(i.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="ml-auto grid w-72 grid-cols-2 gap-y-1">
        <dt>Subtotal</dt><dd className="text-right font-mono">{nad(inv.subtotal)}</dd>
        {vat && (<><dt>VAT</dt><dd className="text-right font-mono">{nad(inv.tax_amount)}</dd></>)}
        <dt className="font-semibold">Total</dt><dd className="text-right font-mono font-semibold">{nad(inv.total)}</dd>
        {Number(inv.amount_credited) > 0 && (<><dt>Credited</dt><dd className="text-right font-mono">−{nad(inv.amount_credited)}</dd></>)}
        <dt>Paid</dt><dd className="text-right font-mono">−{nad(Number(inv.amount_paid) - Number(inv.amount_refunded))}</dd>
        <dt className="font-semibold">Balance due</dt><dd className="text-right font-mono font-semibold">{nad(inv.amount_due)}</dd>
      </dl>
      {inv.payments.filter((p) => p.status === "completed").length > 0 && (
        <section className="mt-6">
          <p className="font-semibold">Payments received</p>
          {inv.payments.filter((p) => p.status === "completed").map((p) => <p key={p.id}><span className="font-mono">{p.receipt_number}</span> · {formatDate(p.received_at)} · {METHOD[p.method]} · <span className="font-mono">{nad(p.amount)}</span></p>)}
        </section>
      )}
    </main>
  );
}
