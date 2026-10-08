import { randomUUID } from "crypto";
import type { AppUser } from "@/lib/auth/types";
import { isAdminEmail } from "@/lib/auth/admins";
import {
  emailIndexPath,
  ensureDataRoot,
  readStoreJson,
  userFilePath,
  writeStoreJson,
} from "@/lib/fileStore";

export interface StoredUserRecord {
  id: string;
  email: string;
  passwordHash: string;
  displayName: string | null;
  avatarUrl: string | null;
  nativeLanguage: string;
  targetScore: number;
  isAdmin: boolean;
  createdAt: string;
  updatedAt: string;
}

function mapUser(row: StoredUserRecord): AppUser {
  return {
    id: row.id,
    email: row.email,
    displayName: row.displayName,
    avatarUrl: row.avatarUrl,
    nativeLanguage: row.nativeLanguage,
    targetScore: row.targetScore,
    isAdmin: Boolean(row.isAdmin) || isAdminEmail(row.email),
    createdAt: row.createdAt,
  };
}

async function saveUser(record: StoredUserRecord): Promise<void> {
  await ensureDataRoot();
  await writeStoreJson(userFilePath(record.id), record);
  await writeStoreJson(emailIndexPath(record.email), { userId: record.id });
}

export async function findUserByEmail(
  email: string
): Promise<(AppUser & { passwordHash: string }) | null> {
  await ensureDataRoot();
  const index = await readStoreJson<{ userId: string }>(
    emailIndexPath(email)
  );
  if (!index?.userId) return null;
  const row = await readStoreJson<StoredUserRecord>(userFilePath(index.userId));
  if (!row) return null;

  const admin = isAdminEmail(row.email);
  if (admin && !row.isAdmin) {
    row.isAdmin = true;
    row.updatedAt = new Date().toISOString();
    await saveUser(row);
  }

  return { ...mapUser(row), passwordHash: row.passwordHash };
}

export async function findUserById(id: string): Promise<AppUser | null> {
  await ensureDataRoot();
  const row = await readStoreJson<StoredUserRecord>(userFilePath(id));
  if (!row) return null;
  return mapUser(row);
}

export async function createUser(input: {
  email: string;
  passwordHash: string;
  displayName?: string | null;
}): Promise<AppUser> {
  await ensureDataRoot();
  const email = input.email.trim().toLowerCase();
  const existing = await findUserByEmail(email);
  if (existing) {
    throw new Error("An account with this email already exists.");
  }

  const now = new Date().toISOString();
  const record: StoredUserRecord = {
    id: randomUUID(),
    email,
    passwordHash: input.passwordHash,
    displayName: input.displayName?.trim() || null,
    avatarUrl: null,
    nativeLanguage: "zh-CN",
    targetScore: 24,
    isAdmin: isAdminEmail(email),
    createdAt: now,
    updatedAt: now,
  };

  await saveUser(record);
  return mapUser(record);
}

export async function updateUserPasswordHash(
  email: string,
  passwordHash: string
): Promise<AppUser | null> {
  const found = await findUserByEmail(email);
  if (!found) return null;
  const row = await readStoreJson<StoredUserRecord>(userFilePath(found.id));
  if (!row) return null;
  row.passwordHash = passwordHash;
  row.isAdmin = true;
  row.updatedAt = new Date().toISOString();
  await saveUser(row);
  return mapUser(row);
}
