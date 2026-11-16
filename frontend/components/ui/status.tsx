import { cn } from "@/lib/cn";
import { CircleCheck, CircleDashed, CircleMinus, CirclePause, type LucideIcon } from "lucide-react";

type Tone = "success" | "warning" | "danger" | "neutral";

const STATUS: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  active: { label: "Active", tone: "success", icon: CircleCheck },
  invited: { label: "Invited", tone: "warning", icon: CircleDashed },
  suspended: { label: "Suspended", tone: "danger", icon: CirclePause },
  inactive: { label: "Inactive", tone: "neutral", icon: CircleMinus },
};

const tones: Record<Tone, string> = {
  success: "text-success-text",
  warning: "text-warning-text",
  danger: "text-danger-text",
  neutral: "text-text-muted",
};

/** Status is always text + icon, never colour alone. */
export function Status({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: "neutral" as Tone, icon: CircleMinus };
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm font-medium", tones[s.tone])}>
      <Icon size={16} strokeWidth={1.5} aria-hidden />
      {s.label}
    </span>
  );
}

/** Small neutral tag, e.g. "System" on locked roles. */
export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex h-5 items-center rounded-sm border border-border bg-surface-muted px-1.5 text-xs text-text-muted">
      {children}
    </span>
  );
}
