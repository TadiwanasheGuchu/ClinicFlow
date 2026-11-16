import type { Metadata } from "next";

import { Input } from "@/components/ui/field";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime, humanise, shortId } from "@/lib/format";
import { hasPermission, requirePermission } from "@/lib/session";
import type { AuditEntry, Member, Page } from "@/types/api";

export const metadata: Metadata = { title: "Audit log" };

const WINDHOEK_OFFSET = "+02:00";

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; action?: string; resource_type?: string; from?: string; to?: string }>;
}) {
  const { access } = await requirePermission("audit.read");
  const { offset: rawOffset, action = "", resource_type = "", from = "", to = "" } = await searchParams;
  const offset = Number(rawOffset ?? 0) || 0;
  const isDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v);

  const page = await api<Page<AuditEntry>>("/audit-logs", {
    query: {
      offset,
      limit: 50,
      action: action || undefined,
      resource_type: resource_type || undefined,
      since: isDate(from) ? `${from}T00:00:00${WINDHOEK_OFFSET}` : undefined,
      until: isDate(to) ? `${to}T23:59:59${WINDHOEK_OFFSET}` : undefined,
    },
  });

  // Resolve actor names where the viewer may see staff.
  const names = new Map<string, string>();
  if (hasPermission(access, "members.read")) {
    const members = await api<Page<Member>>("/members", { query: { limit: 200 } });
    for (const m of members.items) names.set(m.user_id, m.full_name);
  }
  const qs = (o: number) =>
    `/audit?${new URLSearchParams({ offset: String(o), ...(action && { action }), ...(resource_type && { resource_type }), ...(from && { from }), ...(to && { to }) })}`;

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every sensitive change and denied access attempt. Entries can’t be edited or deleted."
      />
      <form className="mb-3 flex flex-wrap items-end gap-2" role="search">
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Action
          <Input name="action" defaultValue={action} placeholder="e.g. member.suspended" className="w-56 font-mono text-sm" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Resource
          <Input name="resource_type" defaultValue={resource_type} placeholder="e.g. branch" className="w-40 font-mono text-sm" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          From
          <Input type="date" name="from" defaultValue={from} className="w-40" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          To
          <Input type="date" name="to" defaultValue={to} className="w-40" />
        </label>
        <button type="submit" className="h-9 rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted">
          Filter
        </button>
      </form>
      {page.items.length === 0 ? (
        <EmptyState message="No audit entries match these filters." />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Time</TH>
              <TH>Action</TH>
              <TH>By</TH>
              <TH>Resource</TH>
              <TH>Details</TH>
              <TH>Request</TH>
            </tr>
          </THead>
          <tbody>
            {page.items.map((e) => (
              <TR key={e.id} className="align-top">
                <TD className="tabular whitespace-nowrap">{formatDateTime(e.timestamp)}</TD>
                <TD>
                  <span className={e.action === "access.denied" ? "font-medium text-danger-text" : undefined}>
                    {humanise(e.action)}
                  </span>
                </TD>
                <TD>
                  {e.actor_user_id ? (names.get(e.actor_user_id) ?? <span className="font-mono text-sm">{shortId(e.actor_user_id)}</span>) : "System"}
                </TD>
                <TD>
                  <span className="text-text-muted">{e.resource_type}</span>{" "}
                  <span className="font-mono text-sm">{shortId(e.resource_id)}</span>
                </TD>
                <TD>
                  {Object.keys(e.details).length > 0 ? (
                    <details>
                      <summary className="cursor-pointer text-sm text-primary">View</summary>
                      <pre className="mt-1 max-w-md overflow-x-auto rounded-sm bg-surface-muted p-2 font-mono text-xs">
                        {JSON.stringify(e.details, null, 2)}
                      </pre>
                    </details>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD mono className="text-text-muted">
                  {e.request_id ? e.request_id.slice(0, 12) : "—"}
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination total={page.total} limit={page.limit} offset={page.offset} href={qs} />
    </>
  );
}
