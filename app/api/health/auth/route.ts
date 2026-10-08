import { NextResponse } from "next/server";
import { isAuthConfigured } from "@/lib/auth/session";
import { ensurePersistenceReady, isDatabaseConfigured } from "@/lib/db";
import { ensureDevAdminUser } from "@/lib/devSeedAdmin";
import { getDataRoot } from "@/lib/fileStore";

export const runtime = "nodejs";

export async function GET() {
  const auth = isAuthConfigured();
  const storeConfigured = isDatabaseConfigured();
  let storeWritable: boolean | null = null;
  let storeError: string | null = null;

  try {
    storeWritable = await ensurePersistenceReady();
    await ensureDevAdminUser();
  } catch (err) {
    storeWritable = false;
    storeError = err instanceof Error ? err.message : "Data store unreachable";
  }

  return NextResponse.json({
    authConfigured: auth,
    databaseConfigured: storeConfigured,
    databaseReachable: storeWritable,
    databaseError: storeError,
    storage: "file",
    dataDir: getDataRoot(),
    hint: !auth
      ? "Set AUTH_SECRET in .env.local, then restart the server. Accounts and history are stored under DATA_DIR on disk (no Postgres)."
      : null,
  });
}
