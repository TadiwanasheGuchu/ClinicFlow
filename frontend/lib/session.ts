import "server-only";

import { redirect } from "next/navigation";

import { api, getActiveOrgId } from "@/lib/api";
import type { Access, Me } from "@/types/api";

export type Workspace = { me: Me; orgId: string; orgName: string; access: Access };

/** UI gating only — the API enforces every permission independently. */
export const hasPermission = (access: Access, permission: string) =>
  access.permissions.includes(permission);

/** Org-wide grant, which some actions (creating branches, managing staff) require. */
export const hasOrgWide = (access: Access, permission: string) =>
  access.grants.some((g) => g.permission === permission && g.branch_id === null);

/** Resolve the signed-in user's active organisation, or send them to onboarding. */
export async function requireWorkspace(): Promise<Workspace> {
  const me = await api<Me>("/me", { tenant: false });
  const active = me.memberships.filter(
    (m) => m.status === "active" && m.organisation_status === "active",
  );
  const selected = await getActiveOrgId();
  const current = active.find((m) => m.organisation_id === selected);
  if (!current) {
    // No valid selection (first visit, or access removed).
    redirect(active.length ? `/switch?to=${active[0]!.organisation_id}` : "/onboarding");
  }
  const access = await api<Access>("/me/access");
  return { me, orgId: current.organisation_id, orgName: current.organisation_name, access };
}

/** Guard a page by permission. */
export async function requirePermission(permission: string): Promise<Workspace> {
  const workspace = await requireWorkspace();
  if (!hasPermission(workspace.access, permission)) redirect("/not-permitted");
  return workspace;
}
