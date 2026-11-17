import { LogOut } from "lucide-react";

import { Nav, type NavItem, OrganisationSwitcher } from "@/components/shell/nav";
import { hasPermission, requireWorkspace } from "@/lib/session";

export default async function ClinicAdminLayout({ children }: { children: React.ReactNode }) {
  const { me, orgId, access } = await requireWorkspace();
  const can = (p: string) => hasPermission(access, p);

  const items: NavItem[] = [
    can("appointments.read") && { href: "/today", label: "Today", icon: "today" },
    can("appointments.read") && { href: "/calendar", label: "Calendar", icon: "calendar" },
    can("patients.read") && { href: "/patients", label: "Patients", icon: "patients" },
    can("appointments.read") && { href: "/messages", label: "Messages", icon: "messages" },
    can("billing.read") && { href: "/invoices", label: "Invoices", icon: "invoices", section: "Billing" },
    can("billing.read") && { href: "/claims", label: "Claims", icon: "claims", section: "Billing" },
    can("billing.read") && { href: "/cash-up", label: "Cash-up", icon: "cashup", section: "Billing" },
    can("billing.read") && { href: "/services", label: "Services and prices", icon: "services", section: "Billing" },
    can("patients.read") && { href: "/medical-aid-funds", label: "Medical aid funds", icon: "funds", section: "Billing" },
    can("appointments.read") && { href: "/practitioners", label: "Practitioners", icon: "practitioners", section: "Practice setup" },
    can("appointments.read") && { href: "/appointment-types", label: "Appointment types", icon: "types", section: "Practice setup" },
    can("branches.read") && { href: "/branches", label: "Branches", icon: "branches", section: "Practice setup" },
    can("members.read") && { href: "/staff", label: "Staff", icon: "staff", section: "Practice setup" },
    can("roles.read") && { href: "/roles", label: "Roles", icon: "roles", section: "Practice setup" },
    can("audit.read") && { href: "/audit", label: "Audit log", icon: "audit", section: "Practice setup" },
    can("organisation.read") && { href: "/organisation", label: "Organisation", icon: "organisation", section: "Practice setup" },
    me.is_platform_admin && { href: "/platform", label: "Platform", icon: "platform", section: "Platform" },
].filter(Boolean) as NavItem[];

  const organisations = me.memberships
    .filter((m) => m.status === "active" && m.organisation_status === "active")
    .map((m) => ({ id: m.organisation_id, name: m.organisation_name }));

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between gap-3 border-b border-border bg-surface px-4">
        <div className="flex min-w-0 items-center gap-4">
          <span className="font-mono text-sm text-primary">ClinicFlow</span>
          <OrganisationSwitcher current={orgId} options={organisations} />
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-text-muted sm:inline">{me.full_name}</span>
          <form action="/signout" method="post">
            <button
              type="submit"
              className="inline-flex h-8 items-center gap-1.5 rounded px-2 text-sm text-text hover:bg-surface-muted"
            >
              <LogOut size={16} strokeWidth={1.5} aria-hidden />
              Sign out
            </button>
          </form>
        </div>
      </header>
      <div className="flex flex-1 flex-col md:flex-row">
        <aside className="border-b border-border bg-surface-muted p-2 md:w-[220px] md:shrink-0 md:border-r md:border-b-0 md:p-3">
          <Nav items={items} />
        </aside>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
