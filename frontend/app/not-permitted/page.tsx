import { ButtonLink } from "@/components/ui/button";

export default function NotPermitted() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-sm text-center">
        <h1 className="text-xl text-text">You don’t have access to this page</h1>
        <p className="mt-2 text-base text-text-muted">
          Your role doesn’t include this area. Ask your practice administrator if you need it.
        </p>
        <ButtonLink href="/" variant="secondary" className="mt-4">
          Go to start
        </ButtonLink>
      </div>
    </main>
  );
}
