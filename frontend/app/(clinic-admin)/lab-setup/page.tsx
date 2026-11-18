import type { Metadata } from "next";

import { Notice, PageHeader, Panel } from "@/components/ui/layout";
import { saveLaboratory, saveLabTest } from "@/features/lab/actions";
import { LaboratoryForm, LabTestForm } from "@/features/lab/forms";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/session";
import type { Laboratory, LabTest } from "@/types/api";

export const metadata: Metadata = { title: "Laboratory tests" };

export default async function LabSetupPage() {
  await requirePermission("lab.configure");
  const [tests, laboratories] = await Promise.all([
    api<LabTest[]>("/laboratory-tests", { query: { include_inactive: true } }),
    api<Laboratory[]>("/laboratories", { query: { include_inactive: true } }),
  ]);
  return (
    <>
      <PageHeader title="Laboratory tests" description="The tests clinicians can tick when requesting, and the laboratories you send specimens to." />
      <div className="flex max-w-5xl flex-col gap-6">
        <Notice>Laboratory requests and results are handled manually: print the request form, and enter results from the laboratory’s report. No laboratory system is connected.</Notice>
        <section className="flex flex-col gap-3" aria-labelledby="tests-heading">
          <h2 id="tests-heading" className="text-md font-medium">Tests</h2>
          {tests.map((t) => <Panel key={t.id}><LabTestForm action={saveLabTest.bind(null, t.id)} item={t} /></Panel>)}
          <Panel title="Add test"><LabTestForm action={saveLabTest.bind(null, null)} /></Panel>
        </section>
        <section className="flex flex-col gap-3" aria-labelledby="labs-heading">
          <h2 id="labs-heading" className="text-md font-medium">Laboratories</h2>
          {laboratories.map((l) => <Panel key={l.id}><LaboratoryForm action={saveLaboratory.bind(null, l.id)} item={l} /></Panel>)}
          <Panel title="Add laboratory"><LaboratoryForm action={saveLaboratory.bind(null, null)} /></Panel>
        </section>
      </div>
    </>
  );
}
