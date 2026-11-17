import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Details, Notice, PageHeader, Panel } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { saveProfile, verifyProfile } from "@/features/credentials/actions";
import { ProfileForm, VerifyForm } from "@/features/credentials/forms";
import { changeMemberStatus, updateMemberRoles } from "@/features/staff/actions";
import { RolesForm, StatusForm } from "@/features/staff/forms";
import { assignmentOptions } from "@/features/staff/options";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { PROFESSIONS } from "@/lib/appointments";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Member, StaffProfile } from "@/types/api";

export const metadata: Metadata = { title: "Staff member" };

export default async function MemberPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ invited?: string }>;
}) {
  const { id } = await params;
  const { invited } = await searchParams;
  const { access } = await requirePermission("members.read");
  let member: Member;
  try {
    member = await api<Member>(`/members/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) notFound();
    throw error;
  }
  const isSelf = member.id === access.membership_id;
  let profile: StaffProfile | null = null;
  try {
    profile = await api<StaffProfile>(`/members/${encodeURIComponent(member.id)}/profile`);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }
  const canEditProfile = hasOrgWide(access, "members.manage");
  const canVerify = hasOrgWide(access, "credentials.verify") && !isSelf;
  const regLabel = !profile
    ? "Not recorded"
    : profile.registration_status === "verified"
      ? profile.licence_current ? "Verified, licence current" : "Verified, but licence expired"
      : profile.registration_status === "rejected" ? "Rejected" : "Not verified";
  const canManage = hasOrgWide(access, "members.manage") && !isSelf;

  return (
    <>
      <PageHeader title={member.full_name} back={{ href: "/staff", label: "Staff" }} />
      <div className="flex max-w-3xl flex-col gap-4">
        {invited && (
          <Notice tone="success">
            Invitation created. {member.full_name} will see it after signing in as {member.email}.
          </Notice>
        )}
        <Panel>
          <Details
            items={[
              { label: "Email", value: member.email },
              { label: "Phone", value: member.phone },
              { label: "Status", value: <Status status={member.status} /> },
              { label: "Last sign-in", value: formatDateTime(member.last_login_at) },
              { label: "Member since", value: formatDate(member.created_at) },
              { label: "Member ID", value: member.id.slice(0, 8), mono: true },
            ]}
          />
        </Panel>

        <Panel title="Roles">
          {canManage ? (
            <RolesForm
              action={updateMemberRoles.bind(null, member.id)}
              {...(await assignmentOptions())}
              initial={member.roles.map((r) => ({ role_id: r.role_id, branch_id: r.branch_id }))}
            />
          ) : (
            <>
              <ul className="list-inside list-disc text-base">
                {member.roles.map((r) => (
                  <li key={`${r.role_id}-${r.branch_id}`}>
                    {r.role_name} — {r.branch_name ?? "all branches"}
                  </li>
                ))}
              </ul>
              {isSelf && <p className="mt-2 text-xs text-text-muted">You can’t change your own roles.</p>}
            </>
          )}
        </Panel>

        <Panel
          title="Professional registration"
          description="Clinical permissions and bookings only take effect once registration is verified and the licence is current."
        >
          <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-1 text-base">
            <span>
              Status:{" "}
              <span className={profile?.licence_current ? "font-medium text-success-text" : "font-medium text-warning-text"}>{regLabel}</span>
            </span>
            {profile?.verified_at && <span className="text-text-muted">Decision recorded {formatDateTime(profile.verified_at)}{profile.verification_note && ` — “${profile.verification_note}”`}</span>}
          </div>
          {canEditProfile ? (
            <ProfileForm action={saveProfile.bind(null, member.id)} profile={profile} />
          ) : profile ? (
            <Details items={[
              { label: "Profession", value: PROFESSIONS[profile.profession] ?? profile.profession },
              { label: "Specialty", value: profile.specialty },
              { label: "Registration", value: [profile.registration_body, profile.professional_number].filter(Boolean).join(" ") || null, mono: true },
              { label: "Licence valid until", value: formatDate(profile.licence_expiry_date) },
            ]} />
          ) : null}
          {canVerify && profile && profile.professional_number && (
            <div className="mt-4 border-t border-border pt-4">
              <VerifyForm action={verifyProfile.bind(null, member.id)} personName={member.full_name} />
            </div>
          )}
          {isSelf && <p className="mt-3 text-xs text-text-muted">Someone else must verify your registration.</p>}
        </Panel>

        {canManage && (
          <Panel title="Access" description="Suspending removes access immediately. History is kept.">
            {member.status === "suspended" ? (
              <StatusForm
                action={changeMemberStatus.bind(null, member.id, "reactivate")}
                personName={member.full_name}
                mode="reactivate"
              />
            ) : (
              <StatusForm
                action={changeMemberStatus.bind(null, member.id, "suspend")}
                personName={member.full_name}
                mode="suspend"
              />
            )}
          </Panel>
        )}
      </div>
    </>
  );
}
