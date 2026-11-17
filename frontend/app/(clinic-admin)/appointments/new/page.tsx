import type { Metadata } from "next";

import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { ButtonLink } from "@/components/ui/button";
import { BookingForm } from "@/features/appointments/booking-form";
import { branchesFor } from "@/features/appointments/branch-choice";
import { api, ApiError } from "@/lib/api";
import { hasOrgWide, requirePermission } from "@/lib/session";
import { isISODate, todayISO } from "@/lib/time";
import type { AppointmentType, Branch, Page, Patient, PatientSummary, Provider } from "@/types/api";

export const metadata: Metadata = { title: "Book appointment" };

export default async function NewAppointmentPage({
  searchParams,
}: {
  searchParams: Promise<{ patient?: string; provider?: string; branch?: string; date?: string }>;
}) {
  const { access } = await requirePermission("appointments.manage");
  const params = await searchParams;
  const [providers, branches, types] = await Promise.all([
    api<Provider[]>("/providers", { query: { bookable_only: true } }),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
    api<AppointmentType[]>("/appointment-types"),
  ]);
  let patient: PatientSummary | null = null;
  if (params.patient) {
    try {
      patient = await api<Patient>(`/patients/${encodeURIComponent(params.patient)}`);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    }
  }
  const { allowed, selected } = branchesFor(access, "appointments.manage", branches.items, params.branch);
  const today = todayISO();
  const ready = selected && providers.length > 0 && types.length > 0;

  return (
    <>
      <PageHeader title="Book appointment" back={{ href: "/today", label: "Today" }} />
      {!ready ? (
        <EmptyState
          message={!types.length ? "Add an appointment type first." : "No practitioners can take bookings yet. Verify a clinician’s registration and set their working hours."}
          action={hasOrgWide(access, "scheduling.manage") && <ButtonLink href={!types.length ? "/appointment-types" : "/practitioners"} variant="secondary">Set up scheduling</ButtonLink>}
        />
      ) : (
        <Panel>
          <BookingForm
            patient={patient}
            providers={providers}
            branches={allowed.map((b) => ({ id: b.id, name: b.name }))}
            types={types}
            defaults={{
              branchId: selected.id,
              providerId: providers.find((p) => p.id === params.provider)?.id ?? "",
              date: isISODate(params.date) && params.date >= today ? params.date : today,
              today,
            }}
            canOverride={access.grants.some((g) => g.permission === "appointments.override")}
          />
        </Panel>
      )}
    </>
  );
}
