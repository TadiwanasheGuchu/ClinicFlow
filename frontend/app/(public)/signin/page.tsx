import type { Metadata } from "next";

import { safePath } from "@/lib/safe-path";

import { SignInButton } from "./sign-in-button";

export const metadata: Metadata = { title: "Sign in" };

export default async function SignInPage({ searchParams }: { searchParams: Promise<{ callbackUrl?: string }> }) {
  const { callbackUrl } = await searchParams;
  const next = safePath(callbackUrl);
  const patient = next.startsWith("/book/");
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded border border-border bg-surface p-6">
        <p className="font-mono text-sm text-primary">ClinicFlow</p>
        <h1 className="mt-2 text-xl text-text">Sign in</h1>
        <p className="mt-1 mb-5 text-base text-text-muted">
          {patient
            ? "Sign in to book and manage your appointments. New here? Choose “Register” on the next screen to create an account."
            : "Use your ClinicFlow account. Staff who were invited by their practice should sign in with the email address the invitation was sent to."}
        </p>
        <SignInButton callbackUrl={next} />
      </div>
    </main>
  );
}
