import "server-only";

import { notFound } from "next/navigation";

import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { loadClinical } from "@/features/clinical/load";
import { api } from "@/lib/api";
import { enabledModules } from "@/lib/specialty";
import type { AllergySummary, Patient } from "@/types/api";

/** Patient, allergies and the module gate for specialty screens. */
export async function loadPatientFor(module: "dental" | "physiotherapy", patientId: string) {
  if (!(await enabledModules()).has(module)) notFound();
  const patient = await loadClinical<Patient>(`/patients/${encodeURIComponent(patientId)}`);
  const allergies = await api<AllergySummary>(`/patients/${patient.id}/allergies`);
  const name = `${patient.first_name} ${patient.last_name}`;
  const banner = (
    <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }} allergies={allergies} />
  );
  return { patient, name, banner };
}
