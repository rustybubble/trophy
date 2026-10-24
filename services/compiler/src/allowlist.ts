/**
 * What the Droid may touch inside its sandbox. Pure functions, enforced by the runner's permission handler and
 * re-checked against `git status` after the run; the agent is never trusted to police itself.
 */
import { isAbsolute, normalize, relative, sep } from "node:path";

export type JobKind = "compile" | "house_rule" | "retune";

export const MODULE_FILES = ["config.yaml", "events.py", "rules.yaml"] as const;

/** Files (relative to the sandbox root) the Droid may create or edit for a job. */
export function editableFiles(kind: JobKind, sport: string): string[] {
  const dir = `sports/${sport}`;
  switch (kind) {
    case "compile":
      return MODULE_FILES.map((f) => `${dir}/${f}`);
    case "house_rule":
      return [`${dir}/rules.yaml`];
    case "retune":
      return [`${dir}/config.yaml`, `${dir}/events.py`];
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

/** The one command the Droid may run: the test gate, optionally with flags. */
const TEST_CMD = /^(\.\/)?replay_test(\s+--?[a-z-]+(=\S+|\s+\S+)?)*\s*$/;

export function isAllowedCommand(command: string): boolean {
  const c = command.trim();
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
  return TEST_CMD.test(c);
}
