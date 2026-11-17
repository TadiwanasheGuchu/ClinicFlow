"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { searchPatients } from "@/features/patients/actions";
import { formatDate } from "@/lib/format";
import type { PatientSummary } from "@/types/api";

/** Search-as-you-type patient chooser; posts the chosen id as `patient_id`. */
export function PatientPicker({ initial }: { initial: PatientSummary | null }) {
  const [selected, setSelected] = useState<PatientSummary | null>(initial);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PatientSummary[]>([]);
  const [, startTransition] = useTransition();

  useEffect(() => {
    const handle = setTimeout(() => startTransition(async () => setResults(await searchPatients(q))), 250);
    return () => clearTimeout(handle);
  }, [q]);

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-sm border border-border bg-surface-muted px-3 py-2">
        <input type="hidden" name="patient_id" value={selected.id} />
        <span>
          <span className="font-medium">{selected.first_name} {selected.last_name}</span>
          <span className="text-text-muted"> · born {formatDate(selected.date_of_birth)} · </span>
          <span className="font-mono text-sm">{selected.patient_number}</span>
        </span>
        <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Change</Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Input aria-label="Search patients" placeholder="Name, patient number, date of birth or phone" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {results.length > 0 && (
        <ul className="rounded-sm border border-border bg-surface" role="listbox" aria-label="Matching patients">
          {results.map((p) => (
            <li key={p.id}>
              <button type="button" className="flex w-full justify-between gap-3 px-3 py-2 text-left hover:bg-primary-subtle" onClick={() => setSelected(p)}>
                <span><span className="font-medium">{p.last_name}, {p.first_name}</span> <span className="text-text-muted">· born {formatDate(p.date_of_birth)}</span></span>
                <span className="font-mono text-sm">{p.patient_number}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim().length >= 2 && results.length === 0 && <p className="text-sm text-text-muted">No match. <Link href="/patients/new" className="text-primary underline">Register a new patient</Link></p>}
    </div>
  );
}
