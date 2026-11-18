import type { Metadata } from "next";

export const metadata: Metadata = { title: "Account" };

const PROBLEMS: Record<string, { title: string; body: string }> = {
  email_unverified: {
    title: "Verify your email address",
    body: "ClinicFlow needs a verified email address. Open the verification email we sent when you signed up, click the link, then sign in again. Check your spam folder if you can’t find it.",
  },
  identity_conflict: {
    title: "This email is linked to another sign-in",
    body: "Your email address is already connected to a different ClinicFlow sign-in. Sign in the way you did before, or ask your practice administrator for help.",
  },
};

/** Shown when sign-in worked but the account can't be used yet. Needs no API access. */
export default async function AccountProblem({ searchParams }: { searchParams: Promise<{ problem?: string }> }) {
  const { problem } = await searchParams;
  const info = PROBLEMS[problem ?? ""] ?? PROBLEMS.email_unverified!;
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 px-4 py-16">
      <p className="font-mono text-sm text-primary">ClinicFlow</p>
      <h1 className="text-xl text-text">{info.title}</h1>
      <p className="text-base text-text">{info.body}</p>
      <form action="/signout" method="post">
        <input type="hidden" name="next" value="/signin" />
        <button type="submit" className="h-10 rounded bg-primary px-4 text-base font-medium text-white hover:bg-primary-hover">
          Sign out and sign in again
        </button>
      </form>
    </main>
  );
}
