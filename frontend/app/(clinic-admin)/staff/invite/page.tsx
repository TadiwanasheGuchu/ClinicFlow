import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHeader, Panel } from "@/components/ui/layout";
import { inviteMember } from "@/features/staff/actions";
import { InviteForm } from "@/features/staff/forms";
import { assignmentOptions } from "@/features/staff/options";
import { hasOrgWide, requireWorkspace } from "@/lib/session";

export const metadata: Metadata = { title: "Invite staff" };

export default async function InvitePage() {
  const { access } = await requireWorkspace();
  if (!hasOrgWide(access, "members.manage")) redirect("/not-permitted");
  const { roles, branches } = await assignmentOptions();
  return (
    <>
      <PageHeader
        title="Invite staff"
        description="They’ll see the invitation after signing in with this email address."
        back={{ href: "/staff", label: "Staff" }}
      />
      <Panel>
        <InviteForm action={inviteMember} roles={roles} branches={branches} />
      </Panel>
    </>
  );
}
