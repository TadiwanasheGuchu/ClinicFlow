"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function SignInButton({ callbackUrl = "/", provider }: { callbackUrl?: string; provider: string }) {
  const [pending, setPending] = useState(false);
  return (
    <Button
      className="h-11 w-full text-md"
      disabled={pending}
      onClick={() => {
        setPending(true);
        void signIn(provider, { callbackUrl });
      }}
    >
      {pending ? "Redirecting…" : "Continue to sign in"}
    </Button>
  );
}
