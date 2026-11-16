import type { Metadata } from "next";

import { Details, PageHeader, Panel } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { OrganisationForm } from "@/features/organisation/organisation-form";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Organisation } from "@/types/api";

export const metadata: Metadata = { title: "Organisation" };

export default async function OrganisationPage() {
  const { access } = await requirePermission("organisation.read");
  const org = await api<Organisation>("/organisation");
  const canManage = hasOrgWide(access, "organisation.manage");

  return (
    <>
      <PageHeader title="Organisation" description="Practice details and defaults used across ClinicFlow." />
      <div className="flex max-w-3xl flex-col gap-4">
        <Panel>
          <Details
            items={[
              { label: "Status", value: <Status status={org.status} /> },
              { label: "Currency", value: org.currency, mono: true },
              { label: "Time zone", value: org.timezone },
              { label: "Registered on ClinicFlow", value: formatDate(org.created_at) },
            ]}
          />
        </Panel>
        <Panel>
          {canManage ? (
            <OrganisationForm organisation={org} />
          ) : (
            <Details
              items={[
                { label: "Practice name", value: org.name },
                { label: "Registered business name", value: org.legal_name },
                { label: "Registration number", value: org.registration_number },
                { label: "Phone", value: org.phone },
                { label: "Email", value: org.email },
                { label: "Patient number prefix", value: org.settings.patient_number_prefix, mono: true },
              ]}
            />
          )}
        </Panel>
      </div>
    </>
  );
}
