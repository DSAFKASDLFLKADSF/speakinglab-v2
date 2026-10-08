import { mkdir, writeFile } from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/getCurrentUser";
import {
  LOCAL_AUDIO_BUCKET,
  buildAudioStoragePath,
  extensionFromAudioMime,
  resolveAudioFilePath,
  normalizeAudioContentType,
  resolvePublicAudioUrl,
} from "@/lib/audioStorage";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!(file instanceof Blob) || file.size === 0) {
      return NextResponse.json(
        { error: "Missing or empty audio file." },
        { status: 400 }
      );
    }

    const allowAnonymous = formData.get("allowAnonymous") === "true";
    const sessionId = formData.get("sessionId");
    const fileName = formData.get("fileName");
    for (const segment of [sessionId, fileName]) {
      if (segment !== null && (typeof segment !== "string" || segment === "." || segment.includes("..") || /[\\/\x00]/.test(segment))) {
        return NextResponse.json({ error: "Invalid audio file name or session ID." }, { status: 400 });
      }
    }

    const sessionUser = await getCurrentUser();
    let userId = sessionUser?.id ?? null;

    if (!userId && allowAnonymous) {
      userId = "anonymous";
    }

    if (!userId) {
      return NextResponse.json(
        { error: "User must be logged in to upload audio." },
        { status: 401 }
      );
    }

    const contentType = normalizeAudioContentType(file.type || "audio/webm");
    const storagePath = buildAudioStoragePath(
      userId,
      typeof sessionId === "string" && sessionId.trim()
        ? sessionId.trim()
        : undefined,
      typeof fileName === "string" && fileName.trim()
        ? fileName.trim()
        : undefined,
      contentType
    );

    const fullPath = resolveAudioFilePath(storagePath);
    if (!fullPath) return NextResponse.json({ error: "Invalid audio path." }, { status: 400 });
    await mkdir(path.dirname(fullPath), { recursive: true });

    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(fullPath, buffer);

    const audioUrl = resolvePublicAudioUrl(storagePath, new URL(request.url).origin);

    return NextResponse.json({
      audioUrl,
      storagePath,
      bucket: LOCAL_AUDIO_BUCKET,
      contentType,
      extension: extensionFromAudioMime(contentType),
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to upload audio.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
