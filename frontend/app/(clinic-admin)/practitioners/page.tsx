import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader, Panel, EmptyState } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { createProvider } from "@/features/scheduling/actions";
import { AddProviderForm } from "@/features/scheduling/forms";
import { PROFESSIONS } from "@/lib/appointments";
import { api } from "@/lib/api";
import { hasOrgWide, hasPermission, requirePermission } from "@/lib/session";
import type { Branch, Member, Page, Provider } from "@/types/api";

export const metadata: Metadata = { title: "Practitioners" };

export default async function PractitionersPage() {
  const { access } = await requirePermission("appointments.read");
  const [providers, branches] = await Promise.all([
    api<Provider[]>("/providers"),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
  ]);
  const branchName = new Map(branches.items.map((b) => [b.id, b.name]));
  const canManage = hasOrgWide(access, "scheduling.manage");
  const candidates =
    canManage && hasPermission(access, "members.read")
      ? (await api<Page<Member>>("/members", { query: { status: "active", limit: 200 } })).items
          .filter((m) => !providers.some((p) => p.membership_id === m.id))
          .map((m) => ({ id: m.id, name: m.full_name }))
      : [];

  return (
    <>
      <PageHeader title="Practitioners" description="Who can be booked, where and when." />
      <div className="flex flex-col gap-5">
        {providers.length === 0 ? (
          <EmptyState message="No practitioners yet. Verify a clinician’s registration on their staff page, then add them here." />
        ) : (
          <Table>
            <THead>
              <tr><TH>Practitioner</TH><TH>Profession</TH><TH>Branches</TH><TH>Registration</TH><TH>Bookings</TH></tr>
            </THead>
            <tbody>
              {providers.map((p) => (
                <TR key={p.id}>
                  <TD><Link href={`/practitioners/${p.id}`} className="font-medium text-primary hover:underline">{p.display_name}</Link></TD>
                  <TD>{PROFESSIONS[p.profession] ?? p.profession}{p.specialty && <span className="text-text-muted"> · {p.specialty}</span>}</TD>
                  <TD className="text-text-muted">{p.branch_ids.map((id) => branchName.get(id)).filter(Boolean).join(", ") || "No working hours set"}</TD>
                  <TD>{p.credentials_current ? <Status status="active" /> : <span className="text-sm font-medium text-danger-text">Not verified or expired</span>}</TD>
                  <TD>{p.booking_enabled && p.credentials_current ? "Accepting" : <span className="text-text-muted">Not accepting</span>}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        {canManage && (
          <Panel title="Add practitioner" description="Only staff whose professional registration is verified and current can be booked.">
            <AddProviderForm action={createProvider} members={candidates} />
          </Panel>
        )}
      </div>
    </>
  );
}
