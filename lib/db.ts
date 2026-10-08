/**
 * Legacy Postgres helpers kept for optional scripts.
 * App persistence is file-based (lib/fileStore.ts) — no DATABASE_URL required.
 */

import { Pool, type PoolClient, type QueryResultRow } from "pg";
import {
  isDataStoreWritable,
  ensureDataRoot,
} from "@/lib/fileStore";

let pool: Pool | undefined;

/** True when the server can persist accounts / history / surveys (file store). */
export function isDatabaseConfigured(): boolean {
  // File store is always available once AUTH_SECRET is set for auth flows.
  // Callers use this as "can we persist?" — answer yes for local JSON store.
  return true;
}

export async function ensurePersistenceReady(): Promise<boolean> {
  await ensureDataRoot();
  return isDataStoreWritable();
}

export function getPool(): Pool {
  const url = process.env.DATABASE_URL?.trim();
  if (!url) {
    throw new Error(
      "DATABASE_URL is not used anymore. Data is stored under DATA_DIR on disk."
    );
  }

  if (!pool) {
    pool = new Pool({ connectionString: url });
  }

  return pool;
}

export async function query<T extends QueryResultRow = QueryResultRow>(
  _text: string,
  _params?: unknown[]
): Promise<T[]> {
  void _text;
  void _params;
  throw new Error(
    "Postgres query() is disabled. Use the file store (lib/fileStore.ts)."
  );
}

export async function queryOne<T extends QueryResultRow = QueryResultRow>(
  _text: string,
  _params?: unknown[]
): Promise<T | null> {
  void _text;
  void _params;
  throw new Error(
    "Postgres queryOne() is disabled. Use the file store (lib/fileStore.ts)."
  );
}

export async function withTransaction<T>(
  _fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  void _fn;
  throw new Error(
    "Postgres withTransaction() is disabled. Use the file store (lib/fileStore.ts)."
  );
}
