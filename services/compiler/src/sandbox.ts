/**
 * The Droid's sandbox: a fresh directory (its own git repository, so every edit is a diff against a base commit)
 * containing only what the job needs:
 *
 *   sports/<sport>/           the module to produce or edit (the only editable files)
 *   reference/<base_sport>/   the golden module to derive from (compile jobs; read-only)
 *   schema/                   rulepack, sportmodule and event JSON Schemas
 *   scene/scene.json          the scene descriptor (compile and retune jobs)
 *   samples/*.l1.jsonl + .labels.json
 *   replay_test               the test gate, pinned to the engine venv; the one command the Droid may run
 *   TASK.md                   the brief, the allowlist and the pass criteria
 *
 * No secrets, no repo, no network beyond the Factory API (the permission handler refuses every other command).
 */
import { execFileSync } from "node:child_process";
import { chmodSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { editableFiles, type JobKind, MODULE_FILES } from "./allowlist.ts";
import { REPO_ROOT } from "./config.ts";

export interface Job {
  kind: JobKind;
  sport: string;
  /** compile: the module to derive from */
  baseSport?: string;
  /** house_rule / retune: the text of the rule or the reason */
  text?: string;
  scene?: string;
  samplesDir: string;
  /** house_rule / retune: the current module directory (defaults to the repo's sports/<sport>) */
  moduleDir?: string;
  gameId?: string;
  ruleVersion?: string;
}

export interface Sandbox {
  dir: string;
  allowlist: string[];
  baseCommit: string;
  moduleDir: string;
}

function git(dir: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd: dir, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

export function createSandbox(job: Job, dir: string, enginePython: string, root = REPO_ROOT): Sandbox {
  mkdirSync(dir, { recursive: true });
  if (readdirSync(dir).length) throw new Error(`sandbox dir is not empty: ${dir}`);
  const schemaDir = join(dir, "schema");
  mkdirSync(schemaDir);
  for (const f of ["rulepack", "sportmodule", "event", "scene"]) {
    cpSync(join(root, "packages/contracts", `${f}.schema.json`), join(schemaDir, `${f}.schema.json`));
  }
  const samplesOut = join(dir, "samples");
  mkdirSync(samplesOut);
  const samples: string[] = [];
  for (const f of readdirSync(job.samplesDir)) {
    if (f.endsWith(".l1.jsonl") || f.endsWith(".labels.json")) {
      cpSync(join(job.samplesDir, f), join(samplesOut, f));
      if (f.endsWith(".l1.jsonl")) samples.push(f);
    }
  }
  if (!samples.length) throw new Error(`${job.samplesDir}: no *.l1.jsonl samples`);
  if (job.scene) {
    mkdirSync(join(dir, "scene"));
    cpSync(job.scene, join(dir, "scene", "scene.json"));
  }
  const moduleDir = join(dir, "sports", job.sport);
  mkdirSync(moduleDir, { recursive: true });
  if (job.kind === "compile") {
    const base = job.baseSport ?? "table_tennis";
    const refSrc = job.moduleDir ?? join(root, "sports", base);
    cpSync(refSrc, join(dir, "reference", base), { recursive: true });
    // Seed the new module with the reference so the Droid edits (a 90 s job) instead of retyping events.py.
    for (const f of MODULE_FILES) cpSync(join(refSrc, f), join(moduleDir, f));
  } else {
    const src = job.moduleDir ?? join(root, "sports", job.sport);
    for (const f of MODULE_FILES) {
      if (!existsSync(join(src, f))) throw new Error(`${src}/${f} missing`);
      cpSync(join(src, f), join(moduleDir, f));
    }
  }
  // the gate: a fixed script so the Droid cannot vary the interpreter, module or samples
  const script = [
    "#!/bin/sh",
    "# The Droid's test gate (trophy_engine.replay_test). The only command the sandbox allows.",
    `cd "$(dirname "$0")" || exit 2`,
    `exec "${enginePython}" -m trophy_engine.replay_test.cli --module "sports/${job.sport}" --samples samples --json .trophy/results.json --events .trophy/events.json "$@"`,
    "",
  ].join("\n");
  writeFileSync(join(dir, "replay_test"), script);
  chmodSync(join(dir, "replay_test"), 0o755);
  writeFileSync(join(dir, ".gitignore"), ".trophy/\n__pycache__/\n");
  const allowlist = editableFiles(job.kind, job.sport);
  writeFileSync(join(dir, "TASK.md"), renderTask(job, allowlist, samples));
  installGuard(dir, allowlist);
  git(dir, "init", "-q", "-b", "main");
  git(dir, "-c", "user.name=trophy-droid", "-c", "user.email=droid@trophy.local", "add", "-A");
  git(
    dir,
    "-c",
    "user.name=trophy-droid",
    "-c",
    "user.email=droid@trophy.local",
    "commit",
    "-q",
    "-m",
    "sandbox base",
    "--allow-empty",
  );
  const baseCommit = git(dir, "rev-parse", "HEAD");
  return { dir, allowlist, baseCommit, moduleDir };
}

const PROMPTS = join(REPO_ROOT, "services/compiler/prompts");
export const GUARD = join(REPO_ROOT, "services/compiler/hooks/guard.py");

/**
 * The enforcement point. The Droid CLI runs project hooks from <cwd>/.factory/hooks.json before every tool call;
 * autonomy "low" auto-approves edits without asking the SDK permission handler (measured 2026-10-24), so the
 * PreToolUse hook is what keeps the agent inside the allowlist. The allowlist and the hooks file are read-only.
 */
export function installGuard(dir: string, allowlist: string[]): void {
  mkdirSync(join(dir, ".trophy"), { recursive: true });
  mkdirSync(join(dir, ".factory"), { recursive: true });
  const allowPath = join(dir, ".trophy", "allowlist.json");
  writeFileSync(allowPath, JSON.stringify({ files: allowlist, commands: ["./replay_test"] }, null, 1));
  chmodSync(allowPath, 0o444);
  const cmd = `python3 "${GUARD}" "${dir}"`;
  const hooks = {
    hooksDisabled: false,
    PreToolUse: [
      {
        matcher: "Edit|Create|ApplyPatch|MultiEdit|Write|Execute",
        hooks: [{ type: "command", command: cmd, timeout: 10 }],
      },
    ],
  };
  const hooksPath = join(dir, ".factory", "hooks.json");
  writeFileSync(hooksPath, JSON.stringify(hooks, null, 1));
  chmodSync(hooksPath, 0o444); // the guard also refuses writes to it; the git audit catches any change
}

export function renderTask(job: Job, allowlist: string[], samples: string[]): string {
  const tpl = readFileSync(join(PROMPTS, `${job.kind}.md`), "utf8");
  const vars: Record<string, string> = {
    sport: job.sport,
    base_sport: job.baseSport ?? "table_tennis",
    text: job.text ?? "",
    allowlist: allowlist.map((f) => `- \`${f}\``).join("\n"),
    samples: samples
      .map((f) => `- \`samples/${f}\` (labels: \`samples/${f.replace(".l1.jsonl", ".labels.json")}\`)`)
      .join("\n"),
    scene: job.scene ? "`scene/scene.json`" : "(none)",
  };
  return tpl.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => vars[k] ?? `{{${k}}}`);
}

/** Unified diff of the sandbox vs its base commit (untracked files included). */
export function sandboxDiff(sb: Sandbox): string {
  git(sb.dir, "add", "-A", "--intent-to-add");
  const out = execFileSync("git", ["diff", sb.baseCommit, "--", "."], { cwd: sb.dir, encoding: "utf8" });
  return out;
}

/** Paths (sandbox-relative) that differ from the base commit, whether or not the agent reported them. */
export function changedFiles(sb: Sandbox): string[] {
  git(sb.dir, "add", "-A", "--intent-to-add");
  const out = execFileSync("git", ["status", "--porcelain", "--untracked-files=all"], {
    cwd: sb.dir,
    encoding: "utf8",
  });
  return out
    .split("\n")
    .filter(Boolean)
    .map((l) => l.slice(3).trim())
    .filter((p) => !p.startsWith(".trophy/"));
}

/** Commit the final module in the sandbox and return the hash (the run's artifact). */
export function commitSandbox(sb: Sandbox, message: string): string {
  git(sb.dir, "add", "-A");
  git(
    sb.dir,
    "-c",
    "user.name=trophy-droid",
    "-c",
    "user.email=droid@trophy.local",
    "commit",
    "-q",
    "-m",
    message,
    "--allow-empty",
  );
  return git(sb.dir, "rev-parse", "HEAD");
}
