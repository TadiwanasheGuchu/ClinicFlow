import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Member, Page } from "@/types/api";

export const metadata: Metadata = { title: "Staff" };

export default async function StaffPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; q?: string; status?: string }>;
}) {
  const { access } = await requirePermission("members.read");
  const { offset: rawOffset, q = "", status = "" } = await searchParams;
  const offset = Number(rawOffset ?? 0) || 0;
  const validStatus = ["invited", "active", "suspended"].includes(status) ? status : undefined;
  const page = await api<Page<Member>>("/members", {
    query: { offset, limit: 50, q: q || undefined, status: validStatus },
  });
  const qs = (o: number) =>
    `/staff?${new URLSearchParams({ offset: String(o), ...(q && { q }), ...(validStatus && { status: validStatus }) })}`;

  return (
    <>
      <PageHeader
        title="Staff"
        description="People with access to this organisation and the roles they hold."
        actions={hasOrgWide(access, "members.manage") && <ButtonLink href="/staff/invite">Invite staff</ButtonLink>}
      />
      <form className="mb-3 flex flex-wrap gap-2" role="search">
        <label className="sr-only" htmlFor="q">Search by name or email</label>
        <Input id="q" name="q" defaultValue={q} placeholder="Search by name or email" className="w-72" />
        <label className="sr-only" htmlFor="status">Status</label>
        <Select id="status" name="status" defaultValue={validStatus ?? ""} className="w-40">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="invited">Invited</option>
          <option value="suspended">Suspended</option>
        </Select>
        <button type="submit" className="h-9 rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted">
          Filter
        </button>
      </form>
      {page.items.length === 0 ? (
        <EmptyState message={q || validStatus ? "No staff match these filters." : "No staff yet."} />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Email</TH>
              <TH>Roles</TH>
              <TH>Status</TH>
              <TH>Last sign-in</TH>
            </tr>
          </THead>
          <tbody>
            {page.items.map((m) => (
              <TR key={m.id}>
                <TD>
                  <Link href={`/staff/${m.id}`} className="font-medium text-primary hover:underline">
                    {m.full_name}
                  </Link>
                </TD>
                <TD className="text-text-muted">{m.email}</TD>
                <TD>
                  {m.roles.map((r) => (r.branch_name ? `${r.role_name} (${r.branch_name})` : r.role_name)).join(", ") || "—"}
                </TD>
                <TD>
                  <Status status={m.status} />
                </TD>
                <TD className="tabular text-text-muted">{formatDateTime(m.last_login_at)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={qs} />
    </>
  );
}
