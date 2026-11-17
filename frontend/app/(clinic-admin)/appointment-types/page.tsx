import type { Metadata } from "next";

import { EmptyState, PageHeader, Panel } from "@/components/ui/layout";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { createAppointmentType, updateAppointmentType } from "@/features/scheduling/actions";
import { AppointmentTypeForm } from "@/features/scheduling/forms";
import { api } from "@/lib/api";
import { formatNAD } from "@/lib/format";
import { hasOrgWide, requirePermission } from "@/lib/session";
import type { AppointmentType } from "@/types/api";

export const metadata: Metadata = { title: "Appointment types" };

export default async function AppointmentTypesPage() {
  const { access } = await requirePermission("appointments.read");
  const types = await api<AppointmentType[]>("/appointment-types", { query: { include_inactive: true } });
  const canManage = hasOrgWide(access, "scheduling.manage");

  return (
    <>
      <PageHeader title="Appointment types" description="Length, fee and the buffer kept free afterwards (for cleaning or notes)." />
      <div className="flex max-w-5xl flex-col gap-4">
        {canManage ? (
          <>
            {types.map((t) => (
              <Panel key={t.id}>
                <AppointmentTypeForm action={updateAppointmentType.bind(null, t.id)} item={t} />
              </Panel>
            ))}
            <Panel title="Add appointment type">
              <AppointmentTypeForm action={createAppointmentType} />
            </Panel>
          </>
        ) : types.length === 0 ? (
          <EmptyState message="No appointment types yet." />
        ) : (
          <Table>
            <THead><tr><TH>Type</TH><TH align="right">Minutes</TH><TH align="right">Buffer</TH><TH align="right">Fee</TH><TH>Offered</TH></tr></THead>
            <tbody>
              {types.map((t) => (
                <TR key={t.id}>
                  <TD className="font-medium">{t.name}</TD>
                  <TD align="right" mono>{t.duration_minutes}</TD>
                  <TD align="right" mono>{t.booking_buffer_minutes}</TD>
                  <TD align="right" mono>{formatNAD(Number(t.fee))}</TD>
                  <TD>{t.is_active ? "Yes" : "No"}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </>
  );
}
