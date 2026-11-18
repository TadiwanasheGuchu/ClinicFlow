import type { Metadata } from "next";

import { Input } from "@/components/ui/field";
import { Notice, PageHeader, Pagination } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { setTenantStatus } from "@/features/platform/actions";
import { TenantStatusControl } from "@/features/platform/tenant-status";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Page, Tenant } from "@/types/api";

export const metadata: Metadata = { title: "Platform" };

export default async function PlatformPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; offset?: string }>;
}) {
  const { q = "", offset: rawOffset } = await searchParams;
  const offset = Number(rawOffset ?? 0) || 0;
  const page = await api<Page<Tenant>>("/platform/organisations", {
    tenant: false,
    query: { q: q || undefined, offset, limit: 50 },
  });

  return (
    <>
      <PageHeader title="Platform" description="Registered organisations on this ClinicFlow installation." />
      <div className="mb-3">
        <Notice>
          Platform administration covers tenant status only. It gives no access to any
          organisation’s staff, patients or clinical records.
        </Notice>
      </div>
      <form className="mb-3 flex gap-2" role="search">
        <label className="sr-only" htmlFor="q">Search organisations</label>
        <Input id="q" name="q" defaultValue={q} placeholder="Search by name or email" className="w-72" />
        <button type="submit" className="h-9 rounded border border-border bg-surface px-3 text-base hover:bg-surface-muted">
          Search
        </button>
      </form>
      <Table>
        <THead>
          <tr>
            <TH>Organisation</TH>
            <TH>Contact</TH>
            <TH>Registered</TH>
            <TH>Status</TH>
            <TH align="right">Actions</TH>
          </tr>
        </THead>
        <tbody>
          {page.items.map((t) => (
            <TR key={t.id}>
              <TD className="font-medium">{t.name}</TD>
              <TD className="text-text-muted">{t.email ?? t.phone ?? "—"}</TD>
              <TD className="tabular">{formatDate(t.created_at)}</TD>
              <TD>
                <Status status={t.status} />
              </TD>
              <TD align="right">
                <TenantStatusControl
                  action={setTenantStatus.bind(null, t.id, t.status === "active" ? "suspended" : "active")}
                  name={t.name}
                  suspend={t.status === "active"}
                  approve={t.status === "pending"}
                />
              </TD>
            </TR>
          ))}
        </tbody>
      </Table>
      <Pagination
        total={page.total}
        limit={page.limit}
        offset={page.offset}
        href={(o) => `/platform?${new URLSearchParams({ offset: String(o), ...(q && { q }) })}`}
      />
    </>
  );
}
