import type { Metadata } from "next";

import { loadClinical } from "@/features/clinical/load";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, humanise } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import { ageOf } from "@/lib/time";
import type { LabOrderDetail, Organisation, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Laboratory request" };

/** Printable request form the patient takes to the laboratory. Black on white for copying. */
export default async function PrintLabOrder({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requirePermission("lab.read");
  const order = await loadClinical<LabOrderDetail>(`/lab-orders/${encodeURIComponent(id)}`);
  const [patient, org] = await Promise.all([api<Patient>(`/patients/${order.patient_id}`), api<Organisation>("/organisation")]);
  return (
    <main className="mx-auto max-w-2xl bg-white p-8 text-sm text-text print:p-0">
      <header className="mb-6 flex justify-between border-b border-text pb-3">
        <div>
          <p className="text-lg font-semibold">{org.name}</p>
          {org.phone && <p>{org.phone}</p>}
          {org.email && <p>{org.email}</p>}
        </div>
        <div className="text-right">
          <p className="text-base font-semibold">Laboratory request</p>
          <p className="font-mono">{order.order_number}</p>
          <p>{formatDate(order.requested_at)}</p>
          {order.urgency === "urgent" && <p className="font-semibold">URGENT</p>}
          {order.status === "cancelled" && <p className="font-semibold">CANCELLED</p>}
        </div>
      </header>
      <section className="mb-5">
        <p><strong>Patient:</strong> {patient.first_name} {patient.last_name}</p>
        <p><strong>Date of birth:</strong> {formatDate(patient.date_of_birth)} ({ageOf(patient.date_of_birth)} y){patient.sex && ` · ${humanise(patient.sex)}`} · <span className="font-mono">{patient.patient_number}</span></p>
        {patient.phone && <p><strong>Phone:</strong> {patient.phone}</p>}
        {order.laboratory_name && <p><strong>Laboratory:</strong> {order.laboratory_name}</p>}
      </section>
      <p className="mb-2 font-semibold">Tests requested</p>
      <table className="mb-6 w-full border-collapse">
        <thead><tr className="border-b border-text text-left"><th className="py-1 pr-2">Test</th><th className="py-1 pr-2">Code</th><th className="py-1">Specimen</th></tr></thead>
        <tbody>
          {order.items.map((i) => (
            <tr key={i.id} className="border-b border-border"><td className="py-1 pr-2">{i.test_name}</td><td className="py-1 pr-2 font-mono">{i.test_code ?? ""}</td><td className="py-1">{i.specimen_type ?? ""}</td></tr>
          ))}
        </tbody>
      </table>
      {order.clinical_information && (
        <section className="mb-6"><p className="font-semibold">Clinical information</p><p className="whitespace-pre-wrap">{order.clinical_information}</p></section>
      )}
      {order.collected_at && <p className="mb-6">Specimen collected {formatDateTime(order.collected_at)}</p>}
      <footer className="mt-12 grid grid-cols-2 gap-8">
        <div><div className="h-12 border-b border-text" /><p>Signature</p></div>
        <div><p className="font-semibold">{order.requested_by_name}</p><p>Please send results to {org.email ?? org.name}, quoting {order.order_number}.</p></div>
      </footer>
    </main>
  );
}
