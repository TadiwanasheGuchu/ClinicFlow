import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { Notice } from "@/components/ui/layout";
import { cancelOnline, rescheduleOnline } from "@/features/portal/actions";
import { ChangeAppointment } from "@/features/portal/forms";
import { ApiError } from "@/lib/api";
import { type PortalAppointment, portalApi, portalInfo, portalMe } from "@/lib/portal";
import { addDays, dateOf, longDate, timeOf, todayISO } from "@/lib/time";
import type { AppointmentStatus as S } from "@/types/api";

export default async function PortalAppointmentPage({ params, searchParams }: { params: Promise<{ slug: string; id: string }>; searchParams: Promise<{ booked?: string }> }) {
  const { slug, id } = await params;
  const { booked } = await searchParams;
  const info = await portalInfo(slug);
  if (!info) notFound();
  const me = await portalMe(slug);
  if (!me) redirect(`/signin?callbackUrl=/book/${slug}`);
  let a: PortalAppointment;
  try {
    a = await portalApi<PortalAppointment>(slug, `/appointments/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
  const today = todayISO();

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/book/${slug}`} className="text-base text-primary">‹ My appointments</Link>
      {booked && (
        <Notice tone="success">
          {a.status === "requested" ? "Request sent. The practice will confirm it." : "You’re booked."} We’ll send a confirmation using your reminder preference.
        </Notice>
      )}
      <section className="rounded border border-border bg-surface p-4">
        <h1 className="text-xl">{longDate(dateOf(a.start_at))}</h1>
        <p className="text-lg">{timeOf(a.start_at)}–{timeOf(a.end_at)}</p>
        <p className="mt-2"><AppointmentStatus status={a.status as S} className="text-base" /></p>
        <dl className="mt-4 grid gap-2 text-base">
          <div><dt className="text-sm text-text-muted">With</dt><dd>{a.provider_name}</dd></div>
          <div><dt className="text-sm text-text-muted">Type</dt><dd>{a.appointment_type}</dd></div>
          <div><dt className="text-sm text-text-muted">Where</dt><dd>{a.branch_name}{a.branch_address && <span className="block text-text-muted">{a.branch_address}</span>}</dd></div>
          <div><dt className="text-sm text-text-muted">Reference</dt><dd className="font-mono">{a.reference}</dd></div>
        </dl>
      </section>
      {a.can_change ? (
        <ChangeAppointment
          reschedule={rescheduleOnline.bind(null, slug, a.id)}
          cancel={cancelOnline.bind(null, slug, a.id)}
          slug={slug}
          providerId={a.provider_id}
          branchId={a.branch_id}
          typeId={a.appointment_type_id}
          today={today}
          maxDate={addDays(today, info.policy.max_days_ahead)}
        />
      ) : ["confirmed", "requested", "pending_confirmation"].includes(a.status) ? (
        <p className="text-base text-text-muted">
          Online changes close {info.policy.cancel_cutoff_hours} hours before the appointment. To change it now, please call the practice{info.phone ? ` on ${info.phone}` : ""}.
        </p>
      ) : null}
    </div>
  );
}
