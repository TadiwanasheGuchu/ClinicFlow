import type { Metadata } from "next";

import { Input, Select } from "@/components/ui/field";
import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { branchesFor } from "@/features/appointments/branch-choice";
import { api } from "@/lib/api";
import { METHOD, nad } from "@/lib/billing";
import { requirePermission } from "@/lib/session";
import { isISODate, longDate, timeOf, todayISO } from "@/lib/time";
import type { Branch, CashUp, Page } from "@/types/api";

export const metadata: Metadata = { title: "Cash-up" };

export default async function CashUpPage({ searchParams }: { searchParams: Promise<{ date?: string; branch?: string }> }) {
  const { access } = await requirePermission("billing.read");
  const params = await searchParams;
  const date = isISODate(params.date) ? params.date : todayISO();
  const branches = await api<Page<Branch>>("/branches", { query: { limit: 200 } });
  const { allowed, selected } = branchesFor(access, "billing.read", branches.items, params.branch);
  const report = await api<CashUp>("/billing/cash-up", { query: { date, branch_id: selected?.id } });

  return (
    <>
      <PageHeader title="Cash-up" description={`${longDate(date)}${selected ? ` · ${selected.name}` : ""}`} />
      <form className="mb-4 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm">Date<Input type="date" name="date" defaultValue={date} className="w-44" /></label>
        {allowed.length > 1 && <label className="flex flex-col gap-1 text-sm">Branch<Select name="branch" defaultValue={selected?.id} className="w-48">{allowed.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></label>}
        <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Show</button>
      </form>
      <div className="flex max-w-4xl flex-col gap-4">
        <Panel title="Totals by method">
          {report.by_method.length === 0 ? <p className="text-text-muted">No money received or refunded on this day.</p> : (
            <Table>
              <THead><tr><TH>Method</TH><TH align="right">Payments</TH><TH align="right">Received</TH><TH align="right">Refunded</TH><TH align="right">Net</TH></tr></THead>
              <tbody>
                {report.by_method.map((m) => (
                  <TR key={m.method}><TD>{METHOD[m.method] ?? m.method}</TD><TD align="right" mono>{m.count}</TD><TD align="right" mono>{nad(m.received)}</TD><TD align="right" mono>{nad(m.refunded)}</TD><TD align="right" mono>{nad(m.net)}</TD></TR>
                ))}
                <TR className="font-semibold"><TD>Total</TD><TD /><TD align="right" mono>{nad(report.total_received)}</TD><TD align="right" mono>{nad(report.total_refunded)}</TD><TD align="right" mono>{nad(report.net)}</TD></TR>
              </tbody>
            </Table>
          )}
        </Panel>
        <Panel title="Payments">
          {report.payments.length === 0 ? <EmptyState message="No payments." /> : (
            <Table>
              <THead><tr><TH>Time</TH><TH>Receipt</TH><TH>Method</TH><TH>Reference</TH><TH align="right">Amount</TH><TH>Status</TH></tr></THead>
              <tbody>
                {report.payments.map((p) => (
                  <TR key={p.id} className={p.status === "reversed" ? "text-text-muted" : undefined}>
                    <TD mono>{timeOf(p.received_at)}</TD><TD mono>{p.receipt_number}</TD><TD>{METHOD[p.method]}</TD><TD className="text-sm">{p.reference ?? "—"}</TD>
                    <TD align="right" mono>{nad(p.amount)}</TD><TD>{p.status === "reversed" ? <span className="text-danger-text">Reversed: {p.reversal_reason}</span> : "Completed"}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
