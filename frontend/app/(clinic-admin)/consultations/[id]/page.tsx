import type { Metadata } from "next";
import Link from "next/link";

import { PatientIdentityBanner } from "@/components/patients/identity-banner";
import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { Tag } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import {
  addDiagnosis, addReferral, cancelPrescription, cancelReferral, changeDiagnosis, closeConsultation,
  markObservationError, noteAction, prescribe, recordVitals,
} from "@/features/clinical/actions";
import { AmendButton, DiagnosisForm, NewNote, NoteEditor, PrescriptionForm, ReasonAction, ReferralForm, SimpleAction, VitalsForm } from "@/features/clinical/forms";
import { loadClinical } from "@/features/clinical/load";
import { orderTests } from "@/features/lab/actions";
import { LabOrderForm } from "@/features/lab/forms";
import { LabStatus } from "@/features/lab/status";
import { api } from "@/lib/api";
import { ENCOUNTER_TYPE_LABEL, NOTE_SECTIONS, NOTE_TYPE_LABEL, OBS_LABEL } from "@/lib/clinical";
import { formatDateTime } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { AllergySummary, ClinicalNote, EncounterDetail, Laboratory, LabOrderSummary, LabTest, Page, Patient } from "@/types/api";

export const metadata: Metadata = { title: "Consultation" };

function NoteBody({ note }: { note: ClinicalNote }) {
  return (
    <dl className="flex flex-col gap-2">
      {(NOTE_SECTIONS[note.note_type] ?? []).filter((s) => note.content[s.key]?.trim()).map((s) => (
        <div key={s.key}>
          <dt className="text-xs font-medium tracking-wide text-text-muted uppercase">{s.label}</dt>
          <dd className="text-base whitespace-pre-wrap">{note.content[s.key]}</dd>
        </div>
      ))}
    </dl>
  );
}

export default async function ConsultationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access, me } = await requirePermission("clinical.read");
  const e = await loadClinical<EncounterDetail>(`/encounters/${encodeURIComponent(id)}`);
  const [patient, allergies] = await Promise.all([
    api<Patient>(`/patients/${e.patient_id}`),
    api<AllergySummary>(`/patients/${e.patient_id}/allergies`),
  ]);
  const name = `${patient.first_name} ${patient.last_name}`;
  const inBranch = (p: string) => access.grants.some((g) => g.permission === p && (g.branch_id === null || g.branch_id === e.branch_id));
  const canWrite = inBranch("clinical.write");
  const canSign = inBranch("clinical.sign");
  const canPrescribe = inBranch("prescriptions.issue");
  const open = e.status === "open";
  const canSeeLab = inBranch("lab.read");
  const canOrderLab = canWrite && open;
  const [labOrders, labTests, laboratories] = await Promise.all([
    canSeeLab ? api<Page<LabOrderSummary>>("/lab-orders", { query: { encounter_id: e.id, group: "all", limit: 50 } }) : Promise.resolve(null),
    canOrderLab ? api<LabTest[]>("/laboratory-tests") : Promise.resolve([] as LabTest[]),
    canOrderLab ? api<Laboratory[]>("/laboratories") : Promise.resolve([] as Laboratory[]),
  ]);

  // Group note versions; show the newest version first within each group.
  const groups = new Map<string, ClinicalNote[]>();
  for (const n of e.notes) groups.set(n.note_group_id, [...(groups.get(n.note_group_id) ?? []), n]);

  return (
    <>
      <PatientIdentityBanner patient={{ name, patient_number: patient.patient_number, date_of_birth: patient.date_of_birth, sex: patient.sex }} allergies={allergies} />
      <PageHeader
        title={ENCOUNTER_TYPE_LABEL[e.encounter_type] ?? e.encounter_type}
        description={`${e.clinician_name} · ${e.branch_name} · started ${formatDateTime(e.started_at)}${e.ended_at ? ` · closed ${formatDateTime(e.ended_at)}` : ""}`}
        back={{ href: `/patients/${patient.id}/clinical`, label: "Clinical record" }}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        {!open && <Notice>This consultation is closed. Signed notes can still be amended; the originals are kept.</Notice>}
        {allergies.state === "not_recorded" && <Notice tone="error">Allergies have not been recorded for {name}. <Link className="underline" href={`/patients/${patient.id}/clinical`}>Record allergies</Link></Notice>}

        <Panel title="Notes">
          <div className="flex flex-col gap-4">
            {[...groups.values()].map((versions) => {
              const sorted = [...versions].sort((a, b) => b.version_number - a.version_number);
              const latest = sorted[0]!;
              const draft = latest.status === "draft" ? latest : null;
              const current = sorted.find((n) => n.status === "signed");
              const mine = draft && draft.author_user_id === me.id;
              return (
                <article key={latest.note_group_id} className="rounded border border-border p-3">
                  {current && (
                    <>
                      <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-base font-medium">{NOTE_TYPE_LABEL[current.note_type]} {current.version_number > 1 && <Tag>Amended · v{current.version_number}</Tag>}</span>
                        <span className="text-sm text-text-muted">Signed by {current.author_name} · {formatDateTime(current.signed_at)}</span>
                      </header>
                      <NoteBody note={current} />
                      {current.amendment_reason && <p className="mt-2 text-sm text-text-muted">Amendment reason: “{current.amendment_reason}”</p>}
                      {canWrite && !draft && <div className="mt-3"><AmendButton action={noteAction.bind(null, e.id, null, current.id)} amending={current} patientName={name} canSign={canSign} /></div>}
                    </>
                  )}
                  {draft && (
                    <div className={current ? "mt-3 border-t border-border pt-3" : ""}>
                      <p className="mb-2 text-sm font-medium text-warning-text">{current ? "Amendment in progress" : "Draft"} · {draft.author_name}</p>
                      {mine ? (
                        <NoteEditor action={noteAction.bind(null, e.id, draft.id, null)} note={draft} patientName={name} canSign={canSign} />
                      ) : (
                        <NoteBody note={draft} />
                      )}
                    </div>
                  )}
                  {sorted.filter((n) => n.status === "amended").length > 0 && (
                    <details className="mt-3">
                      <summary className="cursor-pointer text-sm text-primary">Earlier versions ({sorted.filter((n) => n.status === "amended").length})</summary>
                      {sorted.filter((n) => n.status === "amended").map((n) => (
                        <div key={n.id} className="mt-2 border-l-2 border-border pl-3">
                          <p className="text-sm text-text-muted">v{n.version_number} · signed by {n.author_name} · {formatDateTime(n.signed_at)} · <span className="font-mono">{n.content_sha256?.slice(0, 12)}</span></p>
                          <NoteBody note={n} />
                        </div>
                      ))}
                    </details>
                  )}
                </article>
              );
            })}
            {e.notes.length === 0 && <p className="text-text-muted">No notes yet.</p>}
            {canWrite && open && <NewNote action={noteAction.bind(null, e.id, null, null)} patientName={name} canSign={canSign} />}
          </div>
        </Panel>

        <Panel title="Vital signs">
          {e.observations.length > 0 && (
            <div className="mb-4">
              <Table>
                <THead><tr><TH>Measured</TH><TH>Measurement</TH><TH align="right">Value</TH><TH>Status</TH>{canWrite && <TH align="right">Actions</TH>}</tr></THead>
                <tbody>
                  {e.observations.map((o) => (
                    <TR key={o.id} className={o.status !== "final" ? "text-text-muted line-through" : undefined}>
                      <TD className="tabular">{formatDateTime(o.measured_at)}</TD>
                      <TD>{OBS_LABEL[o.observation_type] ?? o.observation_type}</TD>
                      <TD align="right" mono>{Number(o.value)} {o.unit}</TD>
                      <TD className="no-underline">{o.status === "final" ? "Recorded" : `Entered in error: ${o.status_reason}`}</TD>
                      {canWrite && <TD align="right">{o.status === "final" && <ReasonAction action={markObservationError.bind(null, e.id, o.id)} label="Entered in error" />}</TD>}
                    </TR>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
          {canWrite && open ? <VitalsForm action={recordVitals.bind(null, e.id)} /> : e.observations.length === 0 && <p className="text-text-muted">None recorded.</p>}
        </Panel>

        <Panel title="Diagnoses">
          {e.diagnoses.length > 0 && (
            <ul className="mb-4 flex flex-col gap-2">
              {e.diagnoses.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span className={d.clinical_status === "entered_in_error" ? "text-text-muted line-through" : ""}>
                    {d.code && <span className="mr-2 font-mono text-sm">{d.code}</span>}{d.description}
                    <span className="ml-2 text-sm text-text-muted">{d.clinical_status.replaceAll("_", " ")}</span>
                  </span>
                  {canWrite && d.clinical_status === "active" && (
                    <span className="flex gap-2">
                      <ReasonAction action={changeDiagnosis.bind(null, e.id, d.id)} label="Resolved" hiddenName="clinical_status" hiddenValue="resolved" />
                      <ReasonAction action={changeDiagnosis.bind(null, e.id, d.id)} label="Entered in error" hiddenName="clinical_status" hiddenValue="entered_in_error" />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {canWrite && open ? <DiagnosisForm action={addDiagnosis.bind(null, e.id)} /> : e.diagnoses.length === 0 && <p className="text-text-muted">None recorded.</p>}
        </Panel>

        <Panel title="Prescriptions">
          {e.prescriptions.map((rx) => (
            <article key={rx.id} className="mb-3 rounded border border-border p-3">
              <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span><span className="font-mono">{rx.prescription_number}</span> <span className="text-sm text-text-muted">· {formatDateTime(rx.issued_at)} · {rx.prescriber_name}</span>{rx.status === "cancelled" && <span className="ml-2 text-sm font-medium text-danger-text">Cancelled: {rx.cancel_reason}</span>}</span>
                <span className="flex gap-2">
                  {rx.status === "issued" && <Link className="inline-flex h-7 items-center rounded border border-border px-2.5 text-sm hover:bg-surface-muted" href={`/print/prescriptions/${rx.id}`} target="_blank">Print</Link>}
                  {canPrescribe && rx.status === "issued" && <ReasonAction action={cancelPrescription.bind(null, e.id, rx.id)} label={`Cancel ${rx.prescription_number}`} danger />}
                </span>
              </header>
              <ol className="list-inside list-decimal text-base">
                {rx.items.map((i) => <li key={i.position}><strong>{i.medication}</strong> {i.strength} — {i.dose}, {i.frequency}{i.duration && `, for ${i.duration}`}{i.quantity && ` (qty ${i.quantity})`}{i.instructions && `. ${i.instructions}`}</li>)}
              </ol>
              {rx.allergy_warning && <p className="mt-2 text-sm text-danger-text">Prescribed despite allergy warning: “{rx.allergy_warning.reason}”</p>}
            </article>
          ))}
          {canPrescribe && open ? <PrescriptionForm action={prescribe.bind(null, e.id)} patientName={name} /> : e.prescriptions.length === 0 && <p className="text-text-muted">None issued.</p>}
        </Panel>

        {(canSeeLab || canOrderLab) && (
          <Panel title="Laboratory">
            {labOrders && labOrders.items.length > 0 && (
              <ul className="mb-4 flex flex-col gap-2">
                {labOrders.items.map((o) => (
                  <li key={o.id} className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      <Link className="font-mono text-primary hover:underline" href={`/lab/${o.id}`}>{o.order_number}</Link>
                      {o.urgency === "urgent" && <span className="ml-2 text-sm font-semibold text-danger-text">Urgent</span>}
                      <span className="ml-2">{o.tests.join(", ")}</span>
                    </span>
                    <LabStatus status={o.status} />
                  </li>
                ))}
              </ul>
            )}
            {canOrderLab ? (
              <LabOrderForm action={orderTests.bind(null, e.id)} tests={labTests} laboratories={laboratories} patientName={name} />
            ) : (labOrders?.items.length ?? 0) === 0 && <p className="text-text-muted">No tests requested.</p>}
          </Panel>
        )}

        <Panel title="Referrals">
          {e.referrals.map((r) => (
            <div key={r.id} className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div className={r.status === "cancelled" ? "text-text-muted line-through" : ""}>
                <p className="font-medium">{r.receiving_provider}{r.receiving_specialty && ` · ${r.receiving_specialty}`} {r.urgency === "urgent" && <span className="text-danger-text">· Urgent</span>}</p>
                <p className="text-base whitespace-pre-wrap">{r.reason}</p>
              </div>
              {canWrite && r.status === "issued" && <ReasonAction action={cancelReferral.bind(null, e.id, r.id)} label="Cancel referral" />}
            </div>
          ))}
          {canWrite && open ? <ReferralForm action={addReferral.bind(null, e.id)} /> : e.referrals.length === 0 && <p className="text-text-muted">None issued.</p>}
        </Panel>

        {canWrite && open && (
          <Panel title="Finish">
            <p className="mb-3 text-base text-text-muted">Closing requires all notes to be signed{e.appointment_id ? " and marks the appointment completed" : ""}.</p>
            <SimpleAction action={closeConsultation.bind(null, e.id)} label={`Close consultation for ${name}`} pendingLabel="Closing…" />
          </Panel>
        )}
      </div>
    </>
  );
}
