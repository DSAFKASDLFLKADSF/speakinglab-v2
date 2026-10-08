import { NextResponse } from "next/server";
import {
  devAdminCredentials,
  ensureDevAdminUser,
  resetDevAdminSeedFlag,
} from "@/lib/devSeedAdmin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Dev-only: reset admin password to DEV_ADMIN_PASSWORD (default dev123456). */
export async function POST() {
  if (process.env.NODE_ENV !== "development") {
    return NextResponse.json({ error: "Not available." }, { status: 404 });
  }

  resetDevAdminSeedFlag();
  await ensureDevAdminUser();
  const { email, password } = devAdminCredentials();

  return NextResponse.json({
    ok: true,
    email,
    password,
    message: "Local admin password reset. Use these credentials to log in.",
  });
}
