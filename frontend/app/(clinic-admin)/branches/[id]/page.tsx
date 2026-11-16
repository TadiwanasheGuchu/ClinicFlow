import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Details, PageHeader, Panel } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { setBranchActive, updateBranch } from "@/features/branches/actions";
import { BranchForm } from "@/features/branches/branch-form";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { Branch } from "@/types/api";

export const metadata: Metadata = { title: "Branch" };

async function loadBranch(id: string) {
  try {
    return await api<Branch>(`/branches/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
}

export default async function BranchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("branches.read");
  const branch = await loadBranch(id);
  const canManage = access.grants.some(
    (g) => g.permission === "branches.manage" && (g.branch_id === null || g.branch_id === branch.id),
  );

  return (
    <>
      <PageHeader
        title={branch.name}
        back={{ href: "/branches", label: "Branches" }}
        actions={
          canManage && (
            <form action={setBranchActive.bind(null, branch.id, !branch.is_active)}>
              <Button type="submit" variant="secondary">
                {branch.is_active ? `Deactivate ${branch.name}` : `Reactivate ${branch.name}`}
              </Button>
            </form>
          )
        }
      />
      <div className="mb-4 flex items-center gap-4 text-sm text-text-muted">
        <Status status={branch.is_active ? "active" : "inactive"} />
        <span>
          Code <span className="font-mono text-text">{branch.branch_code}</span>
        </span>
        <span>Created {formatDate(branch.created_at)}</span>
      </div>
      <Panel>
        {canManage ? (
          <BranchForm action={updateBranch.bind(null, branch.id)} branch={branch} />
        ) : (
          <Details
            items={[
              { label: "Phone", value: branch.phone },
              { label: "Email", value: branch.email },
              { label: "Address", value: branch.address },
            ]}
          />
        )}
      </Panel>
    </>
  );
}
