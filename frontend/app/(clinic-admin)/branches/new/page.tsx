import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHeader, Panel } from "@/components/ui/layout";
import { createBranch } from "@/features/branches/actions";
import { BranchForm } from "@/features/branches/branch-form";
import { hasOrgWide, requireWorkspace } from "@/lib/session";

export const metadata: Metadata = { title: "Add branch" };

export default async function NewBranchPage() {
  const { access } = await requireWorkspace();
  if (!hasOrgWide(access, "branches.manage")) redirect("/not-permitted");
  return (
    <>
      <PageHeader title="Add branch" back={{ href: "/branches", label: "Branches" }} />
      <Panel>
        <BranchForm action={createBranch} />
      </Panel>
    </>
  );
}
