import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/layout";
import { Tag } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Role } from "@/types/api";

export const metadata: Metadata = { title: "Roles" };

export default async function RolesPage() {
  const { access } = await requirePermission("roles.read");
  const roles = await api<Role[]>("/roles");
  return (
    <>
      <PageHeader
        title="Roles"
        description="What each role can do. Assign roles to staff organisation-wide or per branch."
        actions={hasOrgWide(access, "roles.manage") && <ButtonLink href="/roles/new">New role</ButtonLink>}
      />
      <Table>
        <THead>
          <tr>
            <TH>Role</TH>
            <TH>Description</TH>
            <TH align="right">Permissions</TH>
            <TH align="right">Assignments</TH>
          </tr>
        </THead>
        <tbody>
          {roles.map((r) => (
            <TR key={r.id}>
              <TD>
                <span className="flex items-center gap-2">
                  <Link href={`/roles/${r.id}`} className="font-medium text-primary hover:underline">
                    {r.name}
                  </Link>
                  {r.is_system && <Tag>System</Tag>}
                </span>
              </TD>
              <TD className="text-text-muted">{r.description ?? "—"}</TD>
              <TD align="right" mono>{r.permissions.length}</TD>
              <TD align="right" mono>{r.assignment_count}</TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </>
  );
}
