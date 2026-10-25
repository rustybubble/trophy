import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { REPO_ROOT } from "../src/config.ts";
import { changedFiles, createSandbox, sandboxDiff } from "../src/sandbox.ts";

const SAMPLES = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis");
const SAMPLES_3D = join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis_3d");
const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

function tmp(): string {
  const d = join(mkdtempSync(join(tmpdir(), "trophy-sb-")), "ws");
  dirs.push(d);
  return d;
}

describe("sandbox", () => {
  it("contains only the module, schemas, samples, the gate and the brief (house rule)", () => {
    const sb = createSandbox(
      { kind: "house_rule", sport: "table_tennis", text: "first to 7", samplesDir: SAMPLES },
      tmp(),
      "/usr/bin/false",
    );
    const top = readdirSync(sb.dir).sort();
    expect(top).toEqual([
      ".factory",
      ".git",
      ".gitignore",
      ".trophy",
      "TASK.md",
      "fixtures", // the SYNTHETIC annotated table-tennis plays (shown, not gated, for a house rule)
      "reference", // reference/base: the pack in force, the gate's baseline (D-43)
      "replay_test",
      "samples",
      "schema",
      "sports",
    ]);
    const hooks = JSON.parse(readFileSync(join(sb.dir, ".factory/hooks.json"), "utf8"));
    expect(hooks.PreToolUse[0].matcher).toContain("Edit");
    expect(hooks.PreToolUse[0].hooks[0].command).toContain("guard.py");
    expect(() => writeFileSync(join(sb.dir, ".factory/hooks.json"), "{}")).toThrow();
    expect(JSON.parse(readFileSync(join(sb.dir, ".trophy/allowlist.json"), "utf8")).files).toEqual(sb.allowlist);
    expect(readdirSync(join(sb.dir, "sports/table_tennis")).sort()).toEqual(["config.yaml", "events.py", "rules.yaml"]);
    expect(readdirSync(join(sb.dir, "samples")).filter((f) => f.endsWith(".l1.jsonl")).length).toBeGreaterThan(0);
    expect(sb.allowlist).toEqual(["sports/table_tennis/rules.yaml", "decision.json"]);
    const task = readFileSync(join(sb.dir, "TASK.md"), "utf8");
    expect(task).toContain("first to 7");
    expect(task).toContain("`sports/table_tennis/rules.yaml`");
    expect(task).not.toContain("{{");
    expect(existsSync(join(sb.dir, ".env"))).toBe(false);
    expect(changedFiles(sb)).toEqual([]);
    // the gate pins its own arguments and never forwards the caller's ("$@" was a bypass)
    const gate = readFileSync(join(sb.dir, "replay_test"), "utf8");
    // "$@" appears only after `set --` has replaced the caller's arguments with the pinned ones
    expect(gate.indexOf("set -- ")).toBeGreaterThan(-1);
    expect(gate.indexOf('"$@"')).toBeGreaterThan(gate.indexOf("set -- "));
    expect(gate).not.toContain("$*");
  });

  it("gives a compile job the reference module read-only and a seeded target", () => {
    const sb = createSandbox(
      {
        kind: "compile",
        sport: "pickleball",
        baseSport: "table_tennis",
        scene: join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis/scene.json"),
        samplesDir: join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis"),
      },
      tmp(),
      "/usr/bin/false",
    );
    expect(readdirSync(join(sb.dir, "reference/table_tennis")).sort()).toEqual([
      "config.yaml",
      "events.py",
      "rules.yaml",
    ]);
    expect(readdirSync(join(sb.dir, "sports/pickleball")).sort()).toEqual(["config.yaml", "events.py", "rules.yaml"]); // seeded copy
    expect(existsSync(join(sb.dir, "scene/scene.json"))).toBe(true);
    expect(sb.allowlist).toContain("sports/pickleball/events.py");
  });

  it("gives a calibrate_checks job the library to edit, a read-only reference, the field, the rules and check_test", () => {
    const sb = createSandbox(
      { kind: "calibrate_checks", sport: "table_tennis", samplesDir: SAMPLES_3D, sessionId: "s_test" },
      tmp(),
      "/usr/bin/false",
    );
    expect(sb.gate).toBe("check_test");
    expect(readdirSync(sb.dir).sort()).toEqual([
      ".factory",
      ".git",
      ".gitignore",
      ".trophy",
      "TASK.md",
      "check_test",
      "checks",
      "reference",
      "rules",
      "samples",
      "schema",
    ]);
    const checks = readdirSync(join(sb.dir, "checks")).sort();
    expect(checks).toContain("library.json");
    expect(checks.filter((f) => f.endsWith(".py"))).toEqual([
      "bounces.py",
      "contacts.py",
      "in_out.py",
      "net_touch.py",
      "phases.py",
      "rally_summary.py",
      "serve_toss.py",
    ]);
    expect(readdirSync(join(sb.dir, "reference/checks")).sort()).toEqual(checks);
    expect(sb.allowlist).toEqual(checks.filter((f) => f.endsWith(".py")).map((f) => `checks/${f}`));
    expect(sb.allowlist).not.toContain("checks/library.json");
    expect(readdirSync(join(sb.dir, "rules/table_tennis")).sort()).toEqual(["config.yaml", "events.py", "rules.yaml"]);
    expect(readdirSync(join(sb.dir, "schema"))).toEqual(["track3d.schema.json"]);
    const samples = readdirSync(join(sb.dir, "samples")).sort();
    expect(samples).toContain("field.json");
    expect(samples.filter((f) => f.endsWith(".track3d.jsonl")).length).toBeGreaterThan(0);
    expect(samples.filter((f) => f.endsWith(".labels3d.json")).length).toBe(
      samples.filter((f) => f.endsWith(".track3d.jsonl")).length,
    );
    const gate = readFileSync(join(sb.dir, "check_test"), "utf8");
    expect(gate).toContain("trophy_engine.check_test.cli");
    expect(gate).toContain("--baseline reference/checks");
    expect(gate).toContain('--rules "rules/table_tennis"');
    expect(JSON.parse(readFileSync(join(sb.dir, ".trophy/allowlist.json"), "utf8"))).toEqual({
      files: sb.allowlist,
      commands: ["./check_test"],
    });
    const task = readFileSync(join(sb.dir, "TASK.md"), "utf8");
    expect(task).toContain("./check_test");
    expect(task).not.toContain("replay_test");
    expect(task).toContain("`checks/phases.py`");
    expect(task).toContain("samples/game_01.labels3d.json");
    expect(task).not.toContain("{{");
    expect(changedFiles(sb)).toEqual([]);
  });

  it("reports every changed path, inside or outside the allowlist, and a unified diff", () => {
    const sb = createSandbox(
      { kind: "house_rule", sport: "table_tennis", text: "x", samplesDir: SAMPLES },
      tmp(),
      "/usr/bin/false",
    );
    writeFileSync(
      join(sb.dir, "sports/table_tennis/rules.yaml"),
      readFileSync(join(sb.dir, "sports/table_tennis/rules.yaml"), "utf8") + "# edited\n",
    );
    writeFileSync(join(sb.dir, "schema/evil.json"), "{}");
    expect(changedFiles(sb).sort()).toEqual(["schema/evil.json", "sports/table_tennis/rules.yaml"]);
    const diff = sandboxDiff(sb);
    expect(diff).toContain("+# edited");
    expect(diff).toContain("schema/evil.json");
  });
});

describe("gate jail (review blocker 2)", () => {
  it("runs the gate's Python with a clean env, no network and no writes outside the sandbox", () => {
    const base = mkdtempSync(join(tmpdir(), "trophy-jail-"));
    dirs.push(base);
    const outside = join(base, "outside.txt");
    // a stand-in for the engine interpreter: it ignores its arguments and probes what the jail allows
    const fake = join(base, "fakepy");
    writeFileSync(
      fake,
      [
        "#!/bin/sh",
        "exec /usr/bin/python3 - <<'PY'",
        "import json, os, socket",
        "r = {'env': sorted(os.environ)}",
        "try:",
        "    socket.create_connection(('1.1.1.1', 53), timeout=3).close(); r['net'] = 'open'",
        "except OSError as e:",
        "    r['net'] = 'blocked'",
        "try:",
        `    open(${JSON.stringify(outside)}, 'w').write('x'); r['outside'] = 'written'`,
        "except OSError:",
        "    r['outside'] = 'blocked'",
        "open('.trophy/probe.json', 'w').write(json.dumps(r))",
        "PY",
        "",
      ].join("\n"),
      { mode: 0o755 },
    );
    const sb = createSandbox(
      { kind: "house_rule", sport: "table_tennis", text: "x", samplesDir: SAMPLES },
      join(base, "ws"),
      fake,
    );
    execFileSync(join(sb.dir, "replay_test"), [], { cwd: sb.dir, env: { ...process.env, TROPHY_SECRET: "sk-test" } });
    const isolation = readFileSync(join(sb.dir, ".trophy/isolation"), "utf8").trim();
    const probe = JSON.parse(readFileSync(join(sb.dir, ".trophy/probe.json"), "utf8")) as Record<string, unknown>;
    expect(probe.env).not.toContain("TROPHY_SECRET"); // env -i on every host
    expect((probe.env as string[]).filter((k) => /KEY|TOKEN|SECRET|PASS/i.test(k))).toEqual([]);
    if (isolation === "none") {
      console.warn("gate jail: no network isolation on this host (CI without user namespaces); env check only");
      return;
    }
    expect(probe.net).toBe("blocked");
    if (isolation === "sandbox-exec") {
      expect(probe.outside).toBe("blocked");
      expect(existsSync(outside)).toBe(false);
    }
  });
});
