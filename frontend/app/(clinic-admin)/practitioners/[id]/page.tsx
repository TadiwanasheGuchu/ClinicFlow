import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Details, EmptyState, Notice, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { addLeave, removeLeave, saveAvailability, updateProvider } from "@/features/scheduling/actions";
import { AvailabilityEditor, LeaveForm, ProviderSettingsForm } from "@/features/scheduling/forms";
import { PROFESSIONS } from "@/lib/appointments";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { hasOrgWide, requirePermission } from "@/lib/session";
import { todayISO, WEEKDAYS } from "@/lib/time";
import type { AvailabilityWindow, Branch, Page, Provider, Unavailability } from "@/types/api";

export const metadata: Metadata = { title: "Practitioner" };

export default async function PractitionerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("appointments.read");
  let provider: Provider;
  try {
    provider = await api<Provider>(`/providers/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const [windows, leave, branches] = await Promise.all([
    api<AvailabilityWindow[]>(`/providers/${provider.id}/availability`),
    api<Unavailability[]>(`/providers/${provider.id}/unavailability`),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
  ]);
  const canManage = hasOrgWide(access, "scheduling.manage");
  const branchOptions = branches.items.map((b) => ({ id: b.id, name: b.name }));
  const branchName = new Map(branchOptions.map((b) => [b.id, b.name]));

  return (
    <>
      <PageHeader title={provider.display_name} back={{ href: "/practitioners", label: "Practitioners" }} />
      <div className="flex max-w-4xl flex-col gap-4">
        {!provider.credentials_current && (
          <Notice tone="error">
            Can’t be booked: professional registration is not verified or the licence has expired.{" "}
            <Link className="underline" href={`/staff/${provider.membership_id}`}>Review registration</Link>
          </Notice>
        )}
        <Panel>
          <Details items={[
            { label: "Profession", value: PROFESSIONS[provider.profession] ?? provider.profession },
            { label: "Specialty", value: provider.specialty },
            { label: "Staff record", value: <Link className="text-primary hover:underline" href={`/staff/${provider.membership_id}`}>View staff page</Link> },
          ]} />
          {canManage && <div className="mt-4 border-t border-border pt-4"><ProviderSettingsForm action={updateProvider.bind(null, provider.id)} provider={provider} /></div>}
        </Panel>

        <Panel title="Working hours" description="Recurring weekly hours, in Namibian time. Bookings are offered only inside these hours.">
          {canManage ? (
            <AvailabilityEditor action={saveAvailability.bind(null, provider.id)} windows={windows} branches={branchOptions} />
          ) : windows.length ? (
            <ul className="text-base">
              {windows.map((w) => <li key={w.id}>{WEEKDAYS[w.weekday]} {w.start_time.slice(0, 5)}–{w.end_time.slice(0, 5)} · {branchName.get(w.branch_id)}</li>)}
            </ul>
          ) : (
            <p className="text-text-muted">No working hours set.</p>
          )}
        </Panel>

        <Panel title="Leave and blocked time" description="Blocking time does not cancel existing bookings in that period.">
          {leave.length === 0 ? (
            <EmptyState message="No upcoming blocked time." />
          ) : (
            <Table>
              <THead><tr><TH>From</TH><TH>Until</TH><TH>Reason</TH>{canManage && <TH align="right">Actions</TH>}</tr></THead>
              <tbody>
                {leave.map((l) => (
                  <TR key={l.id}>
                    <TD className="tabular">{formatDateTime(l.start_at)}</TD>
                    <TD className="tabular">{formatDateTime(l.end_at)}</TD>
                    <TD>{l.reason ?? "—"}</TD>
                    {canManage && (
                      <TD align="right">
                        <form action={removeLeave.bind(null, provider.id, l.id)}>
                          <Button type="submit" size="sm" variant="secondary">Remove</Button>
                        </form>
                      </TD>
                    )}
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
          {canManage && <div className="mt-4"><LeaveForm action={addLeave.bind(null, provider.id)} today={todayISO()} /></div>}
        </Panel>
      </div>
    </>
  );
}
