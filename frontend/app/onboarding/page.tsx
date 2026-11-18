import type { Metadata } from "next";
import Link from "next/link";

import { Notice, Panel } from "@/components/ui/layout";
import { acceptInvitation } from "@/features/onboarding/actions";
import { RegisterOrganisationForm } from "@/features/onboarding/register-form";
import { api } from "@/lib/api";
import type { Me } from "@/types/api";

export const metadata: Metadata = { title: "Set up" };

export default async function OnboardingPage() {
  const me = await api<Me>("/me", { tenant: false });
  const invitations = me.memberships.filter((m) => m.status === "invited");
  const suspended = me.memberships.filter((m) => m.status === "suspended");
  const pending = me.memberships.filter((m) => m.status === "active" && m.organisation_status === "pending");

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-10">
      <div>
        <p className="font-mono text-sm text-primary">ClinicFlow</p>
        <h1 className="mt-2 text-xl text-text">Set up your access</h1>
        <p className="mt-1 text-base text-text-muted">
          Signed in as {me.email}. Accept an invitation from your practice, or register a new
          practice.
        </p>
      </div>

      {me.is_platform_admin && (
        <Notice>
          You are a platform administrator. <Link className="underline" href="/platform">Open platform administration</Link> to approve or suspend practices.
        </Notice>
      )}

      {invitations.length > 0 && (
        <Panel title="Invitations">
          <ul className="divide-y divide-border">
            {invitations.map((inv) => (
              <li key={inv.organisation_id} className="flex items-center justify-between py-2">
                <span className="text-base">{inv.organisation_name}</span>
                <form action={acceptInvitation.bind(null, inv.organisation_id)}>
                  <button
                    type="submit"
                    className="h-8 rounded bg-primary px-3 text-sm font-medium text-white hover:bg-primary-hover"
                  >
                    Accept invitation
                  </button>
                </form>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {suspended.length > 0 && (
        <p className="text-sm text-text-muted">
          Your access to {suspended.map((s) => s.organisation_name).join(", ")} is suspended.
          Contact that practice’s administrator.
        </p>
      )}

      {pending.length > 0 && (
        <Notice>
          {pending.map((p) => p.organisation_name).join(", ")} {pending.length === 1 ? "is" : "are"} waiting
          for approval by the ClinicFlow team. You’ll be able to sign in to it once it’s approved.
        </Notice>
      )}

      {pending.length === 0 && <Panel
        title="Register a practice"
        description="You’ll be the owner. You can add branches, staff and roles afterwards."
      >
        <RegisterOrganisationForm />
      </Panel>}
    </main>
  );
}
