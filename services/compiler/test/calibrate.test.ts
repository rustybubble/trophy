/**
 * calibrate_checks end to end with a scripted agent: the real sandbox (golden library copy, field, 3D fixtures,
 * rules), the real check_test gate (engine venv), the real allowlist audit, then approve. Only the LLM is replaced.
 *
 * Skipped when the engine venv is missing. The tests that need a green gate also skip, with the reason, when the
 * golden library itself does not pass check_test on the fixtures right now (the library, the gate and the fixtures
 * are Agent 3's work in progress; a red golden says nothing about the compiler).
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { DroidRun } from "@trophy/contracts";

import type { Agent, AgentEvent, AgentFactory } from "../src/agent.ts";
import { approveChecks } from "../src/approve.ts";
import type { CompilerConfig } from "../src/config.ts";
import { REPO_ROOT } from "../src/config.ts";
import { runJob } from "../src/runner.ts";
import type { Job } from "../src/sandbox.ts";
import type { RunSink } from "../src/sink.ts";

const ENGINE_PY = join(REPO_ROOT, "services/engine/.venv/bin/python");
const SAMPLES = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis_3d");
const GOLDEN = join(REPO_ROOT, "sports/table_tennis/checks");
const HAVE_ENGINE = existsSync(ENGINE_PY) && existsSync(SAMPLES) && existsSync(GOLDEN);
const TIMEOUT = 90_000; // each gate run is ~2 s on the 3D fixtures; a repair test runs it twice

/** Why the unedited golden library does not pass the gate on the fixtures right now, or null when it does. */
function goldenRed(): string | null {
  if (!HAVE_ENGINE) return "no engine venv / fixtures / golden library";
  const r = spawnSync(
    ENGINE_PY,
    [
      "-m",
      "trophy_engine.check_test.cli",
      "--checks",
      GOLDEN,
      "--samples",
      SAMPLES,
      "--rules",
      join(REPO_ROOT, "sports/table_tennis"),
    ],
    { encoding: "utf8", timeout: 60_000 },
  );
  if (r.status === 0) return null;
  const fails = (r.stdout ?? "").split("\n").filter((l) => l.includes("[FAIL]"));
  return `golden library is red on the fixtures (${fails.length} failing: ${fails.map((l) => l.trim().split(/\s{2,}/)[0]).join(", ")})`;
}
const RED = goldenRed();

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

function config(over: Partial<CompilerConfig> = {}): CompilerConfig {
  const runsDir = mkdtempSync(join(tmpdir(), "trophy-cal-runs-"));
  dirs.push(runsDir);
  return {
    factoryApiKey: "test-only-not-a-key",
    droidExecPath: undefined,
    model: "fake",
    reasoningEffort: "low",
    timeoutMs: TIMEOUT,
    maxAttempts: 3,
    enginePython: ENGINE_PY,
    runsDir,
    spacetimeUri: "",
    spacetimeModule: "trophy",
    spacetimeCompilerToken: "",
    port: 8200,
    ...over,
  };
}

function scripted(turns: Array<(dir: string, emit: (e: AgentEvent) => void) => void>): AgentFactory {
  return async (ctx) => {
    let n = 0;
    const agent: Agent = {
      async turn(prompt, onEvent) {
        const fn = turns[n++];
        if (!fn) return { success: false, text: "", error: "script exhausted" };
        // the runner must name the job's own gate, never the module gate, in every prompt
        expect(prompt).toContain("./check_test");
        expect(prompt).not.toContain("replay_test");
        expect(ctx.gate).toBe("check_test");
        onEvent({ kind: "message", text: `## Plan\nturn ${n}` });
        fn(ctx.sandboxDir, onEvent);
        return { success: true, text: "## Result\ndone" };
      },
      async close() {},
    };
    return agent;
  };
}

class Collect implements RunSink {
  runs: DroidRun[] = [];
  update(run: DroidRun): void {
    this.runs.push(run);
  }
}

const JOB: Job = { kind: "calibrate_checks", sport: "table_tennis", samplesDir: SAMPLES, sessionId: "s_cal01" };
const phases = (dir: string) => join(dir, "checks/phases.py");
const bounces = (dir: string) => join(dir, "checks/bounces.py");
const MARK = "# calibrated to samples/field.json";

/** A harmless edit: a comment on the `gap_s` PARAMS line; the gate result cannot change, the diff must. */
function harmless(dir: string, emit: (e: AgentEvent) => void): void {
  const src = readFileSync(phases(dir), "utf8");
  expect(src).toContain('"gap_s":');
  writeFileSync(phases(dir), src.replace(/^(\s*"gap_s":.*)$/m, `$1  ${MARK}`));
  emit({ kind: "edit", path: phases(dir), text: "Edit checks/phases.py" });
}

describe.skipIf(!HAVE_ENGINE)("calibrate_checks (real sandbox + real check_test, scripted agent)", () => {
  it.skipIf(RED !== null)(
    `edits the library, passes the gate on the synthetic 3D samples, records diff/results/commit; approve installs it${RED ? ` [skipped: ${RED}]` : ""}`,
    async () => {
      const sink = new Collect();
      const cfg = config();
      const run = await runJob(JOB, { config: cfg, sink, agentFactory: scripted([harmless]) });
      expect(run.status, run.error ?? "").toBe("ready");
      expect(run.kind).toBe("calibrate_checks");
      expect(run.trigger.source).toBe("session");
      expect(run.base_sport).toBeNull();
      expect(run.attempt).toBe(1);
      expect(run.allowlist).toEqual([
        "checks/bounces.py",
        "checks/contacts.py",
        "checks/in_out.py",
        "checks/net_touch.py",
        "checks/phases.py",
        "checks/rally_summary.py",
        "checks/serve_toss.py",
      ]);
      expect(run.diff).toContain(`+    "gap_s":`);
      expect(run.diff).toContain(MARK);
      expect(run.diff).toContain("checks/phases.py");
      expect(run.results?.passed).toBe(true);
      expect(run.results?.tests.some((t) => t.name === "library:load" && t.pass)).toBe(true);
      expect(run.results?.tests.some((t) => t.name.endsWith("calls:winners") && t.pass)).toBe(true);
      // the baseline (reference/checks) fills the before column
      expect(run.results?.tests.some((t) => t.name.endsWith("bounces:table") && t.before)).toBe(true);
      expect(run.commit).toMatch(/^[0-9a-f]{40}$/);
      expect(run.gate_ms).toHaveLength(1);
      expect(run.steps.filter((s) => s.kind === "test").map((s) => s.text)).toContain(
        "runner: ./check_test (attempt 1)",
      );
      expect(sink.runs.at(-1)?.status).toBe("ready");

      // approve installs the checks as the session's library with calibrated: true
      const root = mkdtempSync(join(tmpdir(), "trophy-cal-root-"));
      dirs.push(root);
      const runDir = join(cfg.runsDir, run.run_id);
      // no job.json beside the run (the CLI writes one): the session is --session, else the run id
      const row = approveChecks(run, run.run_id, undefined, "judge", runDir, root);
      expect(row.path).toBe(join(root, "data/local/sessions", run.run_id, "checks"));
      expect(row.commit).toBe(run.commit);
      const lib = JSON.parse(readFileSync(join(row.path, "library.json"), "utf8"));
      expect(lib.calibrated).toBe(true);
      expect(lib.run_id).toBe(run.run_id);
      expect(lib.field_sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(lib.approved_by).toBe("judge");
      expect(readFileSync(join(row.path, "phases.py"), "utf8")).toContain(MARK);
      expect(readdirSync(row.path)).toContain("sport_module.json");
      expect(JSON.parse(readFileSync(join(row.path, "sport_module.json"), "utf8")).run_id).toBe(run.run_id);
      // with job.json, the session id and field path come from the job
      writeFileSync(join(runDir, "job.json"), JSON.stringify(JOB));
      const dest = join(root, "data/local/sessions", "s_cal01", "checks");
      expect(approveChecks(run, run.run_id, undefined, "judge", runDir, root).path).toBe(dest);
      const lib2 = JSON.parse(readFileSync(join(dest, "library.json"), "utf8"));
      expect(lib2.session_id).toBe("s_cal01");
      expect(lib2.field).toBe(join(SAMPLES, "field.json"));
      // --session wins over both
      expect(approveChecks(run, run.run_id, "s_other", "judge", runDir, root).path).toContain("/s_other/");
    },
    TIMEOUT,
  );

  it(
    "fails a run that writes checks/library.json or the reference copy, even if the gate would pass",
    async () => {
      const run = await runJob(JOB, {
        config: config(),
        sink: new Collect(),
        agentFactory: scripted([
          (dir, emit) => {
            harmless(dir, emit);
            writeFileSync(join(dir, "checks/library.json"), JSON.stringify({ calibrated: true }));
          },
        ]),
      });
      expect(run.status).toBe("failed");
      expect(run.error).toContain("allowlist violation");
      expect(run.error).toContain("checks/library.json");
      expect(run.gate_ms).toEqual([]); // the audit fails the run before the gate runs

      const run2 = await runJob(JOB, {
        config: config(),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) =>
            writeFileSync(join(dir, "reference/checks/phases.py"), "PARAMS = {}\ndef check(*a, **k):\n    return {}\n"),
        ]),
      });
      expect(run2.status).toBe("failed");
      expect(run2.error).toContain("allowlist violation");
      expect(run2.error).toContain("reference/checks/phases.py");
    },
    TIMEOUT,
  );

  it.skipIf(RED !== null)(
    `repairs a breaking edit: a syntax error in bounces.py fails library:load, attempt 2 passes${RED ? ` [skipped: ${RED}]` : ""}`,
    async () => {
      const sink = new Collect();
      const run = await runJob(JOB, {
        config: config(),
        sink,
        agentFactory: scripted([
          (dir, emit) => {
            writeFileSync(bounces(dir), readFileSync(bounces(dir), "utf8").replace("PARAMS = {", "PARAMS = {{"));
            emit({ kind: "edit", path: bounces(dir), text: "Edit checks/bounces.py" });
          },
          (dir, emit) => {
            // restore from the read-only reference, then a real (harmless) change so the run is not a no-op
            writeFileSync(bounces(dir), readFileSync(join(dir, "reference/checks/bounces.py"), "utf8"));
            harmless(dir, emit);
          },
        ]),
      });
      expect(run.status, run.error ?? "").toBe("ready");
      expect(run.attempt).toBe(2);
      expect(run.gate_ms).toHaveLength(2);
      expect(run.steps.some((s) => s.kind === "repair")).toBe(true);
      const failing = sink.runs.find((r) => r.results && !r.results.passed);
      expect(
        failing?.results?.tests.some((t) => t.name === "library:load" && !t.pass && /syntax/i.test(t.detail ?? "")),
      ).toBe(true);
      expect(run.results?.passed).toBe(true);
      expect(run.diff).toContain(MARK);
      expect(run.diff).not.toContain("PARAMS = {{");
    },
    TIMEOUT,
  );
});
