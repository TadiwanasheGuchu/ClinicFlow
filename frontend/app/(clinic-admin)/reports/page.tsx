import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { Input, Select } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { branchesFor } from "@/features/appointments/branch-choice";
import { api } from "@/lib/api";
import { CLAIM_STATUS, METHOD, nad } from "@/lib/billing";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { hasPermission, requireWorkspace } from "@/lib/session";
import { addDays, isISODate, todayISO } from "@/lib/time";
import type { Branch, FinancialReport, OperationalReport, Page } from "@/types/api";

export const metadata: Metadata = { title: "Reports" };

const AGED: Record<string, string> = { not_due: "Not yet due", "1_30": "1–30 days overdue", "31_60": "31–60 days overdue", "61_90": "61–90 days overdue", over_90: "Over 90 days overdue" };

function presets(today: string): [string, string, string][] {
  const [y, m] = today.split("-").map(Number) as [number, number];
  const firstThis = `${y}-${String(m).padStart(2, "0")}-01`;
  const lastPrev = addDays(firstThis, -1);
  const firstPrev = `${lastPrev.slice(0, 7)}-01`;
  return [["This month", firstThis, today], ["Last month", firstPrev, lastPrev], ["Last 7 days", addDays(today, -6), today], ["Last 30 days", addDays(today, -29), today]];
}

const pct = (v: string | null) => (v === null ? "—" : `${Number(v).toFixed(1)}%`);

function Figures({ items }: { items: [string, ReactNode][] }) {
  // A single compact row of figures (not cards): label above value.
  return (
    <dl className="mb-4 flex flex-wrap gap-x-8 gap-y-2 border-b border-border pb-4">
      {items.map(([label, value]) => (
        <div key={label}><dt className="text-xs text-text-muted">{label}</dt><dd className="font-mono text-md">{value}</dd></div>
      ))}
    </dl>
  );
}

export default async function ReportsPage({ searchParams }: { searchParams: Promise<{ view?: string; start?: string; end?: string; branch?: string }> }) {
  const { access } = await requireWorkspace();
  const canOps = hasPermission(access, "reports.operational");
  const canFin = hasPermission(access, "reports.financial");
  if (!canOps && !canFin) redirect("/not-permitted");
  const params = await searchParams;
  const view = params.view === "financial" && canFin ? "financial" : canOps ? "operational" : "financial";
  const today = todayISO();
  const ranges = presets(today);
  const start = isISODate(params.start) ? params.start : ranges[0]![1];
  const end = isISODate(params.end) ? params.end : ranges[0]![2];
  const permission = `reports.${view}`;
  const branches = await api<Page<Branch>>("/branches", { query: { limit: 200 } });
  const { allowed } = branchesFor(access, permission, branches.items);
  const branch = allowed.find((b) => b.id === params.branch);
  const query = { start, end, branch_id: branch?.id };
  const link = (patch: Record<string, string>) => `/reports?${new URLSearchParams({ view, start, end, ...(branch && { branch: branch.id }), ...patch })}`;

  return (
    <>
      <PageHeader title="Reports" description={`${formatDate(`${start}T12:00:00Z`)} to ${formatDate(`${end}T12:00:00Z`)}${branch ? ` · ${branch.name}` : " · all branches you can see"}`} />
      <nav aria-label="Report" className="mb-3 flex gap-1">
        {canOps && <Link href={link({ view: "operational" })} aria-current={view === "operational" ? "page" : undefined} className={cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", view === "operational" ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted")}>Operational</Link>}
        {canFin && <Link href={link({ view: "financial" })} aria-current={view === "financial" ? "page" : undefined} className={cn("inline-flex h-8 items-center rounded-sm border px-3 text-sm", view === "financial" ? "border-primary bg-primary-subtle font-medium text-primary" : "border-border bg-surface hover:bg-surface-muted")}>Financial</Link>}
      </nav>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-1">
          {ranges.map(([label, s, e]) => (
            <Link key={label} href={link({ start: s, end: e })} className={cn("inline-flex h-8 items-center rounded-sm border px-2.5 text-sm", s === start && e === end ? "border-primary text-primary" : "border-border bg-surface hover:bg-surface-muted")}>{label}</Link>
          ))}
        </div>
        <form className="flex flex-wrap items-end gap-2">
          <input type="hidden" name="view" value={view} />
          <label className="flex flex-col gap-1 text-xs text-text-muted">From<Input type="date" name="start" defaultValue={start} className="w-40" /></label>
          <label className="flex flex-col gap-1 text-xs text-text-muted">To<Input type="date" name="end" defaultValue={end} className="w-40" /></label>
          {allowed.length > 1 && (
            <label className="flex flex-col gap-1 text-xs text-text-muted">Branch
              <Select name="branch" defaultValue={branch?.id ?? ""} className="w-48"><option value="">All</option>{allowed.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
            </label>
          )}
          <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Show</button>
        </form>
      </div>
      {view === "operational" ? <Operational r={await api<OperationalReport>("/reports/operational", { query })} /> : <Financial r={await api<FinancialReport>("/reports/financial", { query })} />}
    </>
  );
}

function Operational({ r }: { r: OperationalReport }) {
  return (
    <div className="flex max-w-6xl flex-col gap-4">
      <Panel>
        <Figures items={[
          ["Appointments", r.totals.booked], ["Completed", r.totals.completed], ["Cancelled", `${r.totals.cancelled} (${pct(r.cancellation_rate_percent)})`],
          ["No-shows", `${r.totals.no_show} (${pct(r.no_show_rate_percent)})`], ["Average wait", r.average_wait_minutes ? `${Number(r.average_wait_minutes).toFixed(0)} min` : "—"],
          ["New patients", r.new_patients], ["Consultations", r.consultations],
        ]} />
        <p className="text-xs text-text-muted">No-show rate is out of appointments that were due to attend (completed + no-show). Average wait is from check-in to the start of the consultation ({r.wait_sample} visits).</p>
      </Panel>
      <Panel title="Practitioners">
        <Table>
          <THead><tr><TH>Practitioner</TH><TH align="right">Booked</TH><TH align="right">Completed</TH><TH align="right">No-shows</TH><TH align="right">Booked hours</TH><TH align="right">Scheduled hours</TH><TH align="right">Utilisation</TH></tr></THead>
          <tbody>{r.by_provider.map((p) => (
            <TR key={p.provider_id}><TD>{p.provider_name}</TD><TD align="right" mono>{p.booked}</TD><TD align="right" mono>{p.completed}</TD><TD align="right" mono>{p.no_show}</TD>
              <TD align="right" mono>{(p.booked_minutes / 60).toFixed(1)}</TD><TD align="right" mono>{(p.available_minutes / 60).toFixed(1)}</TD><TD align="right" mono>{pct(p.utilisation_percent)}</TD></TR>
          ))}</tbody>
        </Table>
      </Panel>
      {r.by_branch.length > 1 && (
        <Panel title="Branches">
          <Table>
            <THead><tr><TH>Branch</TH><TH align="right">Booked</TH><TH align="right">Completed</TH><TH align="right">Cancelled</TH><TH align="right">No-shows</TH></tr></THead>
            <tbody>{r.by_branch.map((b) => <TR key={b.branch_id}><TD>{b.branch_name}</TD><TD align="right" mono>{b.booked}</TD><TD align="right" mono>{b.completed}</TD><TD align="right" mono>{b.cancelled}</TD><TD align="right" mono>{b.no_show}</TD></TR>)}</tbody>
          </Table>
        </Panel>
      )}
      <Panel title="By day">
        <Table>
          <THead><tr><TH>Date</TH><TH align="right">Booked</TH><TH align="right">Completed</TH><TH align="right">Cancelled</TH><TH align="right">No-shows</TH><TH align="right">Walk-ins</TH><TH align="right">Online</TH></tr></THead>
          <tbody>{r.daily.map((d) => (
            <TR key={d.date} className={d.booked === 0 ? "text-text-muted" : undefined}><TD className="tabular">{formatDate(`${d.date}T12:00:00Z`)}</TD><TD align="right" mono>{d.booked}</TD><TD align="right" mono>{d.completed}</TD><TD align="right" mono>{d.cancelled}</TD><TD align="right" mono>{d.no_show}</TD><TD align="right" mono>{d.walk_in}</TD><TD align="right" mono>{d.online}</TD></TR>
          ))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}

function MoneyTable({ rows, keyLabel, countLabel, label }: { rows: { key: string; label: string; count: number; amount: string }[]; keyLabel: string; countLabel: string; label?: (r: { key: string; label: string }) => string }) {
  if (!rows.length) return <p className="text-text-muted">Nothing in this period.</p>;
  return (
    <Table>
      <THead><tr><TH>{keyLabel}</TH><TH align="right">{countLabel}</TH><TH align="right">Amount</TH></tr></THead>
      <tbody>{rows.map((r) => <TR key={r.key}><TD>{label ? label(r) : r.label}</TD><TD align="right" mono>{r.count}</TD><TD align="right" mono>{nad(r.amount)}</TD></TR>)}</tbody>
    </Table>
  );
}

function Financial({ r }: { r: FinancialReport }) {
  return (
    <div className="flex max-w-6xl flex-col gap-4">
      <Panel>
        <Figures items={[
          ["Invoiced", nad(r.invoiced)], ["Invoices", r.invoice_count], ["Credited", nad(r.credited)], ["Collected", nad(r.collected)],
          ["Refunded", nad(r.refunded)], ["Net collected", nad(r.net_collected)], ["Outstanding now", nad(r.outstanding_total)], ["With medical aids", nad(r.claims_outstanding)],
        ]} />
        <p className="text-xs text-text-muted">Invoiced counts invoices issued in the period; collected counts payments received in the period, including medical aid payments. Outstanding is today’s balance across all open invoices.</p>
      </Panel>
      <Panel title={r.series.length && r.series[0]!.period.length === 7 ? "By month" : "By day"}>
        {r.series.length ? (
          <Table>
            <THead><tr><TH>Period</TH><TH align="right">Invoiced</TH><TH align="right">Collected</TH><TH align="right">Refunded</TH></tr></THead>
            <tbody>{r.series.map((s) => <TR key={s.period}><TD className="tabular">{s.period.length === 7 ? new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${s.period}-15T12:00:00Z`)) : formatDate(`${s.period}T12:00:00Z`)}</TD><TD align="right" mono>{nad(s.invoiced)}</TD><TD align="right" mono>{nad(s.collected)}</TD><TD align="right" mono>{nad(s.refunded)}</TD></TR>)}</tbody>
          </Table>
        ) : <p className="text-text-muted">Nothing in this period.</p>}
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Collected by method"><MoneyTable rows={r.collected_by_method} keyLabel="Method" countLabel="Payments" label={(x) => METHOD[x.key] ?? x.key} /></Panel>
        <Panel title="Outstanding by age">
          <Table>
            <THead><tr><TH>Age</TH><TH align="right">Invoices</TH><TH align="right">Amount</TH></tr></THead>
            <tbody>{r.aged_debt.map((a) => <TR key={a.bucket} className={a.bucket === "over_90" && a.invoices ? "text-danger-text" : undefined}><TD>{AGED[a.bucket] ?? a.bucket}</TD><TD align="right" mono>{a.invoices}</TD><TD align="right" mono>{nad(a.amount)}</TD></TR>)}</tbody>
          </Table>
          <p className="mt-2 text-sm"><Link className="text-primary hover:underline" href="/invoices?status=outstanding">Open invoices</Link></p>
        </Panel>
        <Panel title="Revenue by service"><MoneyTable rows={r.revenue_by_service} keyLabel="Service" countLabel="Lines" /></Panel>
        <Panel title="Revenue by practitioner"><MoneyTable rows={r.revenue_by_provider} keyLabel="Practitioner" countLabel="Invoices" /></Panel>
      </div>
      <Panel title="Medical aid claims" description={`Rejection rate in this period: ${pct(r.claim_rejection_rate_percent)} of fund responses.`}>
        {r.claims.length ? (
          <Table>
            <THead><tr><TH>Status</TH><TH align="right">Claims</TH><TH align="right">Claimed</TH><TH align="right">Paid by funds</TH></tr></THead>
            <tbody>{r.claims.map((c) => <TR key={c.status}><TD>{CLAIM_STATUS[c.status]}</TD><TD align="right" mono>{c.count}</TD><TD align="right" mono>{nad(c.claimed)}</TD><TD align="right" mono>{nad(c.paid)}</TD></TR>)}</tbody>
          </Table>
        ) : <p className="text-text-muted">No claims.</p>}
      </Panel>
    </div>
  );
}
