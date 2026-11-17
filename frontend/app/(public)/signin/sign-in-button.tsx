"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function SignInButton({ callbackUrl = "/" }: { callbackUrl?: string }) {
  const [pending, setPending] = useState(false);
  return (
    <Button
      className="h-11 w-full text-md"
      disabled={pending}
      onClick={() => {
        setPending(true);
        void signIn("keycloak", { callbackUrl });
      }}
    >
      {pending ? "Redirecting…" : "Continue to sign in"}
    </Button>
  );
}
