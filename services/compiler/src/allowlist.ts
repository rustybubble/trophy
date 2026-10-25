/**
 * What the Droid may touch inside its sandbox. Pure functions, enforced by the runner's permission handler and
 * re-checked against `git status` after the run; the agent is never trusted to police itself.
 */
import { isAbsolute, normalize, relative, sep } from "node:path";

export type JobKind = "compile" | "house_rule" | "retune" | "calibrate_checks";

export const MODULE_FILES = ["config.yaml", "events.py", "rules.yaml"] as const;

/** The gate script each job kind runs (and the only command the Droid may run in that sandbox). */
export const GATE_SCRIPTS = ["replay_test", "check_test"] as const;
export type GateScript = (typeof GATE_SCRIPTS)[number];

export function gateScript(kind: JobKind): GateScript {
  return kind === "calibrate_checks" ? "check_test" : "replay_test";
}

/**
 * Files (relative to the sandbox root) the Droid may create or edit for a job. A calibrate_checks job may edit
 * every check file the copied library holds (`checkFiles`, e.g. `["bounces.py", ...]`), never library.json.
 */
export function editableFiles(kind: JobKind, sport: string, checkFiles: readonly string[] = []): string[] {
  const dir = `sports/${sport}`;
  switch (kind) {
    case "compile":
      return MODULE_FILES.map((f) => `${dir}/${f}`);
    case "house_rule":
      return [`${dir}/rules.yaml`];
    case "retune":
      return [`${dir}/config.yaml`, `${dir}/events.py`];
    case "calibrate_checks":
      return checkFiles.filter((f) => f.endsWith(".py") && !f.startsWith("_")).map((f) => `checks/${f}`);
  }
}

/** Normalise a path the agent gave us to a sandbox-relative one; null when it escapes the sandbox. */
export function sandboxRelative(sandboxRoot: string, filePath: string): string | null {
  const abs = isAbsolute(filePath) ? normalize(filePath) : normalize(`${sandboxRoot}${sep}${filePath}`);
  const rel = relative(sandboxRoot, abs);
  if (!rel || rel.startsWith("..") || isAbsolute(rel)) return null;
  return rel.split(sep).join("/");
}

export function isAllowedEdit(sandboxRoot: string, filePath: string, allowed: readonly string[]): boolean {
  const rel = sandboxRelative(sandboxRoot, filePath);
  return rel !== null && allowed.includes(rel);
}

/** The one command the Droid may run: a test gate, optionally with flags. Group 2 is the script name. */
const TEST_CMD = /^(\.\/)?(replay_test|check_test)(\s+--?[a-z-]+(=\S+|\s+\S+)?)*\s*$/;

/** `scripts` narrows the gate to the job's own (`["check_test"]`); by default either gate name passes. */
export function isAllowedCommand(
  command: string,
  sandboxRoot?: string,
  scripts: readonly string[] = GATE_SCRIPTS,
): boolean {
  let c = command.trim();
  if (sandboxRoot) {
    // Agents like to prefix `cd <sandbox> && ./replay_test`; allow exactly that directory, quoted or not.
    const dir = sandboxRoot.replace(/\/$/, "");
    for (const q of ['"', "'", ""]) {
      const prefix = `cd ${q}${dir}${q} && `;
      if (c.startsWith(prefix)) {
        c = c.slice(prefix.length);
        break;
      }
    }
  }
  if (
    c.includes("&&") ||
    c.includes("||") ||
    c.includes(";") ||
    c.includes("|") ||
    c.includes("`") ||
    c.includes("$(")
  ) {
    return false;
  }
  const m = TEST_CMD.exec(c);
  return m !== null && scripts.includes(m[2]!);
}
