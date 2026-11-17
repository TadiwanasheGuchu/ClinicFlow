import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { ButtonLink } from "@/components/ui/button";
import { Details, EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { createLinkCode, revokePortalAccess } from "@/features/messages/actions";
import { LinkCodeButton } from "@/features/messages/link-code";
import { updatePatient } from "@/features/patients/actions";
import { Button } from "@/components/ui/button";
import { PatientForm } from "@/features/patients/patient-form";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Appointment, Page, Patient, PortalAccountStatus } from "@/types/api";

export const metadata: Metadata = { title: "Patient" };

const CHANNEL: Record<string, string> = { sms: "SMS", whatsapp: "WhatsApp", email: "Email", phone: "Phone call", none: "No reminders" };

export default async function PatientPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ edit?: string }> }) {
  const { id } = await params;
  const { edit } = await searchParams;
  const { access } = await requirePermission("patients.read");
  let patient: Patient;
  try {
    patient = await api<Patient>(`/patients/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const canWrite = hasPermission(access, "patients.write");
  const canBook = hasPermission(access, "appointments.manage");
  const appointments = hasPermission(access, "appointments.read")
    ? await api<Page<Appointment>>("/appointments", { query: { patient_id: patient.id, limit: 50 } })
    : null;
  const now = Date.now();
  const upcoming = appointments?.items.filter((a) => new Date(a.end_at).getTime() >= now).sort((a, b) => a.start_at.localeCompare(b.start_at)) ?? [];
  const past = appointments?.items.filter((a) => new Date(a.end_at).getTime() < now).sort((a, b) => b.start_at.localeCompare(a.start_at)) ?? [];
  const name = `${patient.first_name} ${patient.last_name}`;
  const online = await api<PortalAccountStatus>(`/patients/${patient.id}/portal-account`);

  const list = (items: Appointment[]) => (
    <Table>
      <THead>
        <tr><TH>When</TH><TH>Reference</TH><TH>Practitioner</TH><TH>Type</TH><TH>Branch</TH><TH>Status</TH></tr>
      </THead>
      <tbody>
        {items.map((a) => (
          <TR key={a.id}>
            <TD className="tabular whitespace-nowrap"><Link className="text-primary hover:underline" href={`/appointments/${a.id}`}>{formatDateTime(a.start_at)}</Link></TD>
            <TD mono>{a.reference}</TD>
            <TD>{a.provider.name}</TD>
            <TD>{a.appointment_type.name}</TD>
            <TD className="text-text-muted">{a.branch.name}</TD>
            <TD><AppointmentStatus status={a.status} /></TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );

  return (
    <>
      <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }} />
      <PageHeader
        title={name}
        back={{ href: "/patients", label: "Patients" }}
        actions={
          <>
            {canWrite && !edit && <ButtonLink href={`/patients/${patient.id}?edit=1`} variant="secondary">Edit details</ButtonLink>}
            {canBook && patient.status === "active" && <ButtonLink href={`/appointments/new?patient=${patient.id}`}>Book appointment</ButtonLink>}
          </>
        }
      />
      <div className="flex max-w-5xl flex-col gap-4">
        {edit && canWrite ? (
          <Panel title="Edit details">
            <PatientForm action={updatePatient.bind(null, patient.id)} patient={patient} />
          </Panel>
        ) : (
          <Panel>
            <Details
              items={[
                { label: "Mobile", value: patient.phone },
                { label: "Email", value: patient.email },
                { label: "Preferred reminders", value: CHANNEL[patient.preferred_channel] },
                { label: "ID or passport", value: patient.id_number, mono: true },
                { label: "Nationality", value: patient.nationality },
                { label: "Address", value: patient.address },
                { label: "Emergency contact", value: patient.emergency_contact ? `${patient.emergency_contact.name} (${patient.emergency_contact.relationship ?? "contact"}) · ${patient.emergency_contact.phone}` : null },
                { label: "Registered", value: formatDate(patient.created_at) },
              ]}
            />
          </Panel>
        )}
        <Panel title="Online access" description="Lets the patient book and manage appointments in the patient portal.">
          {online.linked ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-base">Connected to <span className="font-medium">{online.email}</span> since {formatDate(online.linked_at)} ({online.linked_via === "code" ? "link code" : "self-registration"}).</p>
              {canWrite && (
                <form action={revokePortalAccess.bind(null, patient.id)}>
                  <Button type="submit" variant="secondary">Turn off online access for {name}</Button>
                </form>
              )}
            </div>
          ) : canWrite ? (
            <>
              <p className="mb-3 text-base text-text-muted">Not connected. Create a one-time code (valid 7 days) for the patient to enter online with their date of birth.</p>
              <LinkCodeButton action={createLinkCode.bind(null, patient.id)} />
            </>
          ) : (
            <p className="text-text-muted">Not connected.</p>
          )}
        </Panel>
        {appointments && (
          <>
            <section>
              <h2 className="mb-2 text-md text-text">Upcoming appointments</h2>
              {upcoming.length ? list(upcoming) : <EmptyState message="No upcoming appointments." />}
            </section>
            {past.length > 0 && (
              <section>
                <h2 className="mb-2 text-md text-text">Past appointments</h2>
                {list(past)}
              </section>
            )}
          </>
        )}
      </div>
    </>
  );
}
