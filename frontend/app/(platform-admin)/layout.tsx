import { LogOut } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import type { Me } from "@/types/api";

/** Platform administration needs no practice membership (operators usually have none). */
export default async function PlatformLayout({ children }: { children: React.ReactNode }) {
  if (!(await getAccessToken())) redirect("/signin");
  const me = await api<Me>("/me", { tenant: false });
  if (!me.is_platform_admin) redirect("/not-permitted");
  const hasPractice = me.memberships.some((m) => m.status === "active" && m.organisation_status === "active");
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between gap-3 border-b border-border bg-surface px-4">
        <div className="flex items-center gap-4">
          <span className="font-mono text-sm text-primary">ClinicFlow</span>
          <span className="text-base font-medium">Platform</span>
          {hasPractice && <Link className="text-sm text-primary hover:underline" href="/">Back to practice</Link>}
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-text-muted sm:inline">{me.full_name}</span>
          <form action="/signout" method="post">
            <button type="submit" className="inline-flex h-8 items-center gap-1.5 rounded px-2 text-sm text-text hover:bg-surface-muted">
              <LogOut size={16} strokeWidth={1.5} aria-hidden />
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
    </div>
  );
}
