import {
  CircleAlert, CircleCheck, CircleDashed, CircleDot, CircleX, FlaskConical, Truck, type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { FLAG_LABEL, LAB_STATUS_LABEL } from "@/lib/lab";
import type { LabFlag, LabOrderStatus } from "@/types/api";

const STATUS: Record<LabOrderStatus, { icon: LucideIcon; tone: string }> = {
  requested: { icon: CircleDashed, tone: "text-text-muted" },
  collected: { icon: FlaskConical, tone: "text-text" },
  sent: { icon: Truck, tone: "text-text" },
  processing: { icon: CircleDot, tone: "text-text" },
  completed: { icon: CircleAlert, tone: "text-warning-text" },
  reviewed: { icon: CircleCheck, tone: "text-success-text" },
  cancelled: { icon: CircleX, tone: "text-text-muted" },
};

/** Text and icon, never colour alone. */
export function LabStatus({ status }: { status: LabOrderStatus }) {
  const { icon: Icon, tone } = STATUS[status];
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm font-medium", tone)}>
      <Icon size={16} strokeWidth={1.5} aria-hidden />
      {LAB_STATUS_LABEL[status]}
    </span>
  );
}

/** Abnormal flags are written out in words and bold; critical values also get an icon. */
export function FlagText({ flag }: { flag: LabFlag }) {
  if (flag === "none" || flag === "normal") return <span className="text-text-muted">{FLAG_LABEL[flag]}</span>;
  const critical = flag.startsWith("critical");
  return (
    <span className={cn("inline-flex items-center gap-1 font-semibold", critical ? "text-danger-text" : "text-warning-text")}>
      {critical && <CircleAlert size={16} strokeWidth={1.5} aria-hidden />}
      {FLAG_LABEL[flag]}
    </span>
  );
}
