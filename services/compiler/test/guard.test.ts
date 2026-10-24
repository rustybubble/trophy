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
afterAll(() => rmSync(sb, { recursive: true, force: true }));

function run(payload: object): { code: number | null; err: string } {
  const r = spawnSync("python3", [GUARD, sb], { input: JSON.stringify(payload), encoding: "utf8" });
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
  it("lets read-only tools through and fails closed without an allowlist", () => {
    expect(run({ tool_name: "Read", tool_input: { file_path: "/etc/passwd" } }).code).toBe(0);
    const r = spawnSync("python3", [GUARD, "/nonexistent"], {
      input: JSON.stringify({ tool_name: "Edit", tool_input: { file_path: "x" } }),
      encoding: "utf8",
    });
    expect(r.status).toBe(2);
  });
});
