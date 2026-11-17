import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { Button } from "@/components/ui/button";
import { Details, Notice, PageHeader, Panel } from "@/components/ui/layout";
import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { cancelAppointment, rescheduleAppointment, setAppointmentStatus } from "@/features/appointments/actions";
import { startConsultation } from "@/features/clinical/actions";
import { invoiceForAppointment } from "@/features/billing/actions";
import { CancelForm, RescheduleForm } from "@/features/appointments/manage";
import { MessagesTable } from "@/features/messages/messages-table";
import { ACTION_LABEL, CANCELLABLE, NEXT_STATUSES, RESCHEDULABLE, STATUS_LABEL, VIOLATION_LABEL } from "@/lib/appointments";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, humanise } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import { dateOf, longDate, timeOf, todayISO } from "@/lib/time";
import type { AllergySummary, AppointmentDetail, AppointmentEvent, AppointmentStatus as S, Encounter, Notification, Page } from "@/types/api";

export const metadata: Metadata = { title: "Appointment" };

const SOURCE: Record<string, string> = { reception: "At reception", phone: "Phone", walk_in: "Walk-in", online: "Online" };

function describe(e: AppointmentEvent): string {
  if (e.event_type === "status_changed" && e.previous_status && e.new_status)
    return `${STATUS_LABEL[e.previous_status as S]} → ${STATUS_LABEL[e.new_status as S]}`;
  if (e.event_type === "rescheduled") {
    const from = (e.details.from as { start_at?: string } | undefined)?.start_at;
    const to = (e.details.to as { start_at?: string } | undefined)?.start_at;
    return `Moved from ${formatDateTime(from)} to ${formatDateTime(to)}`;
  }
  if (e.event_type === "created") return `Booked (${STATUS_LABEL[e.new_status as S] ?? e.new_status})`;
  return humanise(e.event_type);
}

export default async function AppointmentPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ booked?: string }> }) {
  const { id } = await params;
  const { booked } = await searchParams;
  const { access, me } = await requirePermission("appointments.read");
  let appt: AppointmentDetail;
  try {
    appt = await api<AppointmentDetail>(`/appointments/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
  const messages = await api<Page<Notification>>("/notifications", { query: { appointment_id: appt.id, limit: 50 } });
  const inBranch = (perm: string) => access.grants.some((g) => g.permission === perm && (g.branch_id === null || g.branch_id === appt.branch.id));
  const canManage = inBranch("appointments.manage");
  const canComplete = inBranch("clinical.write");
  const canReadClinical = inBranch("clinical.read");
  let encounter: Encounter | null = null;
  let allergies: AllergySummary | undefined;
  if (canReadClinical) {
    [encounter, allergies] = await Promise.all([
      api<Encounter>(`/appointments/${appt.id}/encounter`).catch((e) => { if (e instanceof ApiError && e.status === 404) return null; throw e; }),
      api<AllergySummary>(`/patients/${appt.patient.id}/allergies`),
    ]);
  }
  const canInvoice = inBranch("billing.manage") && ["checked_in", "waiting", "in_consultation", "completed"].includes(appt.status);
  const canStart = canComplete && ["checked_in", "waiting", "in_consultation"].includes(appt.status) && !encounter;
  const started = new Date(appt.start_at).getTime() <= Date.now();
  const nextStatuses = NEXT_STATUSES[appt.status].filter((s) => (s !== "completed" || canComplete) && (s !== "no_show" || started));
  const override = appt.events.find((e) => e.details.override)?.details.override as { violations: string[]; reason: string } | undefined;

  return (
    <>
      <PatientIdentityBanner patient={{ name: appt.patient.name, patient_number: appt.patient.patient_number, date_of_birth: appt.patient.date_of_birth }} allergies={allergies} />
      <PageHeader
        title={`${appt.appointment_type.name} with ${appt.provider.name}`}
        description={`${longDate(dateOf(appt.start_at))}, ${timeOf(appt.start_at)}–${timeOf(appt.end_at)} · ${appt.branch.name}`}
        back={{ href: `/today?branch=${appt.branch.id}`, label: "Today" }}
      />
      <div className="flex max-w-4xl flex-col gap-4">
        {booked && <Notice tone="success">Booked. Reference <span className="font-mono">{appt.reference}</span>.</Notice>}
        {override && (
          <Notice tone="error">
            Booked as an override ({override.violations.map((v) => VIOLATION_LABEL[v] ?? v).join("; ")}). Reason: “{override.reason}”.
          </Notice>
        )}
        <Panel>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <AppointmentStatus status={appt.status} className="text-base" />
            {encounter && (
              <Link href={`/consultations/${encounter.id}`} className="inline-flex h-7 items-center rounded bg-primary px-2.5 text-sm font-medium text-white hover:bg-primary-hover">
                {encounter.status === "open" ? "Open consultation" : "View consultation"}
              </Link>
            )}
            {canInvoice && (
              <form action={invoiceForAppointment.bind(null, appt.patient.id, appt.id)}>
                <Button type="submit" size="sm" variant="secondary">Invoice</Button>
              </form>
            )}
            {canStart && (
              <form action={startConsultation.bind(null, appt.patient.id, appt.id)}>
                <Button type="submit" size="sm">Start consultation</Button>
              </form>
            )}
            {canManage && nextStatuses.filter((s) => !(s === "in_consultation" && canStart)).map((s) => (
              <form key={s} action={setAppointmentStatus.bind(null, appt.id, s, undefined)}>
                <Button type="submit" size="sm" variant={s === "no_show" ? "secondary" : "primary"}>{ACTION_LABEL[s]}</Button>
              </form>
            ))}
          </div>
          <Details items={[
            { label: "Reference", value: appt.reference, mono: true },
            { label: "Patient", value: <Link className="text-primary hover:underline" href={`/patients/${appt.patient.id}`}>{appt.patient.name}</Link> },
            { label: "Booked via", value: SOURCE[appt.booking_source] ?? appt.booking_source },
            { label: "Note for reception", value: appt.booking_note },
            ...(appt.cancellation_reason ? [{ label: "Cancellation reason", value: appt.cancellation_reason }] : []),
          ]} />
        </Panel>

        {canManage && (RESCHEDULABLE.includes(appt.status) || CANCELLABLE.includes(appt.status)) && (
          <Panel title="Change this appointment">
            <div className="flex flex-col items-start gap-4">
              {RESCHEDULABLE.includes(appt.status) && (
                <RescheduleForm
                  action={rescheduleAppointment.bind(null, appt.id)}
                  providerId={appt.provider.id}
                  branchId={appt.branch.id}
                  typeId={appt.appointment_type.id}
                  initialDate={dateOf(appt.start_at)}
                  today={todayISO()}
                  canOverride={inBranch("appointments.override")}
                />
              )}
              {CANCELLABLE.includes(appt.status) && (
                <CancelForm action={cancelAppointment.bind(null, appt.id)} label={`Cancel ${appt.patient.name}’s appointment`} />
              )}
            </div>
          </Panel>
        )}

        <Panel title="Messages to the patient" description="Only the practice, branch, date, time and reference are ever included.">
          {messages.items.length ? (
            <MessagesTable items={messages.items} canRetry={canManage} returnTo={`/appointments/${appt.id}`} />
          ) : (
            <p className="text-text-muted">No messages for this appointment.</p>
          )}
        </Panel>

        <Panel title="History">
          <ol className="flex flex-col gap-2">
            {appt.events.map((e) => (
              <li key={e.id} className="grid grid-cols-[150px_1fr] gap-3 text-base">
                <span className="tabular text-text-muted">{formatDateTime(e.created_at)}</span>
                <span>
                  {describe(e)}
                  {e.actor_user_id === me.id && <span className="text-text-muted"> · by you</span>}
                  {e.reason && <span className="text-text-muted"> · “{e.reason}”</span>}
                </span>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </>
  );
}
