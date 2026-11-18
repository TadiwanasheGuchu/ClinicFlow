"use client";

import { cn } from "@/lib/cn";
import {
  Banknote,
  ChartColumn,
  Building2,
  CalendarClock,
  CalendarRange,
  FileText,
  Package,
  FlaskConical,
  TestTubes,
  HandCoins,
  Receipt,
  Tags,
  CalendarDays,
  ClipboardList,
  Contact,
  Landmark,
  MessageSquare,
  ListChecks,
  ScrollText,
  Settings,
  ShieldCheck,
  Stethoscope,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ICONS = {
  today: ClipboardList,
  calendar: CalendarDays,
  patients: Contact,
  invoices: Receipt,
  reports: ChartColumn,
  claims: FileText,
  cashup: Banknote,
  services: Tags,
  funds: HandCoins,
  messages: MessageSquare,
  lab: FlaskConical,
  labsetup: TestTubes,
  myroster: CalendarClock,
  stock: Package,
  roster: CalendarRange,
  practitioners: Stethoscope,
  types: ListChecks,
  branches: Building2,
  staff: Users,
  roles: ShieldCheck,
  audit: ScrollText,
  organisation: Settings,
  platform: Landmark,
};

export type NavItem = { href: string; label: string; icon: keyof typeof ICONS; section?: string };

export function Nav({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col md:overflow-visible">
      {items.map((item, index) => {
        const Icon = ICONS[item.icon];
        const heading = item.section && item.section !== items[index - 1]?.section ? item.section : null;
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <div key={item.href} className="contents">
          {heading && (
            <span className="hidden px-2.5 pt-4 pb-1 text-xs font-medium tracking-wide text-text-muted uppercase md:block">
              {heading}
            </span>
          )}
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-9 shrink-0 items-center gap-2 rounded px-2.5 text-base",
              active
                ? "bg-primary-subtle font-medium text-primary"
                : "text-text hover:bg-surface",
            )}
          >
            <Icon size={20} strokeWidth={1.5} aria-hidden />
            {item.label}
          </Link>
          </div>
        );
      })}
    </nav>
  );
}

export function OrganisationSwitcher({
  current,
  options,
}: {
  current: string;
  options: { id: string; name: string }[];
}) {
  const pathname = usePathname();
  if (options.length < 2) {
    return <span className="truncate text-base font-medium">{options[0]?.name}</span>;
  }
  return (
    <label className="flex items-center gap-2">
      <span className="sr-only">Organisation</span>
      <select
        className="h-8 max-w-56 rounded-sm border border-border bg-surface px-2 text-base font-medium"
        value={current}
        onChange={(e) => {
          window.location.href = `/switch?to=${encodeURIComponent(e.target.value)}&next=${encodeURIComponent(pathname)}`;
        }}
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  );
}
