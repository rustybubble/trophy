/**
 * The compile loop with a scripted agent: the real sandbox, the real replay_test gate (engine venv), the real
 * allowlist audit. Only the LLM is replaced. Skipped when the engine venv is missing (plain `npm test` in CI).
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { DroidRun } from "@trophy/contracts";

import type { Agent, AgentEvent, AgentFactory } from "../src/agent.ts";
import type { CompilerConfig } from "../src/config.ts";
import { REPO_ROOT } from "../src/config.ts";
import { runJob } from "../src/runner.ts";
import type { RunSink } from "../src/sink.ts";

const ENGINE_PY = join(REPO_ROOT, "services/engine/.venv/bin/python");
const SAMPLES = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis");
const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

function config(over: Partial<CompilerConfig> = {}): CompilerConfig {
  const runsDir = mkdtempSync(join(tmpdir(), "trophy-runs-"));
  dirs.push(runsDir);
  return {
    factoryApiKey: "test-only-not-a-key",
    droidExecPath: undefined,
    model: "fake",
    reasoningEffort: "low",
    timeoutMs: 60_000,
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

/** A scripted agent: one function per turn, run against the sandbox directory. */
function scripted(turns: Array<(dir: string, emit: (e: AgentEvent) => void) => void | Promise<void>>): AgentFactory {
  return async (ctx) => {
    let n = 0;
    const agent: Agent = {
      async turn(_prompt, onEvent, signal) {
        const fn = turns[n++];
        if (!fn) return { success: false, text: "", error: "script exhausted" };
        onEvent({ kind: "message", text: `## Plan\nturn ${n}` });
        await fn(ctx.sandboxDir, onEvent);
        if (signal.aborted) return { success: false, text: "", error: "aborted" };
        return { success: true, text: "## Result\ndone", tokenUsage: { input: 10, output: 5 } };
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

const rulesPath = (dir: string) => join(dir, "sports/table_tennis/rules.yaml");

describe.skipIf(!existsSync(ENGINE_PY))("runJob (real sandbox + real gate, scripted agent)", () => {
  it("drafts, fails the gate, repairs, passes, and records diff/results/commit", async () => {
    const sink = new Collect();
    const run = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "first to 7, win by 1", samplesDir: SAMPLES },
      {
        config: config(),
        sink,
        agentFactory: scripted([
          (dir, emit) => {
            // a wrong first draft: breaks the schema (family is an enum) besides changing the params
            const y = readFileSync(rulesPath(dir), "utf8")
              .replace("family: flight", "family: bouncy")
              .replace("points_to_win: 11", "points_to_win: 7");
            writeFileSync(rulesPath(dir), y);
            emit({ kind: "edit", path: rulesPath(dir), text: "Edit rules.yaml" });
          },
          (dir, emit) => {
            const y = readFileSync(rulesPath(dir), "utf8")
              .replace("family: bouncy", "family: flight")
              .replace("win_by: 2", "win_by: 1");
            writeFileSync(rulesPath(dir), y);
            emit({ kind: "edit", path: rulesPath(dir), text: "Edit rules.yaml" });
          },
        ]),
      },
    );
    expect(run.status, run.error ?? "").toBe("ready");
    expect(run.attempt).toBe(2);
    expect(run.plan_md).toContain("## Plan");
    expect(run.diff).toContain("+    points_to_win: 7");
    expect(run.results?.passed).toBe(true);
    expect(run.commit).toMatch(/^[0-9a-f]{40}$/);
    expect(run.gate_ms).toHaveLength(2);
    expect(run.steps.map((s) => s.kind)).toContain("repair");
    expect(run.token_usage).toEqual({ input: 20, output: 10 });
    // the sink saw the plan before the result
    const statuses = sink.runs.map((r) => r.status);
    expect(statuses[0]).toBe("queued");
    expect(statuses.at(-1)).toBe("ready");
    expect(sink.runs.some((r) => r.status === "running" && r.plan_md && !r.results)).toBe(true);
    const failing = sink.runs.find((r) => r.results && !r.results.passed);
    expect(failing?.results?.tests.some((t) => t.name === "module:load" && !t.pass)).toBe(true);
  });

  it("fails a run whose agent edited outside the allowlist, even if the gate would pass", async () => {
    const run = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "x", samplesDir: SAMPLES },
      {
        config: config(),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) => {
            writeFileSync(join(dir, "sports/table_tennis/events.py"), "def events(o, s):\n    return []\n");
          },
        ]),
      },
    );
    expect(run.status).toBe("failed");
    expect(run.error).toContain("allowlist violation");
    expect(run.error).toContain("sports/table_tennis/events.py");
  });

  it("gives up after max_attempts with the last test table recorded", async () => {
    const run = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "x", samplesDir: SAMPLES },
      {
        config: config({ maxAttempts: 2 }),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) => writeFileSync(rulesPath(dir), "sport: table_tennis\n"),
          (dir) => writeFileSync(rulesPath(dir), "sport: table_tennis\nfamily: flight\n"),
        ]),
      },
    );
    expect(run.status).toBe("failed");
    expect(run.attempt).toBe(2);
    expect(run.error).toContain("after 2 attempt");
    expect(run.results?.passed).toBe(false);
  });

  it("times out", async () => {
    const run = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "x", samplesDir: SAMPLES },
      {
        config: config({ timeoutMs: 300 }),
        sink: new Collect(),
        agentFactory: async () => ({
          turn: (_p, _e, signal) =>
            new Promise((resolve) =>
              signal.addEventListener("abort", () => resolve({ success: false, text: "", error: "aborted" })),
            ),
          close: async () => {},
        }),
      },
    );
    expect(run.status).toBe("failed");
    expect(run.error).toContain("timeout");
  });
});
