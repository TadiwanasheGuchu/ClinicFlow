import type { Metadata } from "next";

import { PageHeader, Panel } from "@/components/ui/layout";
import { registerPatient } from "@/features/patients/actions";
import { PatientForm } from "@/features/patients/patient-form";
import { hasPermission, requirePermission } from "@/lib/session";

export const metadata: Metadata = { title: "Register patient" };

export default async function NewPatientPage() {
  const { access } = await requirePermission("patients.write");
  return (
    <>
      <PageHeader title="Register patient" description="We check for existing records with the same details before creating a new one." back={{ href: "/patients", label: "Patients" }} />
      <Panel>
        <PatientForm action={registerPatient} allowBookNext={hasPermission(access, "appointments.manage")} />
      </Panel>
    </>
  );
}
