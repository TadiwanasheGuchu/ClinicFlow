import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { ButtonLink } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { EmptyState, PageHeader } from "@/components/ui/layout";
import { branchesFor } from "@/features/appointments/branch-choice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { hasPermission, requirePermission } from "@/lib/session";
import { addDays, dayRange, isISODate, longDate, minutesOfDay, timeOf, todayISO } from "@/lib/time";
import type { Appointment, AvailabilityWindow, Branch, Page, Provider } from "@/types/api";

export const metadata: Metadata = { title: "Calendar" };

const PX_PER_MIN = 1.6; // 15 minutes = 24px
const toMin = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));

export default async function CalendarPage({ searchParams }: { searchParams: Promise<{ date?: string; branch?: string }> }) {
  const { access } = await requirePermission("appointments.read");
  const params = await searchParams;
  const date = isISODate(params.date) ? params.date : todayISO();
  const branches = await api<Page<Branch>>("/branches", { query: { limit: 200 } });
  const { allowed, selected } = branchesFor(access, "appointments.read", branches.items, params.branch);
  if (!selected) return <EmptyState message="No branch available." />;

  const { from, to } = dayRange(date);
  const [providers, appointments] = await Promise.all([
    api<Provider[]>("/providers", { query: { branch_id: selected.id } }),
    api<Page<Appointment>>("/appointments", { query: { from, to, branch_id: selected.id, limit: 200 } }),
  ]);
  const weekday = (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
  const availability = new Map(
    await Promise.all(
      providers.map(async (p) => [p.id, (await api<AvailabilityWindow[]>(`/providers/${p.id}/availability`)).filter((w) => w.branch_id === selected.id && w.weekday === weekday)] as const),
    ),
  );
  const visible = appointments.items.filter((a) => a.status !== "cancelled");
  const allMinutes = [
    ...[...availability.values()].flat().flatMap((w) => [toMin(w.start_time), toMin(w.end_time)]),
    ...visible.flatMap((a) => [minutesOfDay(a.start_at), minutesOfDay(a.end_at)]),
  ];
  const dayStart = Math.min(7 * 60, ...allMinutes.map((m) => Math.floor(m / 60) * 60));
  const dayEnd = Math.max(18 * 60, ...allMinutes.map((m) => Math.ceil(m / 60) * 60));
  const hours = Array.from({ length: (dayEnd - dayStart) / 60 }, (_, i) => dayStart + i * 60);
  const height = (dayEnd - dayStart) * PX_PER_MIN;
  const canBook = hasPermission(access, "appointments.manage");
  const link = (d: string) => `/calendar?date=${d}&branch=${selected.id}`;

  return (
    <>
      <PageHeader
        title="Calendar"
        description={`${longDate(date)} · ${selected.name}`}
        actions={canBook && <ButtonLink href={`/appointments/new?branch=${selected.id}&date=${date}`}>Book appointment</ButtonLink>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Link href={link(addDays(date, -1))} className="inline-flex h-9 items-center gap-1 rounded border border-border bg-surface px-2.5 hover:bg-surface-muted"><ChevronLeft size={16} strokeWidth={1.5} aria-hidden />Previous day</Link>
        <Link href={link(todayISO())} className="inline-flex h-9 items-center rounded border border-border bg-surface px-3 hover:bg-surface-muted">Today</Link>
        <Link href={link(addDays(date, 1))} className="inline-flex h-9 items-center gap-1 rounded border border-border bg-surface px-2.5 hover:bg-surface-muted">Next day<ChevronRight size={16} strokeWidth={1.5} aria-hidden /></Link>
        <form className="ml-auto flex items-center gap-2">
          <input type="date" name="date" defaultValue={date} aria-label="Go to date" className="h-9 rounded-sm border border-border bg-surface px-2" />
          {allowed.length > 1 ? (
            <Select name="branch" defaultValue={selected.id} aria-label="Branch" className="w-48">{allowed.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
          ) : <input type="hidden" name="branch" value={selected.id} />}
          <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Go</button>
        </form>
      </div>

      {providers.length === 0 ? (
        <EmptyState message="No practitioners work at this branch yet." />
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-surface">
          <div className="grid min-w-max" style={{ gridTemplateColumns: `56px repeat(${providers.length}, minmax(180px, 1fr))` }}>
            <div className="sticky top-0 z-10 border-b border-border bg-surface-muted" />
            {providers.map((p) => (
              <div key={p.id} className="sticky top-0 z-10 border-b border-l border-border bg-surface-muted px-2 py-2 text-sm font-medium">
                {p.display_name}
                {!p.credentials_current && <span className="block text-xs font-normal text-danger-text">Not bookable</span>}
              </div>
            ))}
            <div className="relative" style={{ height }}>
              {hours.map((h) => (
                <span key={h} className="absolute right-2 -translate-y-1/2 font-mono text-xs text-text-muted" style={{ top: (h - dayStart) * PX_PER_MIN }}>
                  {h > dayStart && `${String(h / 60).padStart(2, "0")}:00`}
                </span>
              ))}
            </div>
            {providers.map((p) => (
              <div key={p.id} className="relative border-l border-border bg-surface-muted" style={{ height }}>
                {(availability.get(p.id) ?? []).map((w) => (
                  <div key={w.id} className="absolute inset-x-0 bg-surface" style={{ top: (toMin(w.start_time) - dayStart) * PX_PER_MIN, height: (toMin(w.end_time) - toMin(w.start_time)) * PX_PER_MIN }} />
                ))}
                {hours.map((h) => <div key={h} className="absolute inset-x-0 border-t border-border" style={{ top: (h - dayStart) * PX_PER_MIN }} />)}
                {visible.filter((a) => a.provider.id === p.id).map((a) => {
                  const top = (minutesOfDay(a.start_at) - dayStart) * PX_PER_MIN;
                  const h = Math.max(22, (minutesOfDay(a.end_at) - minutesOfDay(a.start_at)) * PX_PER_MIN - 2);
                  return (
                    <Link
                      key={a.id}
                      href={`/appointments/${a.id}`}
                      className={cn(
                        "absolute inset-x-1 overflow-hidden rounded-sm border-l-[3px] bg-primary-subtle px-1.5 py-0.5 text-xs leading-tight hover:outline hover:outline-1 hover:outline-primary",
                        a.status === "no_show" ? "border-danger bg-danger-subtle" : a.status === "completed" ? "border-success bg-success-subtle" : "border-primary",
                      )}
                      style={{ top, height: h }}
                      title={`${timeOf(a.start_at)} ${a.patient.name} — ${a.appointment_type.name}`}
                    >
                      <span className="font-mono">{timeOf(a.start_at)}</span> <span className="font-medium">{a.patient.name}</span>
                      {h > 34 && <span className="block truncate text-text-muted">{a.appointment_type.name}</span>}
                      {h > 50 && <AppointmentStatus status={a.status} className="text-xs" />}
                    </Link>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="mt-2 text-xs text-text-muted">White areas are working hours. Cancelled appointments are hidden.</p>
    </>
  );
}
