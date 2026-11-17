import { INVOICE_STATUS } from "@/lib/billing";
import type { InvoiceStatus } from "@/types/api";

export function InvoiceStatusText({ status }: { status: InvoiceStatus }) {
  const s = INVOICE_STATUS[status];
  return <span className={`text-sm font-medium ${s.cls}`}>{s.label}</span>;
}
