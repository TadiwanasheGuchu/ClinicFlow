import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { bookOnline } from "@/features/portal/actions";
import { BookingWizard } from "@/features/portal/forms";
import { portalInfo, portalMe } from "@/lib/portal";
import { addDays, todayISO } from "@/lib/time";

export default async function PortalBookPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const info = await portalInfo(slug);
  if (!info) notFound();
  const me = await portalMe(slug);
  if (!me) redirect(`/signin?callbackUrl=/book/${slug}/new`);
  if (!me.linked) redirect(`/book/${slug}`);
  const today = todayISO();

  return (
    <div className="flex flex-col gap-4">
      <Link href={`/book/${slug}`} className="text-base text-primary">‹ My appointments</Link>
      <h1 className="text-xl">Book an appointment</h1>
      {info.providers.length === 0 || info.appointment_types.length === 0 ? (
        <p className="text-text-muted">Online booking isn’t available right now. Please call the practice.</p>
      ) : (
        <>
          <p className="text-base text-text-muted">
            Online bookings need at least {info.policy.min_notice_hours} hours’ notice and open {info.policy.max_days_ahead} days ahead.
            {!info.policy.auto_confirm && " The practice will confirm your request."}
          </p>
          <BookingWizard action={bookOnline.bind(null, slug)} info={info} slug={slug} today={today} maxDate={addDays(today, info.policy.max_days_ahead)} />
        </>
      )}
    </div>
  );
}
