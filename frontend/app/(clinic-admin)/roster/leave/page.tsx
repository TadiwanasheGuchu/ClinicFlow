import type { Metadata } from "next";

import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState, Notice, PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { SubmitButton } from "@/components/ui/form";
import { cancelLeave, decideLeave, recordLeave } from "@/features/roster/actions";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { LEAVE_TYPE } from "@/lib/roster";
import { requirePermission } from "@/lib/session";
import type { Leave, Member, Page } from "@/types/api";

export const metadata: Metadata = { title: "Leave requests" };

const span = (l: Leave) => (l.starts_on === l.ends_on ? formatDate(l.starts_on) : `${formatDate(l.starts_on)} – ${formatDate(l.ends_on)}`);

const count = (value: string | undefined) => Math.max(0, Math.min(9999, Number.parseInt(value ?? "0", 10) || 0));

function DecisionNotice({ params }: { params: { decided?: string; appointments?: string; shifts?: string } }) {
  if (params.decided !== "approved" && params.decided !== "declined") return null;
  if (params.decided === "declined") return <Notice tone="success">Leave declined.</Notice>;
  const appointments = count(params.appointments);
  const shifts = count(params.shifts);
  return (
    <Notice tone={appointments || shifts ? "info" : "success"}>
      <p>Leave approved.</p>
      {appointments > 0 && <p className="font-medium">{appointments} booked appointment{appointments === 1 ? " needs" : "s need"} rebooking in this period. They were not cancelled.</p>}
      {shifts > 0 && <p className="font-medium">{shifts} rostered shift{shifts === 1 ? " needs" : "s need"} cover in this period.</p>}
    </Notice>
  );
}

export default async function LeavePage({ searchParams }: { searchParams: Promise<{ decided?: string; appointments?: string; shifts?: string }> }) {
  const { me } = await requirePermission("roster.manage");
  const params = await searchParams;
  const [pending, upcoming, members] = await Promise.all([
    api<Leave[]>("/leave", { query: { status: "requested" } }),
    api<Leave[]>("/leave", { query: { status: "upcoming" } }),
    api<Page<Member>>("/members", { query: { limit: 200 } }),
  ]);
  const active = members.items.filter((m) => m.status === "active");
  return (
    <>
      <PageHeader title="Leave requests" description="Approved leave for a practitioner also blocks their online and reception bookings." back={{ href: "/roster", label: "Roster" }} />
      <div className="flex max-w-5xl flex-col gap-4">
        <DecisionNotice params={params} />
        <Panel title="Waiting for a decision">
          {pending.length === 0 ? <EmptyState message="No leave requests waiting." /> : (
            <div className="flex flex-col gap-3">
              {pending.map((l) => (
                <article key={l.id} className="rounded border border-border p-3">
                  <p className="font-medium">{l.staff_name} <span className="font-normal text-text-muted">· {l.leave_type && LEAVE_TYPE[l.leave_type]} · {span(l)}</span></p>
                  {l.reason && <p className="mt-1 text-sm text-text-muted">“{l.reason}”</p>}
                  <div className="mt-2">
                    <QuickForm action={decideLeave.bind(null, l.id)}>
                      <Field id={`note-${l.id}`} label="Note to staff member"><Input id={`note-${l.id}`} name="note" className="w-64" /></Field>
                      <SubmitButton name="decision" value="approved">Approve {l.staff_name}’s leave</SubmitButton>
                      <SubmitButton name="decision" value="declined" variant="secondary">Decline</SubmitButton>
                    </QuickForm>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Approved, upcoming">
          {upcoming.length === 0 ? <p className="text-text-muted">None.</p> : (
            <Table>
              <THead><tr><TH>Staff member</TH><TH>Dates</TH><TH>Type</TH><TH>Bookings</TH><TH align="right">Actions</TH></tr></THead>
              <tbody>
                {upcoming.map((l) => (
                  <TR key={l.id}>
                    <TD>{l.staff_name}</TD>
                    <TD className="tabular">{span(l)}</TD>
                    <TD>{l.leave_type && LEAVE_TYPE[l.leave_type]}</TD>
                    <TD className="text-text-muted">{l.blocks_bookings ? "Blocked" : "—"}</TD>
                    <TD align="right"><QuickForm action={cancelLeave.bind(null, l.id)} submit={`Cancel ${l.staff_name}’s leave`} variant="secondary" className="justify-end" /></TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
        <Panel title="Record leave" description="For leave arranged by phone, such as sick leave. It is recorded as approved.">
          <QuickForm action={recordLeave} submit="Record leave" reset>
            <Field id="rl-member" label="Staff member" required>
              <Select id="rl-member" name="membership_id" required className="w-56">
                <option value="">Choose…</option>
                {active.filter((m) => m.user_id !== me.id).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </Select>
            </Field>
            <Field id="rl-type" label="Type"><Select id="rl-type" name="leave_type" defaultValue="sick" className="w-48">{Object.entries(LEAVE_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
            <Field id="rl-from" label="From" required><Input id="rl-from" name="starts_on" type="date" required className="w-40" /></Field>
            <Field id="rl-to" label="To"><Input id="rl-to" name="ends_on" type="date" className="w-40" /></Field>
          </QuickForm>
        </Panel>
      </div>
    </>
  );
}
