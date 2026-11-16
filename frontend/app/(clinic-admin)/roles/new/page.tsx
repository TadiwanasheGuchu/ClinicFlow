import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHeader, Panel } from "@/components/ui/layout";
import { createRole } from "@/features/roles/actions";
import { RoleForm } from "@/features/roles/role-form";
import { api } from "@/lib/api";
import { hasOrgWide, requireWorkspace } from "@/lib/session";
import type { Permission } from "@/types/api";

export const metadata: Metadata = { title: "New role" };

export default async function NewRolePage() {
  const { access } = await requireWorkspace();
  if (!hasOrgWide(access, "roles.manage")) redirect("/not-permitted");
  const permissions = await api<Permission[]>("/permissions");
  return (
    <>
      <PageHeader title="New role" back={{ href: "/roles", label: "Roles" }} />
      <Panel>
        <RoleForm action={createRole} permissions={permissions} />
      </Panel>
    </>
  );
}
