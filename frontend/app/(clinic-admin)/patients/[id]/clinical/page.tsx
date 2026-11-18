import type { Metadata } from "next";
import Link from "next/link";

import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { Select } from "@/components/ui/field";
import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { addAllergy, changeAllergy, noKnownAllergies, startConsultation } from "@/features/clinical/actions";
import { AllergyForm, ReasonAction, SimpleAction } from "@/features/clinical/forms";
import { loadClinical } from "@/features/clinical/load";
import { ButtonLink } from "@/components/ui/button";
import { enabledModules } from "@/lib/specialty";
import { LabStatus } from "@/features/lab/status";
import { api } from "@/lib/api";
import { ENCOUNTER_TYPE_LABEL, OBS_LABEL, SEVERITY_LABEL } from "@/lib/clinical";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { Branch, ClinicalSummary, LabOrderSummary, Page, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Clinical record" };

export default async function ClinicalRecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("clinical.read");
  const patient = await loadClinical<Patient>(`/patients/${encodeURIComponent(id)}`);
  const summary = await loadClinical<ClinicalSummary>(`/patients/${patient.id}/clinical-summary`);
  const labOrders = hasPermission(access, "lab.read")
    ? await api<Page<LabOrderSummary>>("/lab-orders", { query: { patient_id: patient.id, group: "all", limit: 20 } })
    : null;
  const name = `${patient.first_name} ${patient.last_name}`;
  const modules = await enabledModules();
  const canWrite = hasPermission(access, "clinical.write");
  const writeBranches = canWrite
    ? (await api<Page<Branch>>("/branches", { query: { limit: 200 } })).items.filter((b) =>
        access.grants.some((g) => g.permission === "clinical.write" && (g.branch_id === null || g.branch_id === b.id)))
    : [];

  return (
    <>
      <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }} allergies={summary.allergies} />
      <PageHeader
        title="Clinical record"
        description={name}
        back={{ href: `/patients/${patient.id}`, label: "Patient details" }}
        actions={<>
          {modules.has("dental") && <ButtonLink variant="secondary" href={`/patients/${patient.id}/dental`}>Dental</ButtonLink>}
          {modules.has("physiotherapy") && <ButtonLink variant="secondary" href={`/patients/${patient.id}/physio`}>Physiotherapy</ButtonLink>}
        </>}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        <Panel title="Allergies">
          {summary.allergies.allergies.length > 0 ? (
            <ul className="mb-3 flex flex-col gap-2">
              {summary.allergies.allergies.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span><strong className="text-danger-text">{a.substance}</strong> · {SEVERITY_LABEL[a.severity]}{a.reaction && ` · ${a.reaction}`} <span className="text-sm text-text-muted">· recorded {formatDate(a.created_at)}</span></span>
                  {canWrite && (
                    <span className="flex gap-2">
                      <ReasonAction action={changeAllergy.bind(null, patient.id, a.id)} label="No longer active" hiddenName="status" hiddenValue="inactive" />
                      <ReasonAction action={changeAllergy.bind(null, patient.id, a.id)} label="Entered in error" hiddenName="status" hiddenValue="entered_in_error" />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-3 text-base">{summary.allergies.state === "no_known_allergies" ? `No known allergies (recorded ${formatDate(summary.allergies.assessed_at)}).` : "Allergies have not been recorded."}</p>
          )}
          {canWrite && (
            <div className="flex flex-col gap-3">
              <AllergyForm action={addAllergy.bind(null, patient.id)} />
              {summary.allergies.state === "not_recorded" && <SimpleAction action={noKnownAllergies.bind(null, patient.id)} label="Record: no known allergies" variant="secondary" />}
            </div>
          )}
        </Panel>

        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Active diagnoses">
            {summary.active_diagnoses.length ? (
              <ul className="flex flex-col gap-1 text-base">{summary.active_diagnoses.map((d) => <li key={d.id}>{d.code && <span className="mr-2 font-mono text-sm">{d.code}</span>}{d.description}</li>)}</ul>
            ) : <p className="text-text-muted">None recorded.</p>}
          </Panel>
          <Panel title="Latest vital signs">
            {summary.latest_observations.length ? (
              <table className="w-full text-base"><tbody>
                {summary.latest_observations.map((o) => (
                  <tr key={o.observation_type} className="border-b border-border last:border-0">
                    <th scope="row" className="py-1 text-left font-normal">{OBS_LABEL[o.observation_type]}</th>
                    <td className="py-1 text-right font-mono text-sm">{Number(o.value)} {o.unit}</td>
                    <td className="py-1 pl-3 text-right text-sm text-text-muted">{formatDate(o.measured_at)}</td>
                  </tr>
                ))}
              </tbody></table>
            ) : <p className="text-text-muted">None recorded.</p>}
          </Panel>
        </div>

        <Panel title="Recent prescriptions">
          {summary.recent_prescriptions.length ? (
            <ul className="flex flex-col gap-1 text-base">
              {summary.recent_prescriptions.map((rx) => (
                <li key={rx.id} className={rx.status === "cancelled" ? "text-text-muted line-through" : ""}>
                  <span className="font-mono text-sm">{rx.prescription_number}</span> · {formatDate(rx.issued_at)} · {rx.items.map((i) => `${i.medication} ${i.strength ?? ""}`.trim()).join(", ")}
                </li>
              ))}
            </ul>
          ) : <p className="text-text-muted">None in the last six months.</p>}
        </Panel>

        {labOrders && (
          <Panel title="Laboratory">
            {labOrders.items.length ? (
              <Table>
                <THead><tr><TH>Order</TH><TH>Requested</TH><TH>Tests</TH><TH>Status</TH><TH>Flags</TH></tr></THead>
                <tbody>
                  {labOrders.items.map((o) => (
                    <TR key={o.id}>
                      <TD mono><Link className="text-primary hover:underline" href={`/lab/${o.id}`}>{o.order_number}</Link></TD>
                      <TD className="tabular">{formatDate(o.requested_at)}</TD>
                      <TD className="max-w-72 truncate" title={o.tests.join(", ")}>{o.tests.join(", ")}</TD>
                      <TD><LabStatus status={o.status} /></TD>
                      <TD>{o.abnormal_results > 0 ? <span className="font-semibold text-warning-text">{o.abnormal_results} flagged</span> : <span className="text-text-muted">—</span>}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            ) : <p className="text-text-muted">No laboratory orders.</p>}
          </Panel>
        )}

        <Panel title="Consultations">
          {summary.encounters.length ? (
            <Table>
              <THead><tr><TH>Started</TH><TH>Type</TH><TH>Clinician</TH><TH>Branch</TH><TH>Status</TH></tr></THead>
              <tbody>
                {summary.encounters.map((enc) => (
                  <TR key={enc.id}>
                    <TD className="tabular"><Link className="text-primary hover:underline" href={`/consultations/${enc.id}`}>{formatDateTime(enc.started_at)}</Link></TD>
                    <TD>{ENCOUNTER_TYPE_LABEL[enc.encounter_type]}</TD>
                    <TD>{enc.clinician_name}</TD>
                    <TD className="text-text-muted">{enc.branch_name}</TD>
                    <TD>{enc.status === "open" ? <span className="font-medium text-warning-text">Open</span> : "Closed"}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          ) : <EmptyState message="No consultations yet." />}
          {writeBranches.length > 0 && (
            <form action={async (form: FormData) => { "use server"; await startConsultation(patient.id, null, form); }} className="mt-4 flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-sm">Unscheduled consultation
                <Select name="encounter_type" defaultValue="consultation" className="w-56">
                  {Object.entries(ENCOUNTER_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-sm">Branch
                <Select name="branch_id" defaultValue={writeBranches[0]!.id} className="w-48">{writeBranches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
              </label>
              <button type="submit" className="h-9 rounded bg-primary px-3.5 font-medium text-white hover:bg-primary-hover">Start consultation</button>
            </form>
          )}
        </Panel>
        <p className="text-xs text-text-muted">Viewing this record is recorded in the audit log.</p>
      </div>
    </>
  );
}
