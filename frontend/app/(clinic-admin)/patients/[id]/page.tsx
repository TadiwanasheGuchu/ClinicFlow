import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { ButtonLink } from "@/components/ui/button";
import { Details, EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { addMembership, verifyMembership } from "@/features/billing/actions";
import { MembershipForm } from "@/features/billing/forms";
import { createLinkCode, revokePortalAccess } from "@/features/messages/actions";
import { nad } from "@/lib/billing";
import { LinkCodeButton } from "@/features/messages/link-code";
import { updatePatient } from "@/features/patients/actions";
import { Button } from "@/components/ui/button";
import { PatientForm } from "@/features/patients/patient-form";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { AidMembership, AllergySummary, Appointment, Fund, InvoiceSummary, Page, Patient, PortalAccountStatus } from "@/types/api";

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
  const clinical = hasPermission(access, "clinical.read");
  const allergies = clinical ? await api<AllergySummary>(`/patients/${patient.id}/allergies`) : undefined;
  const [memberships, funds] = await Promise.all([
    api<AidMembership[]>(`/patients/${patient.id}/medical-aid`),
    canWrite ? api<Fund[]>("/medical-aid/funds") : Promise.resolve([] as Fund[]),
  ]);
  const billing = hasPermission(access, "billing.read");
  const outstanding = billing ? await api<Page<InvoiceSummary>>("/invoices", { query: { patient_id: patient.id, status: "outstanding", limit: 50 } }) : null;
  const balance = outstanding?.items.reduce((sum, i) => sum + Number(i.amount_due), 0) ?? 0;

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
      <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }} allergies={allergies} />
      <PageHeader
        title={name}
        back={{ href: "/patients", label: "Patients" }}
        actions={
          <>
            {clinical && <ButtonLink href={`/patients/${patient.id}/clinical`} variant="secondary">Clinical record</ButtonLink>}
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
        <Panel title="Medical aid">
          {memberships.length ? (
            <ul className="mb-3 flex flex-col gap-2">
              {memberships.map((m) => (
                <li key={m.id} className={`flex flex-wrap items-center justify-between gap-2 ${m.is_active ? "" : "text-text-muted"}`}>
                  <span>
                    <span className="font-medium">{m.fund_name}</span>{m.plan_name && ` · ${m.plan_name}`} · <span className="font-mono text-sm">{m.membership_number}{m.dependant_code && ` / ${m.dependant_code}`}</span>
                    {m.principal_member_name && <span className="text-text-muted"> · principal {m.principal_member_name}</span>}
                    <span className="ml-2 text-sm">{m.verification_status === "unverified" ? <span className="text-warning-text">Not verified</span> : <span className="text-success-text">Verified {m.verification_status === "verified_by_phone" ? "by phone" : "from card"} {formatDate(m.verified_at)}</span>}</span>
                  </span>
                  {canWrite && m.verification_status === "unverified" && (
                    <span className="flex gap-2">
                      <form action={verifyMembership.bind(null, patient.id, m.id, "verified_by_card")}><Button type="submit" size="sm" variant="secondary">Seen card</Button></form>
                      <form action={verifyMembership.bind(null, patient.id, m.id, "verified_by_phone")}><Button type="submit" size="sm" variant="secondary">Confirmed with fund</Button></form>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : <p className="mb-3 text-text-muted">No medical aid recorded (private patient).</p>}
          {canWrite && (funds.length ? <MembershipForm action={addMembership.bind(null, patient.id)} funds={funds} /> : <p className="text-sm text-text-muted">Add funds under Medical aid funds first.</p>)}
        </Panel>

        {billing && outstanding && (
          <Panel title="Account">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-base">Outstanding <span className="font-mono font-semibold">{nad(balance)}</span> on {outstanding.total} invoice{outstanding.total === 1 ? "" : "s"}</p>
              <span className="flex gap-2">
                <ButtonLink variant="secondary" href={`/invoices?status=&q=${encodeURIComponent(patient.patient_number)}`}>Invoices</ButtonLink>
                {hasPermission(access, "billing.manage") && <ButtonLink href={`/invoices/new?patient=${patient.id}`}>New invoice</ButtonLink>}
              </span>
            </div>
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
