import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/layout";
import { Status } from "@/components/ui/status";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { Branch, Page, Weekday } from "@/types/api";

export const metadata: Metadata = { title: "Branches" };

const ORDER: Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function hoursSummary(branch: Branch) {
  const days = ORDER.filter((d) => branch.operating_hours[d]?.length);
  if (!days.length) return "Not set";
  return `${days.length} day${days.length === 1 ? "" : "s"} a week`;
}

export default async function BranchesPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; all?: string }>;
}) {
  const { access } = await requirePermission("branches.read");
  const params = await searchParams;
  const offset = Number(params.offset ?? 0) || 0;
  const all = params.all === "1";
  const page = await api<Page<Branch>>("/branches", {
    query: { offset, limit: 50, include_inactive: all },
  });
  const canCreate = hasOrgWide(access, "branches.manage");

  return (
    <>
      <PageHeader
        title="Branches"
        description="Practice locations, their contact details and opening hours."
        actions={canCreate && <ButtonLink href="/branches/new">Add branch</ButtonLink>}
      />
      <div className="mb-3 text-sm">
        <Link className="text-primary hover:underline" href={all ? "/branches" : "/branches?all=1"}>
          {all ? "Hide inactive branches" : "Show inactive branches"}
        </Link>
      </div>
      {page.items.length === 0 ? (
        <EmptyState message="No branches yet." />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Code</TH>
              <TH>Phone</TH>
              <TH>Opening hours</TH>
              <TH>Status</TH>
            </tr>
          </THead>
          <tbody>
            {page.items.map((b) => (
              <TR key={b.id}>
                <TD>
                  <Link href={`/branches/${b.id}`} className="font-medium text-primary hover:underline">
                    {b.name}
                  </Link>
                </TD>
                <TD mono>{b.branch_code}</TD>
                <TD className="tabular">{b.phone ?? "—"}</TD>
                <TD className="text-text-muted">{hoursSummary(b)}</TD>
                <TD>
                  <Status status={b.is_active ? "active" : "inactive"} />
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      <Pagination
        total={page.total}
        limit={page.limit}
        offset={page.offset}
        href={(o) => `/branches?offset=${o}${all ? "&all=1" : ""}`}
      />
    </>
  );
}
