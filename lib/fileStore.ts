import { createHash, randomUUID } from "crypto";
import fs from "fs/promises";
import path from "path";

/**
 * Server-side JSON file store (no Postgres).
 *
 * Layout under DATA_DIR (default: <cwd>/data):
 *   users/{userId}.json
 *   email-index/{sha256(email)}.json   → { userId }
 *   practices/{userId}/{id}.json
 *   surveys/{actorKey}/{pre|post}.json
 *
 * Audio files stay in AUDIO_STORAGE_DIR (see lib/audioStorage.ts).
 */

export function getDataRoot(): string {
  const fromEnv = process.env.DATA_DIR?.trim();
  if (fromEnv) return path.resolve(fromEnv);
  return path.join(process.cwd(), "data");
}

export function emailIndexKey(email: string): string {
  return createHash("sha256")
    .update(email.trim().toLowerCase())
    .digest("hex");
}

async function ensureDir(dir: string): Promise<void> {
  await fs.mkdir(dir, { recursive: true });
}

async function writeJsonAtomic(filePath: string, data: unknown): Promise<void> {
  await ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${process.pid}.${randomUUID()}.tmp`;
  const payload = JSON.stringify(data, null, 2);
  await fs.writeFile(tmp, payload, "utf8");
  await fs.rename(tmp, filePath);
}

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(filePath, "utf8");
    return JSON.parse(raw) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

export function userFilePath(userId: string): string {
  return path.join(getDataRoot(), "users", `${userId}.json`);
}

export function emailIndexPath(email: string): string {
  return path.join(getDataRoot(), "email-index", `${emailIndexKey(email)}.json`);
}

export function practiceDir(userId: string): string {
  return path.join(getDataRoot(), "practices", userId);
}

export function practiceFilePath(userId: string, practiceId: string): string {
  return path.join(practiceDir(userId), `${practiceId}.json`);
}

export function surveyActorDir(actorKey: string): string {
  return path.join(getDataRoot(), "surveys", actorKey);
}

export function surveyFilePath(
  actorKey: string,
  surveyType: "pre" | "post"
): string {
  return path.join(surveyActorDir(actorKey), `${surveyType}.json`);
}

export async function writeStoreJson(
  filePath: string,
  data: unknown
): Promise<void> {
  await writeJsonAtomic(filePath, data);
}

export async function readStoreJson<T>(filePath: string): Promise<T | null> {
  return readJsonFile<T>(filePath);
}

export async function deleteStoreFile(filePath: string): Promise<void> {
  try {
    await fs.unlink(filePath);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }
}

export async function listJsonFiles(dir: string): Promise<string[]> {
  try {
    const names = await fs.readdir(dir);
    return names
      .filter((n) => n.endsWith(".json"))
      .map((n) => path.join(dir, n));
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export async function listSubdirs(dir: string): Promise<string[]> {
  try {
    const names = await fs.readdir(dir, { withFileTypes: true });
    return names.filter((d) => d.isDirectory()).map((d) => d.name);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export async function ensureDataRoot(): Promise<string> {
  const root = getDataRoot();
  await ensureDir(root);
  await ensureDir(path.join(root, "users"));
  await ensureDir(path.join(root, "email-index"));
  await ensureDir(path.join(root, "practices"));
  await ensureDir(path.join(root, "surveys"));
  return root;
}

export async function isDataStoreWritable(): Promise<boolean> {
  try {
    const root = await ensureDataRoot();
    const probe = path.join(root, `.write-probe-${process.pid}`);
    await fs.writeFile(probe, "ok", "utf8");
    await fs.unlink(probe);
    return true;
  } catch {
    return false;
  }
}

export { pathExists, randomUUID };
