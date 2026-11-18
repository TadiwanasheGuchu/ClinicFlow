import type { Metadata } from "next";

import { Field, Input, Select } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { cancelLeave, requestLeave } from "@/features/roster/actions";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { LEAVE_STATUS, LEAVE_TYPE, shortDay } from "@/lib/roster";
import { requireWorkspace } from "@/lib/session";
import { dateOf, timeOf, todayISO } from "@/lib/time";
import type { MyRoster } from "@/types/api";

export const metadata: Metadata = { title: "My shifts and leave" };

export default async function MyRosterPage() {
  await requireWorkspace();
  const today = todayISO();
  const mine = await api<MyRoster>("/me/roster", { query: { start: today, days: 14 } });
  return (
    <>
      <PageHeader title="My shifts and leave" description="Your shifts for the next two weeks, and your leave." />
      <div className="flex max-w-4xl flex-col gap-4">
        <Panel title="Next two weeks">
          {mine.shifts.length === 0 ? <p className="text-text-muted">No shifts rostered.</p> : (
            <Table>
              <THead><tr><TH>Day</TH><TH>Time</TH><TH>Branch</TH><TH>Duty</TH></tr></THead>
              <tbody>
                {mine.shifts.map((s) => (
                  <TR key={s.id}>
                    <TD>{shortDay(dateOf(s.starts_at))}</TD>
                    <TD mono>{timeOf(s.starts_at)}–{timeOf(s.ends_at)}</TD>
                    <TD className="text-text-muted">{mine.branch_names[s.branch_id]}</TD>
                    <TD>{s.duty ?? "—"}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        <Panel title="Request leave">
          <QuickForm action={requestLeave} submit="Request leave" reset>
            <Field id="lv-type" label="Type"><Select id="lv-type" name="leave_type" defaultValue="annual" className="w-48">{Object.entries(LEAVE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
            <Field id="lv-from" label="From" required><Input id="lv-from" name="starts_on" type="date" required min={today} className="w-40" /></Field>
            <Field id="lv-to" label="To (last day)"><Input id="lv-to" name="ends_on" type="date" min={today} className="w-40" /></Field>
            <Field id="lv-reason" label="Note for your manager"><Input id="lv-reason" name="reason" className="w-64" /></Field>
          </QuickForm>
        </Panel>
        <Panel title="My leave">
          {mine.leave.length === 0 ? <p className="text-text-muted">No leave recorded.</p> : (
            <Table>
              <THead><tr><TH>Dates</TH><TH>Type</TH><TH>Status</TH><TH align="right">Actions</TH></tr></THead>
              <tbody>
                {mine.leave.map((l) => (
                  <TR key={l.id}>
                    <TD className="tabular">{l.starts_on === l.ends_on ? formatDate(l.starts_on) : `${formatDate(l.starts_on)} – ${formatDate(l.ends_on)}`}</TD>
                    <TD>{l.leave_type && LEAVE_TYPE[l.leave_type]}</TD>
                    <TD>
                      {LEAVE_STATUS[l.status]}
                      {l.decision_note && <span className="block text-sm text-text-muted">“{l.decision_note}” — {l.decided_by_name}</span>}
                    </TD>
                    <TD align="right">
                      {(l.status === "requested" || (l.status === "approved" && l.starts_on > today)) && (
                        <QuickForm action={cancelLeave.bind(null, l.id)} submit="Cancel this leave" variant="secondary" className="justify-end" />
                      )}
                    </TD>
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
