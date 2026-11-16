import "server-only";

import { api } from "@/lib/api";
import type { Branch, Page, Role } from "@/types/api";

/** Roles and active branches for assignment pickers. */
export async function assignmentOptions() {
  const [roles, branches] = await Promise.all([
    api<Role[]>("/roles"),
    api<Page<Branch>>("/branches", { query: { limit: 200 } }),
  ]);
  return {
    roles: roles.map((r) => ({ id: r.id, name: r.name })),
    branches: branches.items.map((b) => ({ id: b.id, name: b.name })),
  };
}
