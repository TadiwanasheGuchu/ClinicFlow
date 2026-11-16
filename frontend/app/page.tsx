import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth";

export default async function Home() {
  if (!(await getAccessToken())) redirect("/signin");
  redirect("/branches");
}
