import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { updateContact } from "@/features/portal/actions";
import { ContactForm } from "@/features/portal/forms";
import { formatDate } from "@/lib/format";
import { portalInfo, portalMe } from "@/lib/portal";

export default async function PortalProfilePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!(await portalInfo(slug))) notFound();
  const me = await portalMe(slug);
  if (!me) redirect(`/signin?callbackUrl=/book/${slug}/profile`);
  if (!me.patient) redirect(`/book/${slug}`);
  return (
    <div className="flex flex-col gap-4">
      <Link href={`/book/${slug}`} className="text-base text-primary">‹ My appointments</Link>
      <h1 className="text-xl">My details</h1>
      <p className="text-base text-text-muted">
        {me.patient.first_name} {me.patient.last_name} · born {formatDate(me.patient.date_of_birth)} · <span className="font-mono">{me.patient.patient_number}</span>
      </p>
      <ContactForm action={updateContact.bind(null, slug)} patient={me.patient} />
    </div>
  );
}
