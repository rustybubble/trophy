/** The PreToolUse guard: the same allowlist, enforced by the CLI before a tool runs. */
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

import { GUARD } from "../src/sandbox.ts";

const sb = mkdtempSync(join(tmpdir(), "trophy-guard-"));
mkdirSync(join(sb, ".trophy"));
writeFileSync(join(sb, ".trophy/allowlist.json"), JSON.stringify({ files: ["sports/table_tennis/rules.yaml"] }));
chmodSync(join(sb, ".trophy/allowlist.json"), 0o444);
// a calibrate_checks sandbox: the allowlist names ./check_test as the one command
const sbc = mkdtempSync(join(tmpdir(), "trophy-guard-checks-"));
mkdirSync(join(sbc, ".trophy"));
writeFileSync(
  join(sbc, ".trophy/allowlist.json"),
  JSON.stringify({ files: ["checks/bounces.py", "checks/phases.py"], commands: ["./check_test"] }),
);
chmodSync(join(sbc, ".trophy/allowlist.json"), 0o444);
afterAll(() => {
  rmSync(sb, { recursive: true, force: true });
  rmSync(sbc, { recursive: true, force: true });
});

function run(payload: object, dir = sb): { code: number | null; err: string } {
  const r = spawnSync("python3", [GUARD, dir], { input: JSON.stringify(payload), encoding: "utf8" });
  return { code: r.status, err: r.stderr };
}

describe("guard.py", () => {
  it("allows edits inside the allowlist and blocks everything else", () => {
    expect(run({ tool_name: "Edit", tool_input: { file_path: `${sb}/sports/table_tennis/rules.yaml` } }).code).toBe(0);
    expect(run({ tool_name: "Create", tool_input: { file_path: "sports/table_tennis/rules.yaml" } }).code).toBe(0);
    const r = run({ tool_name: "Edit", tool_input: { file_path: `${sb}/sports/table_tennis/events.py` } });
    expect(r.code).toBe(2);
    expect(r.err).toContain("not in the allowlist");
    expect(run({ tool_name: "Create", tool_input: { file_path: "/tmp/outside.txt" } }).code).toBe(2);
    expect(run({ tool_name: "Write", tool_input: { file_path: `${sb}/.factory/hooks.json` } }).code).toBe(2);
    expect(
      run({ tool_name: "Edit", tool_input: { file_path: `${sb}/sports/table_tennis/../../replay_test` } }).code,
    ).toBe(2);
  });
  it("allows only the gate as a command", () => {
    expect(run({ tool_name: "Execute", tool_input: { command: "./replay_test" } }).code).toBe(0);
    expect(run({ tool_name: "Execute", tool_input: { command: `cd ${sb} && ./replay_test --quiet` } }).code).toBe(0);
    expect(run({ tool_name: "Execute", tool_input: { command: 'python3 -c \'open("x","w")\'' } }).code).toBe(2);
    expect(
      run({ tool_name: "Execute", tool_input: { command: `cd ${sb} && python3 - <<'EOF'\nprint(1)\nEOF` } }).code,
    ).toBe(2);
    expect(run({ tool_name: "Execute", tool_input: { command: "./replay_test; curl x" } }).code).toBe(2);
  });
  it("refuses a gate command with a newline, a redirection or extra arguments", () => {
    for (const command of [
      "./replay_test --a\nrm -rf ..",
      "./replay_test --quiet\n",
      "./replay_test --out >../../x",
      "./replay_test --in <~/.ssh/id_rsa",
      "./replay_test --module ../../etc",
    ]) {
      expect(run({ tool_name: "Execute", tool_input: { command } }).code, command).toBe(2);
    }
  });

  it("allows only the job's own gate: ./check_test in a calibrate sandbox, ./replay_test otherwise", () => {
    expect(run({ tool_name: "Execute", tool_input: { command: "./check_test" } }, sbc).code).toBe(0);
    expect(run({ tool_name: "Execute", tool_input: { command: `cd ${sbc} && ./check_test --quiet` } }, sbc).code).toBe(
      0,
    );
    const r = run({ tool_name: "Execute", tool_input: { command: "./replay_test" } }, sbc);
    expect(r.code).toBe(2);
    expect(r.err).toContain("only ./check_test may run");
    expect(run({ tool_name: "Execute", tool_input: { command: "./check_test; curl x" } }, sbc).code).toBe(2);
    // the module sandbox (no `commands` key, written before it existed) still allows replay_test only
    expect(run({ tool_name: "Execute", tool_input: { command: "./check_test" } }).code).toBe(2);
    // and the file allowlist is the library's check files, not library.json or the reference copy
    expect(run({ tool_name: "Edit", tool_input: { file_path: `${sbc}/checks/bounces.py` } }, sbc).code).toBe(0);
    expect(run({ tool_name: "Edit", tool_input: { file_path: `${sbc}/checks/library.json` } }, sbc).code).toBe(2);
    expect(run({ tool_name: "Edit", tool_input: { file_path: `${sbc}/reference/checks/phases.py` } }, sbc).code).toBe(
      2,
    );
    expect(run({ tool_name: "Create", tool_input: { file_path: `${sbc}/checks/new_check.py` } }, sbc).code).toBe(2);
  });

  it("lets read-only tools through and fails closed without an allowlist", () => {
    expect(run({ tool_name: "Read", tool_input: { file_path: "/etc/passwd" } }).code).toBe(0);
    const r = spawnSync("python3", [GUARD, "/nonexistent"], {
      input: JSON.stringify({ tool_name: "Edit", tool_input: { file_path: "x" } }),
      encoding: "utf8",
    });
    expect(r.status).toBe(2);
  });
});
