import "server-only";

import type { Access, Branch } from "@/types/api";

/** Branches the user may work with for a permission, and the default selection. */
export function branchesFor(access: Access, permission: string, branches: Branch[], requested?: string) {
  const orgWide = access.grants.some((g) => g.permission === permission && g.branch_id === null);
  const allowed = orgWide
    ? branches
    : branches.filter((b) => access.grants.some((g) => g.permission === permission && g.branch_id === b.id));
  const selected = allowed.find((b) => b.id === requested) ?? allowed[0] ?? null;
  return { allowed, selected };
}
