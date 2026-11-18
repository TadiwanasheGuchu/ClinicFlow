"use client";

/** Unexpected errors. Shows the reference that matches the server log, never details. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 px-4 py-16">
      <p className="font-mono text-sm text-primary">ClinicFlow</p>
      <h1 className="text-xl text-text">Something went wrong</h1>
      <p className="text-base text-text">
        The page couldn’t be loaded. Try again; if it keeps happening, tell your administrator
        {error.digest ? <> and quote reference <span className="font-mono">{error.digest}</span></> : null}.
      </p>
      <div className="flex gap-2">
        <button type="button" onClick={reset} className="h-10 rounded bg-primary px-4 text-base font-medium text-white hover:bg-primary-hover">Try again</button>
        <a href="/" className="inline-flex h-10 items-center rounded border border-border bg-surface px-4 text-base hover:bg-surface-muted">Home</a>
      </div>
    </main>
  );
}
