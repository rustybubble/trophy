/**
 * new_check (interfaces-v1 section 20): the referee's request_check. A scripted agent writes checks/ball_speed.py;
 * the real sandbox, the real jailed new-check-test gate and the real git audit run around it. SYNTHETIC tracks.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { Agent, AgentFactory } from "../src/agent.ts";
import type { CompilerConfig } from "../src/config.ts";
import { defaultEnginePython, REPO_ROOT } from "../src/config.ts";
import { runJob } from "../src/runner.ts";
import type { Job } from "../src/sandbox.ts";

const ENGINE_PY = defaultEnginePython();
const SAMPLES = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis_3d");
const HAVE = existsSync(ENGINE_PY) && existsSync(SAMPLES);
if (!HAVE)
  console.warn(`skipping new_check tests: no engine venv python at ${ENGINE_PY} (run \`uv sync\` in services/engine)`);

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

const SPEED = `"""Fastest ball speed in a window."""

from __future__ import annotations

import math

from trophy_engine.checks.api import Field, Track, merge_params, result

PARAMS = {"min_samples": 3}  # samples needed in the window


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    pts = [s for s in track if (t0 is None or s.t >= t0) and (t1 is None or s.t <= t1)]
    if len(pts) < p["min_samples"]:
        return result("ball_speed", "unknown", p=0.0, evidence={"samples": len(pts)}, calibrated=False)
    v = max(math.dist(a.xyz, b.xyz) / (b.t - a.t) for a, b in zip(pts, pts[1:]) if b.t > a.t)
    return result("ball_speed", "measured", p=1.0, evidence={"max_speed_m_s": round(v, 2)})
`;

function config(): CompilerConfig {
  const runsDir = mkdtempSync(join(tmpdir(), "trophy-nc-runs-"));
  dirs.push(runsDir);
  return {
    factoryApiKey: "test-only-not-a-key",
    droidExecPath: undefined,
    model: "fake",
    reasoningEffort: "low",
    timeoutMs: 90_000,
    maxAttempts: 2,
    enginePython: ENGINE_PY,
    runsDir,
    spacetimeUri: "",
    spacetimeModule: "trophy",
    spacetimeCompilerToken: "",
    port: 8200,
  };
}

function writes(files: Record<string, string>): AgentFactory {
  return async (ctx) => {
    const agent: Agent = {
      async turn(prompt) {
        expect(prompt).toContain("how fast was that rally");
        expect(prompt).toContain("checks/ball_speed.py");
        for (const [f, body] of Object.entries(files)) writeFileSync(join(ctx.sandboxDir, f), body);
        return { success: true, text: "## Result\nwrote it" };
      },
      async close() {},
    };
    return agent;
  };
}

function job(): Job {
  return {
    kind: "new_check",
    sport: "table_tennis",
    text: "how fast was that rally",
    samplesDir: SAMPLES,
    fieldPath: join(SAMPLES, "field.json"),
    newCheck: {
      name: "ball_speed",
      question: "how fast was that rally",
      hint: "ball_speed(rally) -> max speed in m/s",
      sessionTrack: join(SAMPLES, "game_01.track3d.jsonl"),
      sessionField: join(SAMPLES, "field.json"),
      query: { t0: 0.8, t1: 4.4 },
    },
  };
}

describe.skipIf(!HAVE)("new_check (real sandbox + real new-check-test gate, scripted agent)", () => {
  it("writes one new check, passes the gate and answers on the session track", async () => {
    const run = await runJob(job(), {
      config: config(),
      agentFactory: writes({ "checks/ball_speed.py": SPEED }),
      sink: { update() {} },
    });
    expect(run.status, run.error ?? "").toBe("ready");
    const answer = JSON.parse(readFileSync(join(run.workspace!, ".trophy/answer.json"), "utf8"));
    expect(answer.check).toBe("ball_speed");
    expect(answer.verdict).toBe("measured");
    expect(answer.evidence.max_speed_m_s).toBeGreaterThan(1);
    expect(answer.inputs).toEqual({ t0: 0.8, t1: 4.4 });
  }, 120_000);

  it("fails a run that edits an existing check, even when the gate would pass", async () => {
    const existing = readFileSync(join(REPO_ROOT, "sports/table_tennis/checks/contacts.py"), "utf8");
    const run = await runJob(job(), {
      config: config(),
      agentFactory: writes({ "checks/ball_speed.py": SPEED, "checks/contacts.py": `${existing}\n# touched\n` }),
      sink: { update() {} },
    });
    expect(run.status).toBe("failed");
  }, 180_000);
});
