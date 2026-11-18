"use client";

import { Plus, X } from "lucide-react";
import { useActionState, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { ActionForm, FormMessage, SubmitButton } from "@/components/ui/form";
import { MEASURE_LABEL } from "@/lib/dental";
import { type FormState, initialFormState } from "@/lib/form";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

export function MeasurementForm({ action, encounters, presets }: {
  action: Action; encounters: { id: string; label: string }[]; presets: { measure: string; label: string; side: string | null }[];
}) {
  const [state, formAction, pending] = useActionState(action, initialFormState);
  const start = () =>
    presets.length ? presets.map((p, i) => ({ k: i, ...p })) : [{ k: 0, measure: "pain_nrs", label: "Pain", side: null as string | null }];
  const [rows, setRows] = useState(start);
  const [key, setKey] = useState(0);
  // Refill with the measures being tracked and remount in one update, so the new default
  // values (labels, sides) are applied to fresh inputs.
  useEffect(() => {
    if (state.success) {
      setRows(start());
      setKey((k) => k + 1);
    }
  }, [state]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <ActionForm key={key} action={formAction} pending={pending} className="flex flex-col gap-3">
      <FormMessage state={state} />
      <Field id="m-enc" label="Consultation (session)" required>
        <Select id="m-enc" name="encounter_id" required className="w-72">{encounters.map((e) => <option key={e.id} value={e.id}>{e.label}</option>)}</Select>
      </Field>
      {rows.map((r, i) => (
        <div key={r.k} className="flex flex-wrap items-end gap-3">
          <Field id={`mm-${r.k}`} label="Measure">
            <Select id={`mm-${r.k}`} name={`m.${r.k}.measure`} defaultValue={r.measure} className="w-52">{Object.entries(MEASURE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          </Field>
          <Field id={`ml-${r.k}`} label="What"><Input id={`ml-${r.k}`} name={`m.${r.k}.label`} defaultValue={r.label} placeholder="e.g. Shoulder flexion" className="w-52" /></Field>
          <Field id={`ms-${r.k}`} label="Side">
            <Select id={`ms-${r.k}`} name={`m.${r.k}.side`} defaultValue={r.side ?? ""} className="w-28"><option value="">—</option><option value="left">Left</option><option value="right">Right</option><option value="both">Both</option></Select>
          </Field>
          <Field id={`mv-${r.k}`} label="Value"><Input id={`mv-${r.k}`} name={`m.${r.k}.value`} inputMode="decimal" className="w-24 text-right font-mono" /></Field>
          <Field id={`mu-${r.k}`} label="Unit" hint="Other only"><Input id={`mu-${r.k}`} name={`m.${r.k}.unit`} className="w-20" /></Field>
          {rows.length > 1 && <Button variant="ghost" size="sm" onClick={() => setRows((x) => x.filter((y) => y.k !== r.k))} aria-label={`Remove measurement ${i + 1}`}><X size={16} strokeWidth={1.5} aria-hidden /></Button>}
        </div>
      ))}
      <div><Button variant="ghost" size="sm" onClick={() => setRows((x) => [...x, { k: Math.max(...x.map((y) => y.k)) + 1, measure: "rom", label: "", side: null }])}><Plus size={16} strokeWidth={1.5} aria-hidden /> Add measurement</Button></div>
      <div><SubmitButton>Record measurements</SubmitButton></div>
    </ActionForm>
  );
}
