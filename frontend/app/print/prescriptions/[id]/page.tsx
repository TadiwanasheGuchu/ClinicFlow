import type { Metadata } from "next";

import { loadClinical } from "@/features/clinical/load";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import { ageOf } from "@/lib/time";
import type { Organisation, Patient, Prescription } from "@/types/api";

export const metadata: Metadata = { title: "Prescription" };

/** Printable prescription. Plain black-on-white for photocopying and fax. */
export default async function PrintPrescription({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requirePermission("clinical.read");
  const rx = await loadClinical<Prescription>(`/prescriptions/${encodeURIComponent(id)}`);
  const [patient, org] = await Promise.all([api<Patient>(`/patients/${rx.patient_id}`), api<Organisation>("/organisation")]);
  return (
    <main className="mx-auto max-w-2xl bg-white p-8 text-sm text-text print:p-0">
      <header className="mb-6 flex justify-between border-b border-text pb-3">
        <div>
          <p className="text-lg font-semibold">{org.name}</p>
          {org.phone && <p>{org.phone}</p>}
          {org.email && <p>{org.email}</p>}
        </div>
        <div className="text-right">
          <p className="font-mono">{rx.prescription_number}</p>
          <p>{formatDate(rx.issued_at)}</p>
          {rx.status === "cancelled" && <p className="font-semibold">CANCELLED</p>}
        </div>
      </header>
      <section className="mb-5">
        <p><strong>Patient:</strong> {patient.first_name} {patient.last_name}</p>
        <p><strong>Date of birth:</strong> {formatDate(patient.date_of_birth)} ({ageOf(patient.date_of_birth)} y) · <span className="font-mono">{patient.patient_number}</span></p>
        {patient.address && <p><strong>Address:</strong> {patient.address}</p>}
      </section>
      <p className="mb-2 text-lg font-semibold">Rx</p>
      <ol className="mb-8 flex list-decimal flex-col gap-3 pl-5">
        {rx.items.map((i) => (
          <li key={i.position}>
            <p><strong>{i.medication}</strong> {i.strength} {i.dosage_form}</p>
            <p>{i.dose}, {i.frequency}{i.route && `, ${i.route}`}{i.duration && `, for ${i.duration}`}</p>
            {i.quantity && <p>Quantity: {i.quantity}</p>}
            {i.instructions && <p>{i.instructions}</p>}
          </li>
        ))}
      </ol>
      <footer className="mt-12 grid grid-cols-2 gap-8">
        <div>
          <div className="h-12 border-b border-text" />
          <p>Signature</p>
        </div>
        <div>
          <p className="font-semibold">{rx.prescriber_name}</p>
          <p>{rx.prescriber_registration}</p>
        </div>
      </footer>
    </main>
  );
}
