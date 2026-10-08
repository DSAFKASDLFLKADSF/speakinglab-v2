import { randomUUID } from "crypto";
import path from "path";
import type {
  PostSurveyAnswers,
  PreSurveyAnswers,
  SurveyAnswers,
  SurveyResponseRow,
  SurveyType,
} from "@/lib/surveys/types";
import {
  ensureDataRoot,
  getDataRoot,
  listJsonFiles,
  listSubdirs,
  pathExists,
  readStoreJson,
  surveyActorDir,
  surveyFilePath,
  writeStoreJson,
} from "@/lib/fileStore";

interface StoredSurveyFile {
  id: string;
  userId: string | null;
  clientId: string | null;
  surveyType: SurveyType;
  answers: SurveyAnswers;
  createdAt: string;
  updatedAt: string;
}

function actorKey(actor: {
  userId?: string | null;
  clientId?: string | null;
}): string | null {
  if (actor.userId) return `user-${actor.userId}`;
  if (actor.clientId) return `client-${actor.clientId}`;
  return null;
}

function mapRow(row: StoredSurveyFile): SurveyResponseRow {
  return {
    id: row.id,
    userId: row.userId,
    clientId: row.clientId,
    surveyType: row.surveyType,
    answers: row.answers,
    createdAt: row.createdAt,
  };
}

export async function getSurveyResponse(
  surveyType: SurveyType,
  actor: { userId?: string | null; clientId?: string | null }
): Promise<SurveyResponseRow | null> {
  const key = actorKey(actor);
  if (!key) return null;
  await ensureDataRoot();
  const row = await readStoreJson<StoredSurveyFile>(
    surveyFilePath(key, surveyType)
  );
  return row ? mapRow(row) : null;
}

export async function upsertSurveyResponse(
  surveyType: SurveyType,
  answers: SurveyAnswers,
  actor: { userId?: string | null; clientId?: string | null }
): Promise<SurveyResponseRow> {
  const key = actorKey(actor);
  if (!key) throw new Error("userId or clientId required.");

  await ensureDataRoot();
  const file = surveyFilePath(key, surveyType);
  const existing = await readStoreJson<StoredSurveyFile>(file);
  const now = new Date().toISOString();

  const row: StoredSurveyFile = existing
    ? {
        ...existing,
        answers,
        userId: actor.userId ?? existing.userId,
        clientId: actor.clientId ?? existing.clientId,
        updatedAt: now,
      }
    : {
        id: randomUUID(),
        userId: actor.userId ?? null,
        clientId: actor.clientId ?? null,
        surveyType,
        answers,
        createdAt: now,
        updatedAt: now,
      };

  await writeStoreJson(file, row);
  return mapRow(row);
}

export async function listAllSurveyResponses(): Promise<SurveyResponseRow[]> {
  await ensureDataRoot();
  const actors = await listSubdirs(path.join(getDataRoot(), "surveys"));
  const rows: SurveyResponseRow[] = [];

  for (const actor of actors) {
    const files = await listJsonFiles(surveyActorDir(actor));
    for (const file of files) {
      const row = await readStoreJson<StoredSurveyFile>(file);
      if (!row) continue;
      let userEmail: string | null = null;
      if (row.userId) {
        const { findUserById } = await import("@/lib/repositories/users");
        const user = await findUserById(row.userId);
        userEmail = user?.email ?? null;
      }
      rows.push({ ...mapRow(row), userEmail });
    }
  }

  rows.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  return rows;
}

export async function mergeAnonymousSurveysToUser(
  clientId: string,
  userId: string
): Promise<void> {
  const clientKey = `client-${clientId}`;
  const userKey = `user-${userId}`;
  await ensureDataRoot();

  for (const type of ["pre", "post"] as SurveyType[]) {
    const anonPath = surveyFilePath(clientKey, type);
    if (!(await pathExists(anonPath))) continue;

    const anon = await readStoreJson<StoredSurveyFile>(anonPath);
    if (!anon) continue;

    const userPath = surveyFilePath(userKey, type);
    const existingUser = await readStoreJson<StoredSurveyFile>(userPath);
    if (!existingUser) {
      const moved: StoredSurveyFile = {
        ...anon,
        userId,
        updatedAt: new Date().toISOString(),
      };
      await writeStoreJson(userPath, moved);
    }
  }
}

export type { PreSurveyAnswers, PostSurveyAnswers };
