/**
 * Compiler settings from the environment, with the repo's .env as a fallback. Values are never logged.
 *
 * FACTORY_API_KEY is required: without it the compiler refuses to start. There is no keyless mode and no stub
 * backend; a Droid run either talks to Factory or does not happen.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

export class ConfigError extends Error {}

function dotenv(root: string): Record<string, string> {
  const p = join(root, ".env");
  if (!existsSync(p)) return {};
  const out: Record<string, string> = {};
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    out[t.slice(0, i).trim()] = t
      .slice(i + 1)
      .split(" #")[0]!
      .trim();
  }
  return out;
}

export interface CompilerConfig {
  factoryApiKey: string;
  /** Path of the droid executable; undefined = `droid` on PATH */
  droidExecPath: string | undefined;
  model: string;
  /** Droid reasoning effort (none|minimal|low|medium|high|xhigh); low keeps a 90 s budget realistic */
  reasoningEffort: string;
  timeoutMs: number;
  maxAttempts: number;
  /** Python interpreter of the engine venv (runs replay_test) */
  enginePython: string;
  runsDir: string;
  spacetimeUri: string;
  spacetimeModule: string;
  spacetimeCompilerToken: string;
  port: number;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env, root = REPO_ROOT): CompilerConfig {
  const e = { ...dotenv(root), ...env } as Record<string, string | undefined>;
  const key = e.FACTORY_API_KEY?.trim();
  if (!key) {
    throw new ConfigError(
      "FACTORY_API_KEY is not set. The Droid compiler needs a Factory API key (put it in .env, never in the repo).",
    );
  }
  const off = Number(e.PORT_OFFSET || 0);
  const enginePython = e.ENGINE_PYTHON || join(root, "services/engine/.venv/bin/python");
  return {
    factoryApiKey: key,
    droidExecPath: e.DROID_EXEC_PATH || undefined,
    model: e.DROID_MODEL || "claude-sonnet-5",
    reasoningEffort: e.DROID_REASONING_EFFORT || "low",
    timeoutMs: Number(e.DROID_TIMEOUT_S || 90) * 1000,
    maxAttempts: Number(e.DROID_MAX_ATTEMPTS || 3),
    enginePython,
    runsDir: e.DROID_RUNS_DIR || join(root, "data/local/droid_runs"),
    spacetimeUri: (e.SPACETIME_URI || "http://127.0.0.1:3000").replace(/\/$/, ""),
    spacetimeModule: e.SPACETIME_MODULE || "trophy",
    spacetimeCompilerToken: e.SPACETIME_COMPILER_TOKEN || "",
    port: 8200 + off,
  };
}
