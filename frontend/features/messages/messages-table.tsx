import { CircleAlert, CircleCheck, CircleDashed, CircleMinus, Clock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { retryMessage } from "@/features/messages/actions";
import { formatDateTime, humanise } from "@/lib/format";
import type { Notification } from "@/types/api";

const STATUS = {
  pending: { label: "Queued", icon: Clock, cls: "text-secondary-text" },
  sent: { label: "Sent", icon: CircleCheck, cls: "text-success-text" },
  failed: { label: "Failed", icon: CircleAlert, cls: "text-danger-text" },
  cancelled: { label: "Cancelled", icon: CircleMinus, cls: "text-text-muted" },
  skipped: { label: "Not sent", icon: CircleDashed, cls: "text-warning-text" },
};

const CHANNEL: Record<string, string> = { sms: "SMS", whatsapp: "WhatsApp", email: "Email" };

export function MessagesTable({ items, canRetry, returnTo, showBody = false }: { items: Notification[]; canRetry: boolean; returnTo: string; showBody?: boolean }) {
  return (
    <Table>
      <THead>
        <tr><TH>Message</TH><TH>Channel</TH><TH>When</TH><TH>Status</TH>{canRetry && <TH align="right">Actions</TH>}</tr>
      </THead>
      <tbody>
        {items.map((m) => {
          const s = STATUS[m.delivery_status];
          const Icon = s.icon;
          return (
            <TR key={m.id} className="align-top">
              <TD>
                {humanise(m.event_type.replace("appointment_", ""))}
                {showBody && <p className="mt-0.5 max-w-lg text-sm text-text-muted">{m.body}</p>}
              </TD>
              <TD>{CHANNEL[m.channel] ?? m.channel}{m.recipient && <span className="block font-mono text-xs text-text-muted">{m.recipient}</span>}</TD>
              <TD className="tabular whitespace-nowrap">{formatDateTime(m.sent_at ?? m.scheduled_for)}</TD>
              <TD>
                <span className={`inline-flex items-center gap-1 text-sm font-medium ${s.cls}`}><Icon size={16} strokeWidth={1.5} aria-hidden />{s.label}</span>
                {m.last_error && <span className="block text-xs text-text-muted">{m.last_error}{m.attempts > 0 && ` (${m.attempts} attempt${m.attempts === 1 ? "" : "s"})`}</span>}
              </TD>
              {canRetry && (
                <TD align="right">
                  {m.delivery_status === "failed" && (
                    <form action={retryMessage.bind(null, m.id, returnTo)}>
                      <Button type="submit" size="sm" variant="secondary">Retry</Button>
                    </form>
                  )}
                </TD>
              )}
            </TR>
          );
        })}
      </tbody>
    </Table>
  );
}
