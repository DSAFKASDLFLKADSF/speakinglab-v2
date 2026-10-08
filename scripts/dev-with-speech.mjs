import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import net from "node:net";
import { fileURLToPath, pathToFileURL } from "node:url";
import nextEnv from "@next/env";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export function developmentConfig(env = process.env) {
  const port = Number(env.PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535.");
  }
  return {
    port,
    // One explicit port for the page, upload playback and Python audio downloads.
    env: { ...env, PORT: String(port), NEXT_PUBLIC_APP_URL: `http://localhost:${port}`,
      INTERNAL_APP_URL: `http://127.0.0.1:${port}`,
      ...(process.platform === "darwin" && !env.WATCHPACK_POLLING ? { WATCHPACK_POLLING: "1000" } : {}),
    },
  };
}

async function ensurePortAvailable(port) {
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (error) => reject(error.code === "EADDRINUSE"
      ? new Error(`Port ${port} is already in use. Stop that app or set PORT to another port before starting this project.`)
      : new Error(`Cannot open local port ${port}: ${error.code ?? error.message}`)));
    server.listen(port, () => server.close(resolve));
  });
}

export function speechServiceConfig(raw) {
  const url = new URL(raw?.trim() || "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("PYTHON_SPEECH_API_URL must be an HTTP(S) service URL without credentials or query parameters.");
  }
  // Avoid IPv6 localhost resolution when the local Python listener uses IPv4.
  if (url.hostname === "localhost") url.hostname = "127.0.0.1";
  const local = ["127.0.0.1", "[::1]"].includes(url.hostname);
  return {
    baseUrl: url.href.replace(/\/$/, ""),
    healthUrl: `${url.href.replace(/\/$/, "")}/health`,
    canStartLocally: local && url.protocol === "http:" && url.pathname === "/",
    host: url.hostname === "[::1]" ? "::1" : url.hostname,
    port: url.port || (url.protocol === "https:" ? "443" : "80"),
  };
}

export async function speechServiceReady(config, fetchImpl = fetch) {
  try {
    const response = await fetchImpl(config.healthUrl, { signal: AbortSignal.timeout(3000) });
    if (!response.ok) return false;
    const body = await response.json();
    return body.status === "ok" && body.service === "ai-speaking-trainer-python";
  } catch {
    return false;
  }
}

function findPython() {
  const executable = process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
  const candidates = [
    process.env.SPEECH_PYTHON,
    path.join(root, ".venv", executable),
    path.join(root, "python/.venv", executable),
    "python3",
    "python",
  ].filter(Boolean);
  for (const command of candidates) {
    const result = spawnSync(command, ["-c", "import sys; assert sys.version_info >= (3, 10); import uvicorn"], {
      stdio: "ignore", timeout: 10000,
    });
    if (result.status === 0) return command;
  }
  throw new Error("Python 3.10+ with uvicorn is required. Create .venv and install python/requirements.txt first. See LOCAL-START.txt.");
}

export async function startDevelopment() {
  nextEnv.loadEnvConfig(root, true);
  const config = speechServiceConfig(process.env.PYTHON_SPEECH_API_URL);
  const children = [];
  let stopping = false;
  const stop = (code) => {
    if (stopping) return;
    stopping = true;
    for (const child of children) {
      if (child.exitCode === null) child.kill("SIGTERM");
    }
    process.exitCode = code;
  };
  process.once("SIGINT", () => stop(130));
  process.once("SIGTERM", () => stop(143));
  const start = (command, args, cwd, env) => {
    const child = spawn(command, args, { cwd, env, stdio: "inherit" });
    children.push(child);
    child.once("error", (error) => { console.error(error.message); stop(1); });
    child.once("exit", (code) => { if (!stopping) stop(code ?? 1); });
    return child;
  };

  try {
    const frontend = developmentConfig();
    await ensurePortAvailable(frontend.port);
    if (!(await speechServiceReady(config))) {
      if (!config.canStartLocally) {
        throw new Error("The configured speech service is unavailable. Start the deployed Python service and verify PYTHON_SPEECH_API_URL before trying again.");
      }
      if (!existsSync(path.join(root, "python/.env"))) {
        console.warn("python/.env is missing. Restore it from your existing project, or supply your transcription and GLM credentials as environment variables. Do not paste secrets into chat.");
      }
      console.log("Starting the Python scoring and feedback service...");
      start(findPython(), ["-m", "uvicorn", "main:app", "--host", config.host, "--port", config.port], path.join(root, "python"), process.env);
      let ready = false;
      const deadline = Date.now() + 60000;
      while (!stopping && Date.now() < deadline) {
        if (await speechServiceReady(config)) { ready = true; break; }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      if (!ready) throw new Error("The speech service did not become ready. Check the Python error above and LOCAL-START.txt. The frontend has not been started.");
    }
    if (stopping) return;
    console.log("Speech service is reachable. Starting the practice app...");
    start(process.execPath, [path.join(root, "node_modules/next/dist/bin/next"), "dev", "--port", String(frontend.port)], root,
      { ...frontend.env, PYTHON_SPEECH_API_URL: config.baseUrl });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    stop(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await startDevelopment();
}
