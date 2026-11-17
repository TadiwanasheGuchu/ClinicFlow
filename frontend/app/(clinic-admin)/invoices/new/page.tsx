import type { Metadata } from "next";

import { PageHeader, Panel } from "@/components/ui/layout";
import { createInvoice } from "@/features/billing/actions";
import { NewInvoiceForm } from "@/features/billing/forms";
import { branchesFor } from "@/features/appointments/branch-choice";
import { api, ApiError } from "@/lib/api";
import { requirePermission } from "@/lib/session";
import type { Branch, Page, Patient, Service } from "@/types/api";

export const metadata: Metadata = { title: "New invoice" };

export default async function NewInvoicePage({ searchParams }: { searchParams: Promise<{ patient?: string }> }) {
  const { access } = await requirePermission("billing.manage");
  const { patient: patientId } = await searchParams;
  const [services, branches] = await Promise.all([api<Service[]>("/services"), api<Page<Branch>>("/branches", { query: { limit: 200 } })]);
  let patient: Patient | null = null;
  if (patientId) {
    try { patient = await api<Patient>(`/patients/${encodeURIComponent(patientId)}`); } catch (e) { if (!(e instanceof ApiError)) throw e; }
  }
  const { allowed } = branchesFor(access, "billing.manage", branches.items);
  return (
    <>
      <PageHeader title="New invoice" description="Saved as a draft. Lines can be changed until the invoice is issued." back={{ href: "/invoices", label: "Invoices" }} />
      <Panel><NewInvoiceForm action={createInvoice} services={services} branches={allowed.map((b) => ({ id: b.id, name: b.name }))} patient={patient} /></Panel>
    </>
  );
}
