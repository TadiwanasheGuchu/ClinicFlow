import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth";
import { hasPermission, requireWorkspace } from "@/lib/session";

export default async function Home() {
  if (!(await getAccessToken())) redirect("/signin");
  const { access } = await requireWorkspace();
  redirect(hasPermission(access, "appointments.read") ? "/today" : "/branches");
}
