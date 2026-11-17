import type { Metadata } from "next";
import Link from "next/link";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { Button, ButtonLink } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { EmptyState, PageHeader } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { setAppointmentStatus } from "@/features/appointments/actions";
import { branchesFor } from "@/features/appointments/branch-choice";
import { ACTION_LABEL, NEXT_STATUSES, STATUS_LABEL } from "@/lib/appointments";
import { api } from "@/lib/api";
import { hasPermission, requirePermission } from "@/lib/session";
import { dayRange, longDate, timeOf, todayISO } from "@/lib/time";
import type { Appointment, AppointmentStatus as S, Branch, Page } from "@/types/api";

export const metadata: Metadata = { title: "Today" };

// Quick actions offered inline; completing is done from the appointment by the clinician.
const QUICK: S[] = ["checked_in", "waiting", "in_consultation"];

export default async function TodayPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  const { access } = await requirePermission("appointments.read");
  const { branch: requested } = await searchParams;
  const branches = await api<Page<Branch>>("/branches", { query: { limit: 200 } });
  const { allowed, selected } = branchesFor(access, "appointments.read", branches.items, requested);
  const today = todayISO();
  const { from, to } = dayRange(today);
  const page = selected
    ? await api<Page<Appointment>>("/appointments", { query: { from, to, branch_id: selected.id, limit: 200 } })
    : null;
  const items = page?.items ?? [];
  const count = (...s: S[]) => items.filter((a) => s.includes(a.status)).length;
  const canManage = hasPermission(access, "appointments.manage");
  const here = `/today?branch=${selected?.id ?? ""}`;

  const summary: [string, number][] = [
    ["booked", items.filter((a) => a.status !== "cancelled").length],
    ["still expected", count("requested", "pending_confirmation", "confirmed")],
    ["checked in or waiting", count("checked_in", "waiting")],
    ["in consultation", count("in_consultation")],
    ["completed", count("completed")],
    ["no-show", count("no_show")],
  ];

  return (
    <>
      <PageHeader
        title="Today"
        description={longDate(today)}
        actions={canManage && selected && (
          <>
            <ButtonLink variant="secondary" href={`/calendar?branch=${selected.id}`}>Calendar</ButtonLink>
            <ButtonLink href={`/appointments/new?branch=${selected.id}`}>Book appointment</ButtonLink>
          </>
        )}
      />
      {allowed.length > 1 && (
        <form className="mb-3 flex items-center gap-2">
          <label htmlFor="branch" className="text-sm text-text-muted">Branch</label>
          <Select id="branch" name="branch" defaultValue={selected?.id} className="w-56">
            {allowed.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
          <button type="submit" className="h-9 rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted">Show</button>
        </form>
      )}
      <p className="mb-3 text-base text-text-muted tabular" aria-live="polite">
        {summary.map(([label, n], i) => (
          <span key={label}>{i > 0 && " · "}<span className="font-medium text-text">{n}</span> {label}</span>
        ))}
      </p>
      {items.length === 0 ? (
        <EmptyState message="No appointments today at this branch." action={canManage && selected && <ButtonLink variant="secondary" href={`/appointments/new?branch=${selected.id}`}>Book appointment</ButtonLink>} />
      ) : (
        <Table>
          <THead>
            <tr><TH>Time</TH><TH>Patient</TH><TH>Practitioner</TH><TH>Type</TH><TH>Status</TH>{canManage && <TH align="right">Next step</TH>}</tr>
          </THead>
          <tbody>
            {items.map((a) => {
              const next = NEXT_STATUSES[a.status].filter((s) => QUICK.includes(s));
              return (
                <TR key={a.id} className={a.status === "cancelled" ? "text-text-muted" : undefined}>
                  <TD mono className="whitespace-nowrap">
                    <Link href={`/appointments/${a.id}`} className="text-primary hover:underline">{timeOf(a.start_at)}–{timeOf(a.end_at)}</Link>
                  </TD>
                  <TD>
                    <Link href={`/patients/${a.patient.id}`} className="font-medium hover:underline">{a.patient.name}</Link>{" "}
                    <span className="font-mono text-sm text-text-muted">{a.patient.patient_number}</span>
                  </TD>
                  <TD>{a.provider.name}</TD>
                  <TD>{a.appointment_type.name}</TD>
                  <TD><AppointmentStatus status={a.status} /></TD>
                  {canManage && (
                    <TD align="right">
                      {next.map((s) => (
                        <form key={s} action={setAppointmentStatus.bind(null, a.id, s, here)} className="inline">
                          <Button type="submit" size="sm" variant="secondary" aria-label={`${ACTION_LABEL[s]}: ${a.patient.name}, ${timeOf(a.start_at)}`}>{ACTION_LABEL[s]}</Button>
                        </form>
                      ))}
                      {next.length === 0 && <span className="text-sm text-text-muted">{a.status === "in_consultation" ? "With practitioner" : STATUS_LABEL[a.status] === "Completed" ? "Done" : ""}</span>}
                    </TD>
                  )}
                </TR>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}
