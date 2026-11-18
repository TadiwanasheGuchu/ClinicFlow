import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/layout";
import { QuickForm } from "@/components/ui/quick-form";
import { addShift, cancelShift, copyWeek } from "@/features/roster/actions";
import { api } from "@/lib/api";
import { humanise } from "@/lib/format";
import { LEAVE_TYPE, mondayOf, shortDay } from "@/lib/roster";
import { requirePermission } from "@/lib/session";
import { addDays, dateOf, isISODate, timeOf, todayISO } from "@/lib/time";
import type { Branch, Page, Roster } from "@/types/api";

export const metadata: Metadata = { title: "Roster" };

export default async function RosterPage({ searchParams }: { searchParams: Promise<{ week?: string; branch?: string }> }) {
  const { access } = await requirePermission("roster.read");
  const params = await searchParams;
  const week = mondayOf(isISODate(params.week) ? params.week : todayISO());
  const branches = (await api<Page<Branch>>("/branches", { query: { limit: 200 } })).items.filter((b) =>
    access.grants.some((g) => g.permission === "roster.read" && (g.branch_id === null || g.branch_id === b.id)),
  );
  const branch = branches.find((b) => b.id === params.branch) ?? branches[0];
  if (!branch) return <PageHeader title="Roster" description="You don't have access to any branch roster." />;
  const roster = await api<Roster>("/roster", { query: { branch_id: branch.id, start: week, days: 7 } });
  const canManage = access.grants.some((g) => g.permission === "roster.manage" && (g.branch_id === null || g.branch_id === branch.id));
  const days = Array.from({ length: 7 }, (_, i) => addDays(week, i));
  const today = todayISO();
  const link = (w: string) => `/roster?${new URLSearchParams({ week: w, branch: branch.id })}`;

  return (
    <>
      <PageHeader
        title="Roster"
        description={`${branch.name} · week of ${shortDay(week)} ${week.slice(0, 4)}`}
        actions={canManage && <ButtonLink variant="secondary" href="/roster/leave">Leave requests</ButtonLink>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <nav aria-label="Week" className="flex gap-1">
          <Link className="inline-flex h-8 items-center rounded-sm border border-border bg-surface px-3 text-sm hover:bg-surface-muted" href={link(addDays(week, -7))}>Previous week</Link>
          <Link className="inline-flex h-8 items-center rounded-sm border border-border bg-surface px-3 text-sm hover:bg-surface-muted" href={link(mondayOf(today))}>This week</Link>
          <Link className="inline-flex h-8 items-center rounded-sm border border-border bg-surface px-3 text-sm hover:bg-surface-muted" href={link(addDays(week, 7))}>Next week</Link>
        </nav>
        {branches.length > 1 && (
          <form className="flex items-center gap-2">
            <input type="hidden" name="week" value={week} />
            <label htmlFor="branch" className="text-sm text-text-muted">Branch</label>
            <Select id="branch" name="branch" defaultValue={branch.id} className="w-44">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select>
            <button type="submit" className="h-9 rounded border border-border bg-surface px-3 hover:bg-surface-muted">Show</button>
          </form>
        )}
      </div>

      <div className="overflow-x-auto rounded border border-border bg-surface">
        <table className="w-full min-w-[56rem] border-collapse text-base">
          <thead className="sticky top-0 bg-surface-muted text-left text-xs font-medium tracking-wide text-text-muted uppercase">
            <tr>
              <th scope="col" className="w-48 border-b border-border px-3 py-2">Staff</th>
              {days.map((d) => (
                <th key={d} scope="col" className="border-b border-l border-border px-2 py-2">
                  {shortDay(d)}{d === today && <span className="ml-1 normal-case text-primary">· today</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roster.staff.map((person) => (
              <tr key={person.membership_id} className="align-top">
                <th scope="row" className="border-b border-border px-3 py-2 text-left font-normal">
                  <span className="font-medium">{person.name}</span>
                  <span className="block text-sm text-text-muted">
                    {person.profession ? humanise(person.profession) : "Staff"} · <span className="font-mono">{roster.hours[person.membership_id] ?? 0}</span> h
                  </span>
                </th>
                {days.map((d) => {
                  const shifts = roster.shifts.filter((s) => s.membership_id === person.membership_id && dateOf(s.starts_at) === d);
                  const leave = roster.leave.find((l) => l.membership_id === person.membership_id && l.starts_on <= d && l.ends_on >= d);
                  return (
                    <td key={d} className="border-b border-l border-border px-2 py-1.5 text-sm">
                      {leave && (
                        <p className={leave.status === "approved" ? "font-medium text-warning-text" : "text-text-muted"}>
                          {leave.status === "approved" ? "On leave" : "Leave requested"}
                          {leave.leave_type && <span className="block text-xs">{LEAVE_TYPE[leave.leave_type]}</span>}
                        </p>
                      )}
                      {shifts.map((s) => (
                        <div key={s.id} className="mb-1 rounded-sm border border-border bg-surface-muted px-1.5 py-1">
                          <span className="font-mono">{timeOf(s.starts_at)}–{timeOf(s.ends_at)}</span>
                          {s.duty && <span className="block text-xs text-text-muted">{s.duty}</span>}
                          {canManage && (
                            <QuickForm action={cancelShift.bind(null, s.id)} submit={<span>Remove<span className="sr-only"> {person.name}’s shift on {shortDay(d)}</span></span>} variant="secondary" pendingLabel="…" className="mt-1 [&_button]:h-6 [&_button]:px-1.5 [&_button]:text-xs" />
                          )}
                        </div>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage && (
        <div className="mt-6 flex max-w-5xl flex-col gap-4">
          <Panel title="Add shift" description="If the end is earlier than the start, the shift ends the next day.">
            <QuickForm action={addShift} submit="Add shift">
              <input type="hidden" name="branch_id" value={branch.id} />
              <Field id="sh-member" label="Staff member" required>
                <Select id="sh-member" name="membership_id" required className="w-56"><option value="">Choose…</option>{roster.staff.map((p) => <option key={p.membership_id} value={p.membership_id}>{p.name}</option>)}</Select>
              </Field>
              <Field id="sh-date" label="Day" required>
                <Select id="sh-date" name="date" required className="w-40">{days.map((d) => <option key={d} value={d}>{shortDay(d)}</option>)}</Select>
              </Field>
              <Field id="sh-start" label="From" required><Input id="sh-start" name="start" type="time" required defaultValue="08:00" className="w-36" /></Field>
              <Field id="sh-end" label="To" required><Input id="sh-end" name="end" type="time" required defaultValue="17:00" className="w-36" /></Field>
              <Field id="sh-duty" label="Duty"><Input id="sh-duty" name="duty" placeholder="e.g. Reception" className="w-44" /></Field>
            </QuickForm>
          </Panel>
          <Panel title="Repeat a week" description="Copies last week's shifts into this week. Shifts that would clash with existing shifts or approved leave are skipped.">
            <QuickForm action={copyWeek.bind(null, branch.id, addDays(week, -7), week)} submit={`Copy week of ${shortDay(addDays(week, -7))} into this week`} variant="secondary" />
          </Panel>
        </div>
      )}
    </>
  );
}
