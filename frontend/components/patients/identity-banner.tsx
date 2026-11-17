import { CircleAlert, CircleCheck, CircleHelp } from "lucide-react";

import { SEVERITY_LABEL } from "@/lib/clinical";
import { formatDate } from "@/lib/format";
import { ageOf } from "@/lib/time";
import type { AllergySummary } from "@/types/api";

const SEX: Record<string, string> = {
  female: "Female",
  male: "Male",
  intersex: "Intersex",
  unknown: "Sex not recorded",
};

/** The allergy indicator is never blank (docs/DESIGN.md §6). */
function AllergyIndicator({ allergies }: { allergies: AllergySummary | null | undefined }) {
  if (allergies === undefined) {
    return <span className="text-sm text-text-muted">Allergies: not shown in administrative view</span>;
  }
  if (allergies === null || allergies.state === "not_recorded") {
    return (
      <span className="inline-flex items-center gap-1 text-sm font-medium text-warning-text">
        <CircleHelp size={16} strokeWidth={1.5} aria-hidden /> Allergies not recorded
      </span>
    );
  }
  if (allergies.state === "no_known_allergies") {
    return (
      <span className="inline-flex items-center gap-1 text-sm font-medium text-success-text">
        <CircleCheck size={16} strokeWidth={1.5} aria-hidden /> No known allergies
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-danger bg-danger-subtle px-2 py-0.5 text-sm font-medium text-danger-text">
      <CircleAlert size={16} strokeWidth={1.5} aria-hidden />
      Allergies: {allergies.allergies.map((a) => `${a.substance} (${SEVERITY_LABEL[a.severity] ?? a.severity})`).join(", ")}
    </span>
  );
}

/** Pinned identity strip on patient-context screens so staff never act on the wrong patient.
 *  Pass `allergies` on clinical screens; omit it on administrative screens. */
export function PatientIdentityBanner({
  patient,
  allergies,
}: {
  patient: { name: string; patient_number: string; date_of_birth: string; sex?: string | null };
  allergies?: AllergySummary | null;
}) {
  return (
    <div className="sticky top-0 z-20 -mx-4 mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-border bg-surface px-4 py-2 md:-mx-6 md:px-6">
      <span className="text-md font-semibold text-text">{patient.name}</span>
      <span className="text-base text-text">
        Born {formatDate(patient.date_of_birth)}{" "}
        <span className="text-text-muted">({ageOf(patient.date_of_birth)} y)</span>
      </span>
      {patient.sex !== undefined && <span className="text-base text-text-muted">{SEX[patient.sex ?? "unknown"]}</span>}
      <span className="font-mono text-sm text-text">{patient.patient_number}</span>
      <AllergyIndicator allergies={allergies} />
    </div>
  );
}
