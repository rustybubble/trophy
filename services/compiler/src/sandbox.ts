/**
 * The Droid's sandbox: a fresh directory (its own git repository, so every edit is a diff against a base commit)
 * containing only what the job needs.
 *
 * Module jobs (compile, house_rule, retune):
 *   sports/<sport>/           the module to produce or edit (the only editable files)
 *   reference/<base_sport>/   the golden module to derive from (compile jobs; read-only)
 *   reference/base/           house_rule: the module with the pack in force (the gate's baseline; read-only)
 *   schema/                   rulepack, sportmodule and event JSON Schemas
 *   scene/scene.json          the scene descriptor (compile and retune jobs)
 *   samples/*.l1.jsonl + .labels.json          (sports with events.py)
 *   fixtures/*.events.jsonl + .labels.json     (annotated sports, D-44)
 *   session/session.json      house_rule: this game's events so far (re-judged: calls_changed is real, D-43)
 *   replay_test               the test gate, pinned to the engine venv; the one command the Droid may run
 *
 * interpreter (D-43): the sport's let/out/fault interpreter, its rules.yaml
 *   sports/<sport>/rules.yaml        the one editable file (seeded from the approved interpreter, if any)
 *   sports/<sport>/config.yaml, RULES.md, events.py (if any)     read-only
 *   reference/table_tennis/rules.yaml  the golden pack, as a worked example (read-only)
 *   reference/events.md              the event vocabulary (types and payload fields)
 *   fixtures/*.events.jsonl + .labels.json   hand-annotated plays and the calls they must produce
 *   samples/                         the golden layer-1 fixtures (sports with events.py)
 *
 * calibrate_checks (D-36):
 *   checks/*.py + library.json   a copy of the golden check library to specialise (the *.py are the editable files)
 *   reference/checks/            the same copy, read-only (the gate's "before" column)
 *   samples/field.json + *.track3d.jsonl + *.labels3d.json   this calibration and its labelled fused tracks
 *   rules/<sport>/               config.yaml, events.py, rules.yaml (read-only; the gate scores the events with them)
 *   schema/track3d.schema.json
 *   check_test                   the gate; the one command the Droid may run
 *
 * Both:
 *   TASK.md                   the brief, the allowlist and the pass criteria
 *
 * No secrets, no repo, no network beyond the Factory API (the permission handler refuses every other command).
 */
import { execFileSync } from "node:child_process";
import { chmodSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { editableFiles, type GateScript, gateScript, type JobKind, MODULE_FILES } from "./allowlist.ts";
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
  /** calibrate_checks: this calibration's field.json (defaults to <samplesDir>/field.json) */
  fieldPath?: string;
  /** calibrate_checks: the check library to specialise (defaults to the repo's sports/<sport>/checks) */
  checksDir?: string;
  /** calibrate_checks: the session the approved library belongs to */
  sessionId?: string;
  gameId?: string;
  ruleVersion?: string;
  /** house_rule: the pack in force (rules stack: the run starts from the last applied pack), from the engine */
  basePack?: string;
  /** house_rule: the session.json the engine dumped (the gate re-judges it against the pack in force) */
  session?: string;
  /** annotated fixtures (*.events.jsonl + *.labels.json); default evals/fixtures/annotated/<sport> when it exists */
  fixturesDir?: string;
  /** a run requested through request_droid_run keeps the row's run id */
  runId?: string;
  /** interpreter: who asked (sport_module = a game started without one; user = Regenerate; cli) */
  triggerSource?: "cli" | "sport_module" | "user";
  /** new_check: the referee's question that no session check answers (interfaces-v1 section 20) */
  newCheck?: {
    /** the new check's name: checks/<name>.py, [a-z][a-z0-9_]* */
    name: string;
    question: string;
    hint?: string;
    /** the session's fused 3D track (a snapshot) and its field.json */
    sessionTrack: string;
    sessionField: string;
    /** the arguments the referee asked with (t_s, or t0/t1) */
    query: Record<string, unknown>;
  };
}

export interface Sandbox {
  dir: string;
  allowlist: string[];
  baseCommit: string;
  /** The directory the Droid edits: sports/<sport> for module jobs, checks/ for calibrate_checks */
  moduleDir: string;
  /** The gate script's name (`replay_test` | `check_test`), also the only command the sandbox allows */
  gate: GateScript;
}

function git(dir: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd: dir, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

export function createSandbox(job: Job, dir: string, enginePython: string, root = REPO_ROOT): Sandbox {
  mkdirSync(dir, { recursive: true });
  if (readdirSync(dir).length) throw new Error(`sandbox dir is not empty: ${dir}`);
  const gate = gateScript(job.kind);
  const { moduleDir, allowlist, samples, gateCmd, fixtures } =
    job.kind === "new_check"
      ? layoutNewCheck(job, dir, root)
      : job.kind === "calibrate_checks"
        ? layoutChecks(job, dir, root)
        : job.kind === "interpreter"
          ? layoutInterpreter(job, dir, root)
          : layoutModule(job, dir, root);
  // the gate: a fixed script so the Droid cannot vary the interpreter, module or samples; it runs the Droid-written
  // code jailed (review blocker 2): a clean env (no keys), isolated Python, no network, writes only in the sandbox
  const script = gateScriptText(gateCmd.module, gateCmd.args, enginePython);
  writeFileSync(join(dir, gate), script);
  chmodSync(join(dir, gate), 0o755);
  writeFileSync(join(dir, ".gitignore"), ".trophy/\n__pycache__/\n");
  writeFileSync(join(dir, "TASK.md"), renderTask(job, allowlist, samples, fixtures ?? []));
  installGuard(dir, allowlist, [`./${gate}`]);
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
  return { dir, allowlist, baseCommit, moduleDir, gate };
}

interface Layout {
  moduleDir: string;
  allowlist: string[];
  /** sample file names listed in TASK.md */
  samples: string[];
  /** annotated fixture names listed in TASK.md */
  fixtures?: string[];
  gateCmd: { module: string; args: string };
}

/** The annotated fixtures for a sport: the job's dir, else evals/fixtures/annotated/<sport> if it has any. */
function fixturesFor(job: Job, root: string): string | undefined {
  const d = job.fixturesDir ?? join(root, "evals/fixtures/annotated", job.sport);
  return existsSync(d) && readdirSync(d).some((f) => f.endsWith(".events.jsonl")) ? d : undefined;
}

/** Copy *.events.jsonl + their *.labels.json into <dir>/fixtures; returns the event file names. */
function copyFixtures(src: string, dir: string): string[] {
  const out = join(dir, "fixtures");
  mkdirSync(out, { recursive: true });
  const names: string[] = [];
  for (const f of readdirSync(src).sort()) {
    if (f.endsWith(".events.jsonl")) {
      const labels = f.replace(".events.jsonl", ".labels.json");
      if (!existsSync(join(src, labels))) throw new Error(`${src}/${f}: no ${labels} next to it`);
      cpSync(join(src, f), join(out, f));
      cpSync(join(src, labels), join(out, labels));
      names.push(f);
    }
  }
  return names;
}

/** Copy layer-1 samples (*.l1.jsonl + *.labels.json) into <dir>/samples; returns the sample names (maybe none). */
function copySamples(src: string | undefined, dir: string): string[] {
  const out = join(dir, "samples");
  mkdirSync(out, { recursive: true });
  const samples: string[] = [];
  if (!src || !existsSync(src)) return samples;
  for (const f of readdirSync(src)) {
    if (f.endsWith(".l1.jsonl") || f.endsWith(".labels.json")) {
      cpSync(join(src, f), join(out, f));
      if (f.endsWith(".l1.jsonl")) samples.push(f);
    }
  }
  return samples.sort();
}

/** The files of a module directory that exist: config.yaml + rules.yaml, events.py unless it is annotated (D-44). */
function moduleFiles(src: string): string[] {
  return MODULE_FILES.filter((f) => existsSync(join(src, f)));
}

function layoutModule(job: Job, dir: string, root: string): Layout {
  const schemaDir = join(dir, "schema");
  mkdirSync(schemaDir);
  for (const f of ["rulepack", "sportmodule", "event", "scene"]) {
    cpSync(join(root, "packages/contracts", `${f}.schema.json`), join(schemaDir, `${f}.schema.json`));
  }
  const src =
    job.kind === "compile"
      ? (job.moduleDir ?? join(root, "sports", job.baseSport ?? "table_tennis"))
      : (job.moduleDir ?? join(root, "sports", job.sport));
  const annotated = !existsSync(join(src, "events.py"));
  const samples = annotated ? copySamples(undefined, dir) : copySamples(job.samplesDir, dir);
  const fxSrc = job.kind === "house_rule" ? fixturesFor(job, root) : undefined;
  const fixtures = fxSrc ? copyFixtures(fxSrc, dir) : [];
  if (!samples.length && !fixtures.length) throw new Error(`${job.samplesDir}: no *.l1.jsonl samples`);
  if (job.scene) {
    mkdirSync(join(dir, "scene"));
    cpSync(job.scene, join(dir, "scene", "scene.json"));
  }
  const moduleDir = join(dir, "sports", job.sport);
  mkdirSync(moduleDir, { recursive: true });
  const args: string[] = [`--module "sports/${job.sport}"`];
  if (job.kind === "compile") {
    const base = job.baseSport ?? "table_tennis";
    // only the three module files: sports/<sport>/ also holds checks/ (D-36), which is not this job's business
    mkdirSync(join(dir, "reference", base), { recursive: true });
    for (const f of MODULE_FILES) cpSync(join(src, f), join(dir, "reference", base, f));
    // Seed the new module with the reference so the Droid edits (a 90 s job) instead of retyping events.py.
    for (const f of MODULE_FILES) cpSync(join(src, f), join(moduleDir, f));
  } else {
    const files = moduleFiles(src);
    for (const f of annotated ? ["config.yaml", "rules.yaml"] : MODULE_FILES) {
      if (!files.includes(f)) throw new Error(`${src}/${f} missing`);
    }
    for (const f of files) cpSync(join(src, f), join(moduleDir, f));
    if (job.kind === "house_rule") {
      // rules stack (D-43): start from the pack in force, which the engine handed over, not the golden file
      if (job.basePack) cpSync(job.basePack, join(moduleDir, "rules.yaml"));
      // the same module, read-only, as the gate's baseline ("before" column and calls_changed)
      const base = join(dir, "reference", "base");
      mkdirSync(base, { recursive: true });
      for (const f of files) cpSync(join(moduleDir, f), join(base, f));
      args.push("--baseline reference/base", "--house-rule");
      if (job.session) {
        mkdirSync(join(dir, "session"));
        cpSync(job.session, join(dir, "session", "session.json"));
        args.push("--session session/session.json");
      }
    }
  }
  if (samples.length) args.push("--samples samples");
  if (fixtures.length) args.push("--annotated fixtures");
  return {
    moduleDir,
    allowlist: editableFiles(job.kind, job.sport),
    samples,
    fixtures,
    gateCmd: { module: "trophy_engine.replay_test.cli", args: args.join(" ") },
  };
}

/**
 * interpreter (D-43): write the sport's rules.yaml so the annotated plays produce their labelled calls. The rulebook
 * summary, the court, the event vocabulary and the golden table-tennis pack are the inputs; the gate replays every
 * fixture through the engine with the candidate pack (and the layer-1 golden fixtures when the sport has events.py).
 */
function layoutInterpreter(job: Job, dir: string, root: string): Layout {
  const src = job.moduleDir ?? join(root, "sports", job.sport);
  if (!existsSync(join(src, "config.yaml"))) throw new Error(`${src}/config.yaml missing (the sport's court and name)`);
  const schemaDir = join(dir, "schema");
  mkdirSync(schemaDir);
  for (const f of ["rulepack", "event"]) {
    cpSync(join(root, "packages/contracts", `${f}.schema.json`), join(schemaDir, `${f}.schema.json`));
  }
  const moduleDir = join(dir, "sports", job.sport);
  mkdirSync(moduleDir, { recursive: true });
  for (const f of ["config.yaml", "events.py", "RULES.md", "rules.yaml"]) {
    if (existsSync(join(src, f))) cpSync(join(src, f), join(moduleDir, f));
  }
  mkdirSync(join(dir, "reference", "table_tennis"), { recursive: true });
  cpSync(join(root, "sports/table_tennis/rules.yaml"), join(dir, "reference/table_tennis/rules.yaml"));
  writeFileSync(
    join(dir, "reference", "events.md"),
    eventVocabulary(join(root, "packages/contracts/event.schema.json")),
  );
  const fx = fixturesFor(job, root);
  if (!fx)
    throw new Error(`no annotated fixtures for ${job.sport} (evals/fixtures/annotated/${job.sport}/*.events.jsonl)`);
  const fixtures = copyFixtures(fx, dir);
  const hasEvents = existsSync(join(src, "events.py"));
  const samples = hasEvents ? copySamples(job.samplesDir, dir) : copySamples(undefined, dir);
  const args = [`--module "sports/${job.sport}"`, "--annotated fixtures"];
  if (samples.length) args.push("--samples samples");
  return {
    moduleDir,
    allowlist: editableFiles("interpreter", job.sport),
    samples,
    fixtures,
    gateCmd: { module: "trophy_engine.replay_test.cli", args: args.join(" ") },
  };
}

/** The event vocabulary as a short Markdown table (types and payload fields), from event.schema.json. */
export function eventVocabulary(schemaPath: string): string {
  const s = JSON.parse(readFileSync(schemaPath, "utf8")) as {
    $defs: Record<
      string,
      {
        enum?: string[];
        properties?: Record<string, { enum?: unknown[]; type?: unknown; description?: string; $ref?: string }>;
        required?: string[];
        description?: string;
      }
    >;
  };
  const d = s.$defs;
  const lines = [
    "# Event vocabulary (trophy.event.v1, from schema/event.schema.json)",
    "",
    "Every event: `type`, `t_game_s`, `side` (A|B, when it belongs to a side), `team_id`, `pos_m`, `conf`, `source`",
    "(`annotated` for hand-marked events) and `payload`. In CEL: `ev.type`, `ev.side`, `ev.team_id`, `ev.payload.<field>`.",
    "Use `has(ev.payload.x)` before reading an optional field (missing fields are absent, never null).",
    "",
    "| type | payload fields (required in bold) |",
    "|---|---|",
  ];
  for (const t of d.EventType?.enum ?? []) {
    const name = `${t
      .split("_")
      .map((w) => w[0]!.toUpperCase() + w.slice(1))
      .join("")}Payload`;
    const p = d[name];
    if (!p?.properties) {
      lines.push(`| \`${t}\` | (none) |`);
      continue;
    }
    const req = new Set(p.required ?? []);
    const fields = Object.entries(p.properties)
      .filter(([k]) => k !== "calib_untrusted" && k !== "onset_id")
      .map(([k, v]) => {
        const ty = v.enum
          ? v.enum.join("\\|")
          : v.$ref
            ? v.$ref.split("/").pop()
            : Array.isArray(v.type)
              ? v.type.join("\\|")
              : String(v.type ?? "");
        const label = req.has(k) ? `**${k}**` : k;
        return `${label} (${ty})`;
      });
    lines.push(`| \`${t}\` | ${fields.join(", ")} |`);
  }
  return lines.join("\n") + "\n";
}

const noPycache = (p: string) => !/__pycache__/.test(p);

function layoutChecks(job: Job, dir: string, root: string): Layout {
  const schemaDir = join(dir, "schema");
  mkdirSync(schemaDir);
  cpSync(join(root, "packages/contracts/track3d.schema.json"), join(schemaDir, "track3d.schema.json"));
  // the calibration and its labelled tracks
  const fieldPath = job.fieldPath ?? join(job.samplesDir, "field.json");
  if (!existsSync(fieldPath)) throw new Error(`${fieldPath}: no field.json for this calibration`);
  const samplesOut = join(dir, "samples");
  mkdirSync(samplesOut);
  cpSync(fieldPath, join(samplesOut, "field.json"));
  const samples: string[] = [];
  for (const f of readdirSync(job.samplesDir)) {
    if (f.endsWith(".track3d.jsonl") || f.endsWith(".labels3d.json")) {
      cpSync(join(job.samplesDir, f), join(samplesOut, f));
      if (f.endsWith(".track3d.jsonl")) samples.push(f);
    }
  }
  if (!samples.length) throw new Error(`${job.samplesDir}: no *.track3d.jsonl samples`);
  // the golden library, twice: checks/ to edit, reference/checks/ as the gate's "before" column
  const src = job.checksDir ?? join(root, "sports", job.sport, "checks");
  if (!existsSync(src)) throw new Error(`${src}: no check library to calibrate`);
  const moduleDir = join(dir, "checks");
  cpSync(src, moduleDir, { recursive: true, filter: noPycache });
  cpSync(src, join(dir, "reference", "checks"), { recursive: true, filter: noPycache });
  // the API the checks import, to read instead of searching the disk (reads outside the sandbox are refused)
  cpSync(join(root, "services/engine/trophy_engine/checks/api.py"), join(dir, "reference", "checks_api.py"));
  const checkFiles = readdirSync(moduleDir)
    .filter((f) => f.endsWith(".py") && !f.startsWith("_"))
    .sort();
  if (!checkFiles.length) throw new Error(`${src}: no checks (*.py)`);
  // the sport module, read-only: the gate replays the library's events through rules.yaml for the rally winners
  const modSrc = join(root, "sports", job.sport);
  const rulesDir = join(dir, "rules", job.sport);
  mkdirSync(rulesDir, { recursive: true });
  for (const f of MODULE_FILES) {
    if (!existsSync(join(modSrc, f))) throw new Error(`${modSrc}/${f} missing`);
    cpSync(join(modSrc, f), join(rulesDir, f));
  }
  return {
    moduleDir,
    allowlist: editableFiles(job.kind, job.sport, checkFiles),
    samples,
    gateCmd: {
      module: "trophy_engine.check_test.cli",
      args: `--checks checks --samples samples --field samples/field.json --baseline reference/checks --rules "rules/${job.sport}"`,
    },
  };
}

const PROMPTS = join(REPO_ROOT, "services/compiler/prompts");
export const GUARD = join(REPO_ROOT, "services/compiler/hooks/guard.py");

/**
 * The enforcement point. The Droid CLI runs project hooks from <cwd>/.factory/hooks.json before every tool call;
 * autonomy "low" auto-approves edits without asking the SDK permission handler (measured 2026-10-24), so the
 * PreToolUse hook is what keeps the agent inside the allowlist. The allowlist and the hooks file are read-only.
 * `commands` names the job's gate (`./replay_test` or `./check_test`); the guard refuses the other one.
 */
export function installGuard(dir: string, allowlist: string[], commands: string[] = ["./replay_test"]): void {
  mkdirSync(join(dir, ".trophy"), { recursive: true });
  mkdirSync(join(dir, ".factory"), { recursive: true });
  const allowPath = join(dir, ".trophy", "allowlist.json");
  writeFileSync(allowPath, JSON.stringify({ files: allowlist, commands }, null, 1));
  chmodSync(allowPath, 0o444);
  // the hook runs with whatever python the host has: `python` on Windows (python3 there is often a Store stub)
  const py = process.env.GUARD_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const cmd = `${py} "${GUARD}" "${dir}"`;
  const hooks = {
    hooksDisabled: false,
    PreToolUse: [
      {
        matcher: "Edit|Create|ApplyPatch|MultiEdit|Write|Execute|Read|Grep|Glob|LS",
        hooks: [{ type: "command", command: cmd, timeout: 10 }],
      },
    ],
  };
  const hooksPath = join(dir, ".factory", "hooks.json");
  writeFileSync(hooksPath, JSON.stringify(hooks, null, 1));
  chmodSync(hooksPath, 0o444); // the guard also refuses writes to it; the git audit catches any change
}

/**
 * new_check: the session library (read-only by the allowlist), the labelled samples for check-test, the session's own
 * track and the question's arguments. The gate is new-check-test: the library must still pass and the new check must
 * load, run deterministically on the session track and answer (.trophy/answer.json).
 */
function layoutNewCheck(job: Job, dir: string, root: string): Layout {
  const nc = job.newCheck;
  if (!nc) throw new Error("new_check job without newCheck");
  if (!/^[a-z][a-z0-9_]{0,39}$/.test(nc.name)) throw new Error(`bad check name ${JSON.stringify(nc.name)}`);
  const base = layoutChecks(job, dir, root);
  if (existsSync(join(dir, "checks", `${nc.name}.py`))) throw new Error(`checks/${nc.name}.py already exists`);
  const sessionDir = join(dir, "session");
  mkdirSync(sessionDir);
  cpSync(nc.sessionTrack, join(sessionDir, "track3d.jsonl"));
  cpSync(nc.sessionField, join(sessionDir, "field.json"));
  writeFileSync(join(sessionDir, "query.json"), JSON.stringify(nc.query, null, 1));
  return {
    ...base,
    allowlist: editableFiles("new_check", job.sport, [nc.name]),
    gateCmd: {
      module: "trophy_engine.check_test.newcheck",
      args:
        `--checks checks --samples samples --field samples/field.json --rules "rules/${job.sport}" --new ${nc.name} ` +
        "--session session/track3d.jsonl --session-field session/field.json --query session/query.json " +
        "--answer .trophy/answer.json",
    },
  };
}

export function renderTask(job: Job, allowlist: string[], samples: string[], fixtures: string[] = []): string {
  const tpl = readFileSync(join(PROMPTS, `${job.kind}.md`), "utf8");
  const labelOf = (f: string) =>
    f.endsWith(".track3d.jsonl")
      ? f.replace(".track3d.jsonl", ".labels3d.json")
      : f.replace(".l1.jsonl", ".labels.json");
  const vars: Record<string, string> = {
    sport: job.sport,
    base_sport: job.baseSport ?? "table_tennis",
    text: job.text ?? "",
    gate: `./${gateScript(job.kind)}`,
    allowlist: allowlist.map((f) => `- \`${f}\``).join("\n"),
    samples: samples.map((f) => `- \`samples/${f}\` (labels: \`samples/${labelOf(f)}\`)`).join("\n"),
    scene: job.scene ? "`scene/scene.json`" : "(none)",
    name: job.newCheck?.name ?? "",
    question: job.newCheck?.question ?? "",
    hint: job.newCheck?.hint ?? "(none)",
    query: JSON.stringify(job.newCheck?.query ?? {}),
    fixtures: fixtures.length
      ? fixtures
          .map((f) => `- \`fixtures/${f}\` (labels: \`fixtures/${f.replace(".events.jsonl", ".labels.json")}\`)`)
          .join("\n")
      : "(none)",
    samples_or_none: samples.length ? samples.map((f) => `- \`samples/${f}\``).join("\n") : "(none)",
    session: job.session
      ? "`session/session.json`: this game's events so far. The gate re-judges them with the pack in force (`reference/base/`) and with yours and lists every play whose call changes (`calls_changed`)."
      : "(no session: the game has no events yet)",
    rulebook:
      existsSync(join(REPO_ROOT, "sports", job.sport, "RULES.md")) || existsSync(join(job.moduleDir ?? "", "RULES.md"))
        ? `\`sports/${job.sport}/RULES.md\``
        : "(none: use your knowledge of the official rules, and cite them in `rule_ref`)",
    seeded:
      job.kind === "interpreter" &&
      existsSync(join(job.moduleDir ?? join(REPO_ROOT, "sports", job.sport), "rules.yaml"))
        ? `\`sports/${job.sport}/rules.yaml\` already holds the current interpreter: improve it until the gate passes.`
        : `\`sports/${job.sport}/rules.yaml\` does not exist yet: create it.`,
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

/**
 * The gate script. Never forwards its own arguments ("$@" was a bypass). The Python it runs gets `env -i` (only PATH,
 * a HOME and TMPDIR inside the sandbox), `-I -B` (no PYTHON* variables, no user site, no bytecode written outside), and
 * no network and no writes outside the sandbox: `sandbox-exec` on macOS, `unshare -rn` on Linux where permitted. Where
 * neither exists it says so on stderr and in .trophy/isolation, rather than failing silently.
 */
export function gateScriptText(module: string, args: string, enginePython: string): string {
  const profile =
    "(version 1)(allow default)(deny network*)(deny file-write*)" +
    '(allow file-write* (subpath "$SB") (literal "/dev/null") (literal "/dev/dtracehelper"))';
  return [
    "#!/bin/sh",
    `# The Droid's test gate (${module}). The only command the sandbox allows; it takes no arguments.`,
    'cd "$(dirname "$0")" || exit 2',
    'SB="$(pwd -P)"',
    "mkdir -p .trophy/home .trophy/tmp",
    `set -- "${enginePython}" -I -B -m ${module} ${args} --json .trophy/results.json --events .trophy/events.json`,
    'CLEAN="env -i PATH=/usr/bin:/bin HOME=$SB/.trophy/home TMPDIR=$SB/.trophy/tmp LANG=C.UTF-8"',
    'if [ "$(uname)" = Darwin ] && [ -x /usr/bin/sandbox-exec ]; then',
    "  echo sandbox-exec > .trophy/isolation",
    `  exec $CLEAN /usr/bin/sandbox-exec -p "${profile.replace(/"/g, '\\"')}" "$@"`,
    "elif command -v unshare >/dev/null 2>&1 && unshare -rn true 2>/dev/null; then",
    "  echo unshare > .trophy/isolation",
    '  exec $CLEAN unshare -rn "$@"',
    "else",
    "  echo none > .trophy/isolation",
    '  echo "trophy gate: no network isolation on this host (no sandbox-exec; unshare -rn refused): clean env only" >&2',
    '  exec $CLEAN "$@"',
    "fi",
    "",
  ].join("\n");
}
