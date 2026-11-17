import Link from "next/link";
import { notFound } from "next/navigation";

import { AppointmentStatus } from "@/components/ui/appointment-status";
import { ButtonLink } from "@/components/ui/button";
import { linkAccount, registerSelf } from "@/features/portal/actions";
import { LinkForm, RegisterSelfForm } from "@/features/portal/forms";
import { SignInButton } from "@/app/(public)/signin/sign-in-button";
import { type PortalAppointment, portalApi, portalInfo, portalMe } from "@/lib/portal";
import { dateOf, longDate, timeOf, WEEKDAYS } from "@/lib/time";
import type { AppointmentStatus as S } from "@/types/api";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function AppointmentCard({ a, slug }: { a: PortalAppointment; slug: string }) {
  return (
    <li>
      <Link href={`/book/${slug}/appointments/${a.id}`} className="block rounded border border-border bg-surface p-4 hover:border-primary">
        <p className="text-md font-semibold">{longDate(dateOf(a.start_at))}, {timeOf(a.start_at)}</p>
        <p className="text-base text-text-muted">{a.provider_name} · {a.branch_name}</p>
        <p className="mt-1"><AppointmentStatus status={a.status as S} /></p>
      </Link>
    </li>
  );
}

export default async function PortalHome({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const info = await portalInfo(slug);
  if (!info) notFound();
  const me = await portalMe(slug);

  if (!me) {
    return (
      <div className="flex flex-col gap-6">
        <section>
          <h1 className="text-xl">Book an appointment</h1>
          <p className="mt-1 text-text-muted">Sign in or create an account to see available times and manage your bookings.</p>
          <div className="mt-4"><SignInButton callbackUrl={`/book/${slug}`} /></div>
        </section>
        {info.branches.map((b) => (
          <section key={b.id} className="rounded border border-border bg-surface p-4">
            <h2 className="text-md font-semibold">{b.name}</h2>
            {b.address && <p className="text-text-muted">{b.address}</p>}
            {b.phone && <p><a className="text-primary underline" href={`tel:${b.phone.replace(/\s/g, "")}`}>{b.phone}</a></p>}
            <table className="mt-3 text-base">
              <tbody>
                {DAYS.map((d, i) => {
                  const hours = b.operating_hours[d];
                  return (
                    <tr key={d}><th scope="row" className="pr-4 text-left font-normal text-text-muted">{WEEKDAYS[i]}</th>
                      <td className="font-mono text-sm">{hours?.length ? hours.map((h) => `${h.open}–${h.close}`).join(", ") : "Closed"}</td></tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    );
  }

  if (!me.linked) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl">Welcome to {info.name}</h1>
          <p className="mt-1 text-text-muted">Signed in as {me.email}. Before booking, connect your account to your patient record.</p>
        </div>
        <section className="rounded border border-border bg-surface p-4">
          <h2 className="mb-1 text-lg">I’m new to this practice</h2>
          <p className="mb-4 text-base text-text-muted">We’ll create your patient record.</p>
          <RegisterSelfForm action={registerSelf.bind(null, slug)} />
        </section>
        <section className="rounded border border-border bg-surface p-4">
          <h2 className="mb-1 text-lg">I’ve been to this practice before</h2>
          <p className="mb-4 text-base text-text-muted">Ask reception for a link code, then enter it here with your date of birth.</p>
          <LinkForm action={linkAccount.bind(null, slug)} />
        </section>
      </div>
    );
  }

  const all = await portalApi<PortalAppointment[]>(slug, "/appointments");
  const now = Date.now();
  const upcoming = all.filter((a) => new Date(a.end_at).getTime() >= now && a.status !== "cancelled").sort((a, b) => a.start_at.localeCompare(b.start_at));
  const past = all.filter((a) => !upcoming.includes(a)).slice(0, 10);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl">{me.patient?.first_name} {me.patient?.last_name}</h1>
          <p className="font-mono text-sm text-text-muted">{me.patient?.patient_number}</p>
        </div>
        <Link href={`/book/${slug}/profile`} className="text-base text-primary underline">My details</Link>
      </div>
      <ButtonLink href={`/book/${slug}/new`} className="h-11 w-full text-md">Book an appointment</ButtonLink>
      <section>
        <h2 className="mb-2 text-lg">Upcoming</h2>
        {upcoming.length ? <ul className="flex flex-col gap-2">{upcoming.map((a) => <AppointmentCard key={a.id} a={a} slug={slug} />)}</ul> : <p className="text-text-muted">No upcoming appointments.</p>}
      </section>
      {past.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg">Past and cancelled</h2>
          <ul className="flex flex-col gap-2">{past.map((a) => <AppointmentCard key={a.id} a={a} slug={slug} />)}</ul>
        </section>
      )}
    </div>
  );
}
