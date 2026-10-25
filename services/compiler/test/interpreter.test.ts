/**
 * D-43 in the compiler: the interpreter job (its sandbox, its tight allowlist enforced by the guard, the real gate over
 * the SYNTHETIC annotated fixtures) and the house-rule decision (decision.json, rules stacking from the engine's pack,
 * calls_changed from this session). Only the LLM is replaced by a scripted agent.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { DroidRun } from "@trophy/contracts";

import type { Agent, AgentEvent, AgentFactory } from "../src/agent.ts";
import { type CompilerConfig, defaultEnginePython, REPO_ROOT } from "../src/config.ts";
import { readDecision, runJob } from "../src/runner.ts";
import { createSandbox, GUARD } from "../src/sandbox.ts";
import { DroidRunSpacetimeSink, HouseRuleSpacetimeSink, type RunSink, Serial } from "../src/sink.ts";
import { isRunRequest } from "../src/spacetime.ts";

const ENGINE_PY = defaultEnginePython();
const TT_SAMPLES = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis");
const TT_FIX = join(REPO_ROOT, "evals/fixtures/annotated/table_tennis/SYNTHETIC_let_out_fault.events.jsonl");
const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});
function tmp(prefix = "trophy-int-"): string {
  const d = mkdtempSync(join(tmpdir(), prefix));
  dirs.push(d);
  return d;
}

function config(over: Partial<CompilerConfig> = {}): CompilerConfig {
  return {
    factoryApiKey: "test-only-not-a-key",
    droidExecPath: undefined,
    model: "fake",
    reasoningEffort: "low",
    timeoutMs: 60_000,
    maxAttempts: 3,
    enginePython: ENGINE_PY,
    runsDir: tmp("trophy-runs-"),
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
      async turn(_prompt, onEvent) {
        const fn = turns[n++];
        if (!fn) return { success: false, text: "", error: "script exhausted" };
        onEvent({ kind: "message", text: `## Plan\nturn ${n}` });
        fn(ctx.sandboxDir, onEvent);
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
    this.runs.push(structuredClone(run));
  }
}

function guard(sb: string, tool: string, input: object): number | null {
  return spawnSync("python3", [GUARD, sb], { input: JSON.stringify({ tool_name: tool, tool_input: input }) }).status;
}

const RULE = 'tier: AUTO\n    kind: point\n    check: code\n    text: "x"\n    speech: "x"';
function badmintonPack(withLet: boolean): string {
  return [
    "sport: badminton",
    "family: flight",
    "version: 1",
    "name: Badminton (pickup)",
    "teams:",
    "  - {team_id: A, name: Near}",
    "  - {team_id: B, name: Far}",
    "field: {frame: centre, landmarks: []}",
    "scoring: {template: rally, params: {points_to_win: 21, win_by: 2, cap: 30, serves_per_turn: 1}}",
    "rules:",
    ...(withLet
      ? [
          "  - id: net_let",
          "    name: Shuttle caught on the net",
          `    ${RULE}`,
          "    when: \"ev.type == 'net' && ev.payload.kind == 'touch' && !ev.payload.serve\"",
          "    outcome: let",
        ]
      : []),
    "  - id: net_fault",
    "    name: Into the net",
    `    ${RULE}`,
    "    when: \"ev.type == 'net' && ev.payload.kind == 'into'\"",
    "    outcome: fault",
    '    team: "opponent(ev.payload.from_side)"',
    "    points: 1",
    "  - id: out",
    "    name: Lands out",
    `    ${RULE}`,
    "    when: \"ev.type == 'bounce' && ev.payload.p_in < 0.5\"",
    "    outcome: out",
    '    team: "ev.side"',
    "    points: 1",
    "  - id: in",
    "    name: Lands in",
    `    ${RULE}`,
    "    when: \"ev.type == 'bounce' && ev.payload.p_in >= 0.5\"",
    "    outcome: point",
    '    team: "opponent(ev.side)"',
    "    points: 1",
    "",
  ].join("\n");
}

const LET_RULE = `rules:
  - id: serve_net_let
    name: Serve clips the net
    tier: AUTO
    kind: point
    when: "ev.type == 'net' && ev.payload.kind == 'touch' && has(ev.payload.serve) && ev.payload.serve && params.net_let_on_serve"
    check: code
    outcome: let
    text: "Let: the serve clipped the net"
    speech: "Let."
    house_rule: true
`;

describe("interpreter sandbox", () => {
  it("gives the Droid the rulebook, court, vocabulary, reference and fixtures, and only rules.yaml to write", () => {
    const sb = createSandbox(
      { kind: "interpreter", sport: "badminton", samplesDir: join(REPO_ROOT, "evals/fixtures/synthetic/badminton") },
      join(tmp(), "ws"),
      "/usr/bin/false",
    );
    expect(sb.allowlist).toEqual(["sports/badminton/rules.yaml"]);
    expect(readdirSync(join(sb.dir, "sports/badminton")).sort()).toEqual(["RULES.md", "config.yaml"]);
    expect(existsSync(join(sb.dir, "reference/table_tennis/rules.yaml"))).toBe(true);
    const vocab = readFileSync(join(sb.dir, "reference/events.md"), "utf8");
    expect(vocab).toContain("| `net` |");
    expect(vocab).toContain("**from_side**");
    expect(readdirSync(join(sb.dir, "fixtures")).sort()).toEqual([
      "SYNTHETIC_rallies.events.jsonl",
      "SYNTHETIC_rallies.labels.json",
    ]);
    const task = readFileSync(join(sb.dir, "TASK.md"), "utf8");
    expect(task).not.toContain("{{");
    expect(task).toContain("does not exist yet: create it");
    expect(task).toContain("`fixtures/SYNTHETIC_rallies.events.jsonl`");
    const gate = readFileSync(join(sb.dir, "replay_test"), "utf8");
    expect(gate).toContain('--module "sports/badminton" --annotated fixtures');
    expect(gate).not.toContain("--samples");
    // the guard: rules.yaml only; never the court, the rulebook, the labels, the reference or the gate
    expect(guard(sb.dir, "Create", { file_path: join(sb.dir, "sports/badminton/rules.yaml") })).toBe(0);
    for (const f of [
      "sports/badminton/config.yaml",
      "sports/badminton/RULES.md",
      "sports/badminton/events.py",
      "sports/badminton/checks/x.py",
      "fixtures/SYNTHETIC_rallies.labels.json",
      "reference/table_tennis/rules.yaml",
      "replay_test",
      "decision.json",
    ]) {
      expect(guard(sb.dir, "Edit", { file_path: join(sb.dir, f) }), f).toBe(2);
    }
    expect(guard(sb.dir, "Execute", { command: "./replay_test" })).toBe(0);
    expect(guard(sb.dir, "Execute", { command: "./check_test" })).toBe(2);
    expect(guard(sb.dir, "Read", { file_path: join(REPO_ROOT, "evals/fixtures/annotated/badminton") })).toBe(2);
  });

  it("seeds table tennis from its interpreter and keeps the golden layer-1 fixtures in the gate", () => {
    const sb = createSandbox(
      { kind: "interpreter", sport: "table_tennis", samplesDir: TT_SAMPLES },
      join(tmp(), "ws"),
      "/usr/bin/false",
    );
    expect(readdirSync(join(sb.dir, "sports/table_tennis")).sort()).toEqual([
      "RULES.md",
      "config.yaml",
      "events.py",
      "rules.yaml",
    ]);
    expect(readFileSync(join(sb.dir, "replay_test"), "utf8")).toContain("--annotated fixtures --samples samples");
    expect(readFileSync(join(sb.dir, "TASK.md"), "utf8")).toContain("already holds the current interpreter");
  });

  it("refuses a sport with no annotated fixtures", () => {
    expect(() =>
      createSandbox(
        { kind: "interpreter", sport: "badminton", samplesDir: "/nope", fixturesDir: tmp() },
        join(tmp(), "ws"),
        "/usr/bin/false",
      ),
    ).toThrow(/no annotated fixtures/);
  });
});

describe("house-rule decision", () => {
  it("reads and validates decision.json", () => {
    const d = tmp();
    expect(readDecision(d).error).toContain("missing");
    writeFileSync(join(d, "decision.json"), "{nope");
    expect(readDecision(d).error).toContain("not JSON");
    writeFileSync(join(d, "decision.json"), JSON.stringify({ applies: "yes", rationale: "x" }));
    expect(readDecision(d).error).toContain("applies");
    writeFileSync(join(d, "decision.json"), JSON.stringify({ applies: false, rationale: " " }));
    expect(readDecision(d).error).toContain("rationale");
    writeFileSync(join(d, "decision.json"), JSON.stringify({ applies: false, rationale: " not about play " }));
    expect(readDecision(d).decision).toEqual({ applies: false, rationale: "not about play" });
  });

  it("the house-rule sink carries the decision, run id and gate result to the engine", () => {
    const sink = new HouseRuleSpacetimeSink(async () => {}, "01HR");
    const patch = sink.patch({
      run_id: "R1",
      status: "ready",
      backend: "droid",
      plan_md: "",
      diff: "",
      steps: [],
      results: { passed: true, tests: [], calls_changed: [], engine: "", summary: "" },
      decision: { applies: true, rationale: "r" },
      commit: "abc1234",
      workspace: "/w",
      sport: "table_tennis",
    } as unknown as DroidRun);
    expect(patch).toMatchObject({
      status: "ready",
      run_id: "R1",
      decision: { applies: true, rationale: "r", decided_by: "droid" },
      results: { passed: true },
      pack_path: "/w/sports/table_tennis/rules.yaml@abc1234",
    });
  });

  it("serialises reducer calls, collapses stale snapshots and never throws", async () => {
    const order: string[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const q = new Serial("t", () => order.push("logged"));
    void q.push(async () => {
      await gate;
      order.push("a");
    });
    await Promise.resolve(); // a is in flight now, waiting on the gate
    await Promise.resolve();
    void q.push(async () => void order.push("b"));
    void q.push(async () => void order.push("c")); // replaces b, still waiting
    void q.push(async () => {
      throw new Error("boom");
    }, false);
    const done = q.push(async () => void order.push("d"), false);
    release();
    await done;
    expect(order).toEqual(["a", "c", "logged", "d"]);
    const calls: unknown[] = [];
    const s = new DroidRunSpacetimeSink(async (r, p) => void calls.push([r, (p as DroidRun).status]));
    await s.update({ status: "running" } as DroidRun);
    expect(calls).toEqual([["update_droid_run", "running"]]);
  });

  it("only picks up interpreter requests the engine queued", () => {
    const base = {
      status: "queued",
      kind: "interpreter",
      attempt: 0,
      trigger: { source: "sport_module", requested_by: "engine" },
    } as unknown as DroidRun;
    expect(isRunRequest(base)).toBe(true);
    expect(isRunRequest({ ...base, trigger: { source: "user", requested_by: "engine" } })).toBe(true);
    expect(isRunRequest({ ...base, trigger: { source: "cli" } })).toBe(false); // a CLI run's own first snapshot
    expect(isRunRequest({ ...base, workspace: "/w" })).toBe(false);
    expect(isRunRequest({ ...base, status: "running" })).toBe(false);
    expect(isRunRequest({ ...base, kind: "house_rule" })).toBe(false);
  });
});

describe.skipIf(!existsSync(ENGINE_PY))("D-43 runs (real sandbox + real gate, scripted agent)", () => {
  it("interpreter: a pack missing the let fails the fixtures, the repair passes; the requested run id is kept", async () => {
    const sink = new Collect();
    const p = (dir: string) => join(dir, "sports/badminton/rules.yaml");
    const run = await runJob(
      {
        kind: "interpreter",
        sport: "badminton",
        samplesDir: "/nonexistent",
        runId: "01REQUESTEDBYENGINE0000000",
        triggerSource: "sport_module",
        gameId: "g_synth002",
        text: "no approved interpreter for badminton",
      },
      {
        config: config(),
        sink,
        agentFactory: scripted([
          (dir) => writeFileSync(p(dir), badmintonPack(false)),
          (dir) => writeFileSync(p(dir), badmintonPack(true)),
        ]),
      },
    );
    expect(run.status, run.error ?? "").toBe("ready");
    expect(run.run_id).toBe("01REQUESTEDBYENGINE0000000");
    expect(run.kind).toBe("interpreter");
    expect(run.trigger).toMatchObject({ source: "sport_module", requested_by: "engine" });
    expect(run.attempt).toBe(2);
    expect(run.results?.passed).toBe(true);
    expect(run.results?.tests.some((t) => t.name === "SYNTHETIC_rallies:call:4@17s" && t.pass)).toBe(true);
    const first = sink.runs.find((r) => r.results && !r.results.passed);
    expect(first?.results?.tests.find((t) => t.name === "SYNTHETIC_rallies:call:4@17s")?.pass).toBe(false);
    expect(run.diff).toContain("+  - id: net_let");
    expect(run.allowlist).toEqual(["sports/badminton/rules.yaml"]);
  });

  it("interpreter: regenerating table tennis adds the let and still passes the golden fixtures", async () => {
    const run = await runJob(
      { kind: "interpreter", sport: "table_tennis", samplesDir: TT_SAMPLES },
      {
        config: config(),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) => {
            const p = join(dir, "sports/table_tennis/rules.yaml");
            writeFileSync(p, readFileSync(p, "utf8").replace("rules:\n", LET_RULE));
          },
        ]),
      },
    );
    expect(run.status, run.error ?? "").toBe("ready");
    const names = run.results!.tests.map((t) => t.name);
    expect(names).toContain("rally_01:calls:winner");
    expect(names).toContain("SYNTHETIC_let_out_fault:call:2@5.3s");
  });

  it("house rule: the decision is required, rules stack on the engine's pack, and calls_changed comes from the session", async () => {
    const d = tmp();
    // the engine's snapshot: the pack in force already holds an earlier house rule, and this game's events
    const golden = readFileSync(join(REPO_ROOT, "sports/table_tennis/rules.yaml"), "utf8");
    writeFileSync(join(d, "base.rules.yaml"), golden.replace("points_to_win: 11", "points_to_win: 7"));
    const events = readFileSync(TT_FIX, "utf8")
      .trim()
      .split("\n")
      .map((l) => JSON.parse(l));
    writeFileSync(
      join(d, "session.json"),
      JSON.stringify({
        schema: "trophy.session.v1",
        game_id: "g_live0001",
        sport: "table_tennis",
        teams: [
          { team_id: "A", name: "Mu" },
          { team_id: "B", name: "Vedansh" },
        ],
        params: {},
        first_server: "A",
        rule_version: "01EARLIER",
        dead_after_point_s: 2,
        server_from_first_hit: false,
        events,
      }),
    );
    const sink = new Collect();
    const p = (dir: string) => join(dir, "sports/table_tennis/rules.yaml");
    const run = await runJob(
      {
        kind: "house_rule",
        sport: "table_tennis",
        text: "a serve that clips the net is a let",
        samplesDir: TT_SAMPLES,
        ruleVersion: "01HOUSE",
        basePack: join(d, "base.rules.yaml"),
        session: join(d, "session.json"),
      },
      {
        config: config(),
        sink,
        agentFactory: scripted([
          (dir) => {
            expect(readFileSync(p(dir), "utf8")).toContain("points_to_win: 7"); // stacked on the earlier rule
            writeFileSync(p(dir), readFileSync(p(dir), "utf8").replace("rules:\n", LET_RULE));
          }, // forgot decision.json
          (dir) =>
            writeFileSync(join(dir, "decision.json"), JSON.stringify({ applies: true, rationale: "ITTF 2.9.1.1 let" })),
        ]),
      },
    );
    expect(run.status, run.error ?? "").toBe("ready");
    expect(run.attempt).toBe(2);
    expect(run.steps.some((s) => s.kind === "repair" && s.text.includes("decision.json is missing"))).toBe(true);
    expect(run.decision).toEqual({ applies: true, rationale: "ITTF 2.9.1.1 let" });
    expect(run.trigger).toMatchObject({ source: "house_rule", rule_version: "01HOUSE" });
    const session = run.results!.calls_changed.filter((c) => !c.before.includes(":"));
    expect(session[0]).toMatchObject({ t_s: 5, after: "let", before: "point → A (B at fault)" });
    expect(run.results!.tests.find((t) => t.name === "session:calls_changed")?.after).toMatch(/\d+ play\(s\) change/);
    expect(run.diff).toContain("+  - id: serve_net_let");
    expect(run.diff).toContain("decision.json");
  });

  it("house rule: 'does not apply' needs no rule change; 'applies' without one is sent back", async () => {
    const no = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "players must wear hats", samplesDir: TT_SAMPLES },
      {
        config: config(),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) =>
            writeFileSync(join(dir, "decision.json"), JSON.stringify({ applies: false, rationale: "not about play" })),
        ]),
      },
    );
    expect(no.status, no.error ?? "").toBe("ready");
    expect(no.decision).toEqual({ applies: false, rationale: "not about play" });
    const yes = await runJob(
      { kind: "house_rule", sport: "table_tennis", text: "first to 5", samplesDir: TT_SAMPLES },
      {
        config: config({ maxAttempts: 2 }),
        sink: new Collect(),
        agentFactory: scripted([
          (dir) => writeFileSync(join(dir, "decision.json"), JSON.stringify({ applies: true, rationale: "x" })),
          (dir) => writeFileSync(join(dir, "decision.json"), JSON.stringify({ applies: true, rationale: "y" })),
        ]),
      },
    );
    expect(yes.status).toBe("failed");
    expect(yes.steps.some((s) => s.text.includes("rules.yaml is unchanged"))).toBe(true);
  });
});
