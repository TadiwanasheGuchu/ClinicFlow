"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function SignInButton() {
  const [pending, setPending] = useState(false);
  return (
    <Button
      className="w-full"
      disabled={pending}
      onClick={() => {
        setPending(true);
        void signIn("keycloak", { callbackUrl: "/" });
      }}
    >
      {pending ? "Redirecting…" : "Continue to sign in"}
    </Button>
  );
}
