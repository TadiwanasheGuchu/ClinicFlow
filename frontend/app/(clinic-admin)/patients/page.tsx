import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import { ageOf } from "@/lib/time";
import type { Page, PatientSummary } from "@/types/api";

export const metadata: Metadata = { title: "Patients" };

export default async function PatientsPage({ searchParams }: { searchParams: Promise<{ q?: string; offset?: string }> }) {
  const { access } = await requirePermission("patients.read");
  const { q = "", offset: rawOffset } = await searchParams;
  const offset = Number(rawOffset ?? 0) || 0;
  const page = await api<Page<PatientSummary>>("/patients", { query: { q: q || undefined, offset, limit: 50 } });

  return (
    <>
      <PageHeader
        title="Patients"
        description="Search by name, patient number, date of birth (DD/MM/YYYY) or phone number."
        actions={hasPermission(access, "patients.write") && <ButtonLink href="/patients/new">Register patient</ButtonLink>}
      />
      <form className="mb-3 flex gap-2" role="search">
        <label className="sr-only" htmlFor="q">Search patients</label>
        <Input id="q" name="q" defaultValue={q} placeholder="e.g. Shikongo, P-000231, 12/04/1990" className="w-80" autoFocus />
        <button type="submit" className="h-9 rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted">Search</button>
      </form>
      {page.items.length === 0 ? (
        <EmptyState message={q ? `No patients match “${q}”.` : "No patients registered yet."} action={hasPermission(access, "patients.write") && <ButtonLink href="/patients/new" variant="secondary">Register patient</ButtonLink>} />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Patient</TH>
              <TH>Number</TH>
              <TH>Date of birth</TH>
              <TH>Phone</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <tbody>
            {page.items.map((p) => (
              <TR key={p.id}>
                <TD>
                  <Link href={`/patients/${p.id}`} className="font-medium text-primary hover:underline">
                    {p.last_name}, {p.first_name}
                  </Link>
                </TD>
                <TD mono>{p.patient_number}</TD>
                <TD className="tabular">
                  {formatDate(p.date_of_birth)} <span className="text-text-muted">({ageOf(p.date_of_birth)} y)</span>
                </TD>
                <TD className="tabular">{p.phone ?? "—"}</TD>
                <TD><Status status={p.status === "active" ? "active" : "inactive"} /></TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={(o) => `/patients?${new URLSearchParams({ offset: String(o), ...(q && { q }) })}`} />
    </>
  );
}
