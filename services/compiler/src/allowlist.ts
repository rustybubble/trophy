/**
 * What the Droid may touch inside its sandbox. Pure functions, enforced by the runner's permission handler and
 * re-checked against `git status` after the run; the agent is never trusted to police itself.
 */
import { isAbsolute, normalize, relative, sep } from "node:path";

export type JobKind = "compile" | "house_rule" | "retune" | "calibrate_checks" | "new_check" | "interpreter";

export const MODULE_FILES = ["config.yaml", "events.py", "rules.yaml"] as const;

/** house_rule: the Droid's decision {applies, rationale}, written at the sandbox root and parsed by the runner (D-43) */
export const DECISION_FILE = "decision.json";

/** The gate script each job kind runs (and the only command the Droid may run in that sandbox). */
export const GATE_SCRIPTS = ["replay_test", "check_test"] as const;
export type GateScript = (typeof GATE_SCRIPTS)[number];

export function gateScript(kind: JobKind): GateScript {
  return kind === "calibrate_checks" || kind === "new_check" ? "check_test" : "replay_test";
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
      return [`${dir}/rules.yaml`, DECISION_FILE];
    case "interpreter":
      // D-43: the sport's let/out/fault interpreter is its rule pack; config.yaml, events.py, RULES.md, the fixtures
      // and the reference stay read-only. (The rule engine has no hook to run per-event Python, so no checks/*.py.)
      return [`${dir}/rules.yaml`];
    case "retune":
      return [`${dir}/config.yaml`, `${dir}/events.py`];
    case "calibrate_checks":
      return checkFiles.filter((f) => f.endsWith(".py") && !f.startsWith("_")).map((f) => `checks/${f}`);
    case "new_check":
      // exactly one new file: checkFiles is [the new check's name]; the existing library stays untouched
      return checkFiles.map((f) => `checks/${f.endsWith(".py") ? f : `${f}.py`}`);
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

/**
 * The one command the Droid may run: the job's gate, bare, or with `--quiet` (agents add it). The gate script pins
 * every argument itself and ignores any it is given, so nothing else is needed. Single literal spaces only: no
 * newlines, tabs, redirections (`<`, `>`), globs or other arguments. Group 2 is the script name.
 */
const TEST_CMD = /^(\.\/)?(replay_test|check_test)( --quiet)?$/;
/** Printable ASCII only: a newline or other control character could smuggle a second command past a line check. */
const PRINTABLE = /^[\x20-\x7e]*$/;

/** `scripts` narrows the gate to the job's own (`["check_test"]`); by default either gate name passes. */
export function isAllowedCommand(
  command: string,
  sandboxRoot?: string,
  scripts: readonly string[] = GATE_SCRIPTS,
): boolean {
  if (!PRINTABLE.test(command)) return false;
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
    c.includes("$") ||
    c.includes("<") ||
    c.includes(">")
  ) {
    return false;
  }
  const m = TEST_CMD.exec(c);
  return m !== null && scripts.includes(m[2]!);
}
