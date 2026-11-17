import { formatDate } from "@/lib/format";
import { ageOf } from "@/lib/time";

const SEX: Record<string, string> = {
  female: "Female",
  male: "Male",
  intersex: "Intersex",
  unknown: "Sex not recorded",
};

/** Pinned identity strip on patient-context screens (docs/DESIGN.md §6) so staff never act on
 *  the wrong patient. Clinical records (and the allergy list) arrive in Phase 4; until then the
 *  banner states plainly that allergies are not shown, rather than leaving it blank. */
export function PatientIdentityBanner({
  patient,
}: {
  patient: { name: string; patient_number: string; date_of_birth: string; sex?: string | null };
}) {
  return (
    <div className="sticky top-0 z-20 -mx-4 mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-border bg-surface px-4 py-2 md:-mx-6 md:px-6">
      <span className="text-md font-semibold text-text">{patient.name}</span>
      <span className="text-base text-text">
        Born {formatDate(patient.date_of_birth)}{" "}
        <span className="text-text-muted">({ageOf(patient.date_of_birth)} y)</span>
      </span>
      {patient.sex !== undefined && (
        <span className="text-base text-text-muted">{SEX[patient.sex ?? "unknown"]}</span>
      )}
      <span className="font-mono text-sm text-text">{patient.patient_number}</span>
      <span className="text-sm text-text-muted">Allergies: not shown in administrative view</span>
    </div>
  );
}
