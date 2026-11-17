import {
  CalendarCheck,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  CircleX,
  Clock,
  LogIn,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";

import { STATUS_LABEL } from "@/lib/appointments";
import { cn } from "@/lib/cn";
import type { AppointmentStatus as Status } from "@/types/api";

const STYLE: Record<Status, { icon: LucideIcon; cls: string }> = {
  requested: { icon: CircleDashed, cls: "text-warning-text" },
  pending_confirmation: { icon: CircleDashed, cls: "text-warning-text" },
  confirmed: { icon: CalendarCheck, cls: "text-secondary-text" },
  checked_in: { icon: LogIn, cls: "text-primary" },
  waiting: { icon: Clock, cls: "text-warning-text" },
  in_consultation: { icon: Stethoscope, cls: "text-primary" },
  completed: { icon: CircleCheck, cls: "text-success-text" },
  cancelled: { icon: CircleX, cls: "text-text-muted" },
  no_show: { icon: CircleSlash, cls: "text-danger-text" },
};

/** Text + icon; never colour alone. */
export function AppointmentStatus({ status, className }: { status: Status; className?: string }) {
  const s = STYLE[status];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm font-medium whitespace-nowrap", s.cls, className)}>
      <Icon size={16} strokeWidth={1.5} aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}
