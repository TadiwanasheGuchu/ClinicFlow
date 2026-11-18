import type { Metadata } from "next";
import Link from "next/link";

import { loadPatientFor } from "@/components/clinical/patient-context";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { openEpisode } from "@/features/physio/actions";
import { api } from "@/lib/api";
import { OUTCOME_LABEL } from "@/lib/dental";
import { formatDate } from "@/lib/format";
import { requirePermission } from "@/lib/session";
import type { Branch, Page, PhysioEpisode } from "@/types/api";

export const metadata: Metadata = { title: "Physiotherapy" };

export default async function PhysioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { access } = await requirePermission("clinical.read");
  const { patient, name, banner } = await loadPatientFor("physiotherapy", id);
  const episodes = await api<PhysioEpisode[]>(`/patients/${patient.id}/physio-episodes`);
  const branches = (await api<Page<Branch>>("/branches", { query: { limit: 200 } })).items.filter((b) =>
    access.grants.some((g) => g.permission === "clinical.write" && (g.branch_id === null || g.branch_id === b.id)));
  return (
    <>
      {banner}
      <PageHeader title="Physiotherapy" description={name} back={{ href: `/patients/${patient.id}/clinical`, label: "Clinical record" }} />
      <div className="flex max-w-5xl flex-col gap-4">
        <Panel title="Episodes of care">
          {episodes.length === 0 ? <p className="text-text-muted">No episodes yet.</p> : (
            <Table>
              <THead><tr><TH>Condition</TH><TH>Started</TH><TH align="right">Sessions</TH><TH>Status</TH><TH>Clinician</TH></tr></THead>
              <tbody>
                {episodes.map((e) => (
                  <TR key={e.id}>
                    <TD><Link className="text-primary hover:underline" href={`/physio-episodes/${e.id}`}>{e.condition}</Link>{e.body_region && <span className="text-sm text-text-muted"> · {e.body_region}</span>}</TD>
                    <TD className="tabular">{formatDate(e.started_on)}</TD>
                    <TD align="right" mono>{e.sessions_done}{e.planned_sessions ? ` / ${e.planned_sessions}` : ""}</TD>
                    <TD>{e.status === "active" ? <span className="font-medium">Active</span> : `Discharged ${formatDate(e.discharged_on)}${e.discharge_outcome ? ` · ${OUTCOME_LABEL[e.discharge_outcome]}` : ""}`}</TD>
                    <TD className="text-text-muted">{e.clinician_name}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        {branches.length > 0 && (
          <Panel title="Open an episode of care" description="Session notes stay in the consultation; this tracks goals, sessions and outcome measures.">
            <QuickForm action={openEpisode.bind(null, patient.id)} submit="Open episode">
              <Field id="ep-condition" label="Condition" required><Input id="ep-condition" name="condition" required minLength={2} placeholder="e.g. Right shoulder impingement" className="w-72" /></Field>
              <Field id="ep-region" label="Body region"><Input id="ep-region" name="body_region" className="w-40" /></Field>
              <Field id="ep-branch" label="Branch"><Select id="ep-branch" name="branch_id" className="w-44">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
              <Field id="ep-planned" label="Planned sessions"><Input id="ep-planned" name="planned_sessions" type="number" min={1} max={200} className="w-24 text-right font-mono" /></Field>
              <Field id="ep-ref" label="Referred by"><Input id="ep-ref" name="referral_source" className="w-56" /></Field>
              <Field id="ep-goals" label="Goals" className="w-full"><Textarea id="ep-goals" name="goals" rows={2} /></Field>
            </QuickForm>
          </Panel>
        )}
      </div>
    </>
  );
}
