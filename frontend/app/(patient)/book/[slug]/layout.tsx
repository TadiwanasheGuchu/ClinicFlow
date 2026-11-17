import { LogOut } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getAccessToken } from "@/lib/auth";
import { portalInfo } from "@/lib/portal";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const info = await portalInfo((await params).slug);
  return { title: info ? `Book · ${info.name}` : "Booking" };
}

/** Patient portal shell: mobile-first, 16px base text, no staff navigation. */
export default async function PortalLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const info = await portalInfo(slug);
  if (!info) notFound();
  const signedIn = !!(await getAccessToken());
  return (
    <div className="min-h-screen bg-background text-md">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex h-14 max-w-xl items-center justify-between gap-3 px-4">
          <Link href={`/book/${slug}`} className="truncate text-md font-semibold text-text">{info.name}</Link>
          {signedIn && (
            <form action="/signout" method="post">
              <input type="hidden" name="next" value={`/book/${slug}`} />
              <button type="submit" className="inline-flex h-11 items-center gap-1.5 rounded px-2 text-base text-text hover:bg-surface-muted">
                <LogOut size={20} strokeWidth={1.5} aria-hidden /> Sign out
              </button>
            </form>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-xl px-4 py-5">{children}</main>
      <footer className="mx-auto max-w-xl px-4 pb-8 text-sm text-text-muted">
        Online booking by <span className="font-mono">ClinicFlow</span>. For anything urgent, call the practice{info.phone && <> on <a className="text-primary underline" href={`tel:${info.phone.replace(/\s/g, "")}`}>{info.phone}</a></>}.
      </footer>
    </div>
  );
}
