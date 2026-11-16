import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { deleteRole, updateRole } from "@/features/roles/actions";
import { RoleForm } from "@/features/roles/role-form";
import { api, ApiError } from "@/lib/api";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Permission, Role } from "@/types/api";

export const metadata: Metadata = { title: "Role" };

export default async function RolePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("roles.read");
  let role: Role;
  let permissions: Permission[];
  try {
    [role, permissions] = await Promise.all([
      api<Role>(`/roles/${encodeURIComponent(id)}`),
      api<Permission[]>("/permissions"),
    ]);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const canManage = hasOrgWide(access, "roles.manage") && !role.is_system;
  const canDelete = canManage && role.assignment_count === 0;

  return (
    <>
      <PageHeader
        title={role.name}
        back={{ href: "/roles", label: "Roles" }}
        actions={
          canDelete && (
            <form action={deleteRole.bind(null, role.id)}>
              <Button type="submit" variant="secondary">
                Delete role “{role.name}”
              </Button>
            </form>
          )
        }
      />
      <div className="flex max-w-3xl flex-col gap-4">
        {role.is_system && (
          <Notice>The Owner role is a system role and can’t be changed or deleted.</Notice>
        )}
        {canManage && role.assignment_count > 0 && (
          <Notice>
            {role.assignment_count} staff assignment{role.assignment_count === 1 ? "" : "s"} use
            this role. Changes apply to all of them.
          </Notice>
        )}
        <Panel>
          <RoleForm
            action={updateRole.bind(null, role.id)}
            permissions={permissions}
            role={role}
            readOnly={!canManage}
          />
        </Panel>
      </div>
    </>
  );
}
