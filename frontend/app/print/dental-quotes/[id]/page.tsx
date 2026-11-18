import type { Metadata } from "next";

import { loadClinical } from "@/features/clinical/load";
import { api } from "@/lib/api";
import { nad } from "@/lib/billing";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import { ageOf } from "@/lib/time";
import type { DentalPlan, Organisation, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Treatment quotation" };

/** Printable quotation for the patient (and their medical aid). Black on white. */
export default async function PrintQuote({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requirePermission("clinical.read");
  const plan = await loadClinical<DentalPlan>(`/dental-plans/${encodeURIComponent(id)}`);
  const [patient, org] = await Promise.all([api<Patient>(`/patients/${plan.patient_id}`), api<Organisation>("/organisation")]);
  const items = plan.items.filter((i) => i.status !== "cancelled");
  return (
    <main className="mx-auto max-w-2xl bg-white p-8 text-sm text-text print:p-0">
      <header className="mb-6 flex justify-between border-b border-text pb-3">
        <div>
          <p className="text-lg font-semibold">{org.name}</p>
          {org.phone && <p>{org.phone}</p>}
          {org.email && <p>{org.email}</p>}
        </div>
        <div className="text-right">
          <p className="text-base font-semibold">Treatment quotation</p>
          <p className="font-mono">{plan.plan_number}</p>
          <p>{formatDate(plan.proposed_at)}</p>
          {plan.quote_valid_until && <p>Valid until {formatDate(plan.quote_valid_until)}</p>}
          {plan.status === "cancelled" && <p className="font-semibold">CANCELLED</p>}
        </div>
      </header>
      <section className="mb-5">
        <p><strong>Patient:</strong> {patient.first_name} {patient.last_name}</p>
        <p><strong>Date of birth:</strong> {formatDate(patient.date_of_birth)} ({ageOf(patient.date_of_birth)} y) · <span className="font-mono">{patient.patient_number}</span></p>
      </section>
      <p className="mb-2 font-semibold">{plan.title}</p>
      <table className="mb-4 w-full border-collapse">
        <thead><tr className="border-b border-text text-left"><th className="py-1 pr-2">Tooth</th><th className="py-1 pr-2">Procedure</th><th className="py-1 text-right">Fee</th></tr></thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className="border-b border-border"><td className="py-1 pr-2 font-mono">{i.tooth ?? ""}{i.surfaces && ` ${i.surfaces}`}</td><td className="py-1 pr-2">{i.procedure}</td><td className="py-1 text-right font-mono">{nad(i.fee)}</td></tr>
          ))}
          <tr><td /><td className="py-1 font-semibold">Total</td><td className="py-1 text-right font-mono font-semibold">{nad(plan.total)}</td></tr>
        </tbody>
      </table>
      {plan.notes && <p className="mb-4 whitespace-pre-wrap">{plan.notes}</p>}
      <p className="mb-8">This is an estimate. Fees may change if the treatment needed changes; we will discuss any change with you first. Medical aid cover is not guaranteed — please confirm with your fund.</p>
      <footer className="grid grid-cols-2 gap-8">
        <div><div className="h-12 border-b border-text" /><p>Patient signature and date</p></div>
        <div><div className="h-12 border-b border-text" /><p>Practitioner</p></div>
      </footer>
    </main>
  );
}
