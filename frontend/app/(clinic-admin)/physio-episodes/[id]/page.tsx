import type { Metadata } from "next";
import Link from "next/link";

import { loadPatientFor } from "@/components/clinical/patient-context";
import { Field, Select, Textarea } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { ReasonAction } from "@/features/clinical/forms";
import { loadClinical } from "@/features/clinical/load";
import { dischargeEpisode, measurementError, recordMeasurements } from "@/features/physio/actions";
import { MeasurementForm } from "@/features/physio/forms";
import { api } from "@/lib/api";
import { MEASURE_LABEL, OUTCOME_LABEL } from "@/lib/dental";
import { formatDate, formatDateTime } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { ClinicalSummary, PhysioEpisodeDetail } from "@/types/api";

export const metadata: Metadata = { title: "Episode of care" };

const num = (v: string) => Number(v).toString();
const side = (s: string | null) => (s ? ` (${s})` : "");

export default async function EpisodePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("clinical.read");
  const ep = await loadClinical<PhysioEpisodeDetail>(`/physio-episodes/${encodeURIComponent(id)}`);
  const { name, banner } = await loadPatientFor("physiotherapy", ep.patient_id);
  const canWrite = ep.status === "active" && access.grants.some((g) => g.permission === "clinical.write" && (g.branch_id === null || g.branch_id === ep.branch_id));
  const summary = canWrite ? await api<ClinicalSummary>(`/patients/${ep.patient_id}/clinical-summary`) : null;
  const encounters = (summary?.encounters ?? []).slice(0, 15).map((e) => ({ id: e.id, label: `${formatDateTime(e.started_at)} · ${e.clinician_name}${e.status === "open" ? " (open)" : ""}` }));
  const presets = ep.series.map((s) => ({ measure: s.measure, label: s.label, side: s.side }));

  return (
    <>
      {banner}
      <PageHeader
        title={ep.condition}
        description={`${ep.body_region ? `${ep.body_region} · ` : ""}started ${formatDate(ep.started_on)} · ${ep.clinician_name} · ${ep.sessions_done}${ep.planned_sessions ? ` of ${ep.planned_sessions}` : ""} sessions`}
        back={{ href: `/patients/${ep.patient_id}/physio`, label: "Physiotherapy" }}
      />
      <div className="flex max-w-5xl flex-col gap-4">
        {ep.status === "discharged" && (
          <Panel title={`Discharged ${formatDate(ep.discharged_on)} · ${ep.discharge_outcome ? OUTCOME_LABEL[ep.discharge_outcome] : ""}`}>
            <p className="whitespace-pre-wrap">{ep.discharge_summary}</p>
          </Panel>
        )}
        {(ep.goals || ep.referral_source) && (
          <Panel title="Goals">
            {ep.goals && <p className="whitespace-pre-wrap">{ep.goals}</p>}
            {ep.referral_source && <p className="mt-2 text-sm text-text-muted">Referred by {ep.referral_source}</p>}
          </Panel>
        )}
        <Panel title="Progress" description="First and latest value of each measure.">
          {ep.series.length === 0 ? <p className="text-text-muted">No measurements yet.</p> : (
            <Table>
              <THead><tr><TH>Measure</TH><TH align="right">First</TH><TH align="right">Latest</TH><TH align="right">Change</TH><TH align="right">Times</TH></tr></THead>
              <tbody>
                {ep.series.map((s) => (
                  <TR key={`${s.measure}-${s.label}-${s.side}`}>
                    <TD>{s.label}{side(s.side)} <span className="text-sm text-text-muted">· {MEASURE_LABEL[s.measure]}</span></TD>
                    <TD align="right" mono>{num(s.first)}{s.unit}</TD>
                    <TD align="right" mono>{num(s.latest)}{s.unit}</TD>
                    <TD align="right" mono>{Number(s.change) > 0 ? "+" : Number(s.change) < 0 ? "−" : ""}{num(String(Math.abs(Number(s.change))))}{s.unit}</TD>
                    <TD align="right" mono>{s.points.length}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        <Panel title="Sessions">
          {ep.sessions.length === 0 ? <p className="text-text-muted">No sessions counted yet. Recording measurements in a consultation counts it.</p> : (
            <ol className="flex flex-col gap-1">
              {ep.sessions.map((s) => (
                <li key={s.session_number}><span className="font-mono">{s.session_number}.</span> <Link className="text-primary hover:underline" href={`/consultations/${s.encounter_id}`}>{formatDateTime(s.started_at)}</Link> <span className="text-text-muted">· {s.clinician_name}</span></li>
              ))}
            </ol>
          )}
        </Panel>
        {canWrite && encounters.length > 0 && (
          <Panel title="Record measurements"><MeasurementForm action={recordMeasurements.bind(null, ep.id)} encounters={encounters} presets={presets} /></Panel>
        )}
        <Panel title="All measurements">
          {ep.measurements.length === 0 ? <p className="text-text-muted">None.</p> : (
            <Table>
              <THead><tr><TH>When</TH><TH>Measure</TH><TH align="right">Value</TH><TH>By</TH>{canWrite && <TH align="right">Actions</TH>}</tr></THead>
              <tbody>
                {[...ep.measurements].reverse().map((m) => (
                  <TR key={m.id} className={m.status !== "recorded" ? "text-text-muted line-through" : undefined}>
                    <TD className="tabular">{formatDateTime(m.measured_at)}</TD>
                    <TD className="no-underline">{m.label}{side(m.side)}{m.status !== "recorded" && <span className="block text-sm">Entered in error: {m.status_reason}</span>}</TD>
                    <TD align="right" mono>{num(m.value)}{m.unit}</TD>
                    <TD className="text-text-muted">{m.recorded_by_name}</TD>
                    {canWrite && <TD align="right">{m.status === "recorded" && <ReasonAction action={measurementError.bind(null, ep.id, m.id)} label="Entered in error" />}</TD>}
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        {canWrite && (
          <Panel title="Discharge" description="Closes the episode. It can't be changed afterwards.">
            <QuickForm action={dischargeEpisode.bind(null, ep.id)} submit={`Discharge ${name}`}>
              <Field id="dc-outcome" label="Outcome"><Select id="dc-outcome" name="outcome" className="w-48">{Object.entries(OUTCOME_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
              <Field id="dc-summary" label="Discharge summary" required className="w-full"><Textarea id="dc-summary" name="summary" rows={3} required minLength={3} /></Field>
            </QuickForm>
          </Panel>
        )}
      </div>
    </>
  );
}
