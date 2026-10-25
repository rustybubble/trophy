import { describe, expect, it } from "vitest";

import { editableFiles, gateScript, isAllowedCommand, isAllowedEdit, sandboxRelative } from "../src/allowlist.ts";

const SB = "/tmp/sb";

describe("allowlist", () => {
  it("scopes editable files per job kind", () => {
    expect(editableFiles("compile", "pickleball")).toEqual([
      "sports/pickleball/config.yaml",
      "sports/pickleball/events.py",
      "sports/pickleball/rules.yaml",
    ]);
    // D-43: a house rule also writes the Droid's decision; an interpreter only its rule pack
    expect(editableFiles("house_rule", "table_tennis")).toEqual(["sports/table_tennis/rules.yaml", "decision.json"]);
    expect(editableFiles("interpreter", "badminton")).toEqual(["sports/badminton/rules.yaml"]);
    expect(gateScript("interpreter")).toBe("replay_test");
    expect(editableFiles("retune", "table_tennis")).toEqual([
      "sports/table_tennis/config.yaml",
      "sports/table_tennis/events.py",
    ]);
  });

  it("lets a calibrate_checks job edit every copied check file and nothing else", () => {
    expect(
      editableFiles("calibrate_checks", "table_tennis", ["bounces.py", "phases.py", "library.json", "_x.py"]),
    ).toEqual(["checks/bounces.py", "checks/phases.py"]);
    expect(editableFiles("calibrate_checks", "table_tennis")).toEqual([]);
    expect(gateScript("calibrate_checks")).toBe("check_test");
    expect(gateScript("house_rule")).toBe("replay_test");
  });

  it("accepts absolute and relative paths inside the sandbox only", () => {
    const allowed = editableFiles("house_rule", "table_tennis");
    expect(isAllowedEdit(SB, `${SB}/sports/table_tennis/rules.yaml`, allowed)).toBe(true);
    expect(isAllowedEdit(SB, "sports/table_tennis/rules.yaml", allowed)).toBe(true);
    expect(isAllowedEdit(SB, "./sports/table_tennis/../table_tennis/rules.yaml", allowed)).toBe(true);
    expect(isAllowedEdit(SB, `${SB}/sports/table_tennis/events.py`, allowed)).toBe(false);
    expect(isAllowedEdit(SB, `${SB}/replay_test`, allowed)).toBe(false);
    expect(isAllowedEdit(SB, `${SB}/../other/sports/table_tennis/rules.yaml`, allowed)).toBe(false);
    expect(isAllowedEdit(SB, "/etc/passwd", allowed)).toBe(false);
    expect(sandboxRelative(SB, "../x")).toBeNull();
  });

  it("allows only the test gate as a command", () => {
    expect(isAllowedCommand("./replay_test")).toBe(true);
    expect(isAllowedCommand("./replay_test --quiet")).toBe(true);
    expect(isAllowedCommand("replay_test")).toBe(true);
    expect(isAllowedCommand("./replay_test && cat /etc/passwd")).toBe(false);
    expect(isAllowedCommand("./replay_test; rm -rf /")).toBe(false);
    expect(isAllowedCommand("./replay_test | tee x")).toBe(false);
    expect(isAllowedCommand("python -c 'print(1)'")).toBe(false);
    expect(isAllowedCommand("curl https://example.com")).toBe(false);
    expect(isAllowedCommand("./replay_test $(whoami)")).toBe(false);
  });

  it("refuses the bypasses found in review: a newline, redirections, extra arguments", () => {
    expect(isAllowedCommand("./replay_test --a\nrm -rf ..")).toBe(false);
    expect(isAllowedCommand("./replay_test\nrm -rf ..")).toBe(false);
    expect(isAllowedCommand("./replay_test --quiet\n")).toBe(false);
    expect(isAllowedCommand("./replay_test --out >../../x")).toBe(false);
    expect(isAllowedCommand("./replay_test --in <~/.ssh/id_rsa")).toBe(false);
    expect(isAllowedCommand("./replay_test\t--quiet")).toBe(false);
    expect(isAllowedCommand("./replay_test --module ../../etc")).toBe(false);
    expect(isAllowedCommand("./replay_test --json=/tmp/x")).toBe(false);
    expect(isAllowedCommand("./replay_test $HOME")).toBe(false);
    expect(isAllowedCommand("./replay_test  --quiet")).toBe(false);
    expect(isAllowedCommand("../replay_test")).toBe(false);
    expect(isAllowedCommand("cd /tmp/sb && ./replay_test", "/tmp/sb")).toBe(true);
    expect(isAllowedCommand('cd "/tmp/sb" && ./replay_test --quiet', "/tmp/sb/")).toBe(true);
    expect(isAllowedCommand("cd /tmp/other && ./replay_test", "/tmp/sb")).toBe(false);
    expect(isAllowedCommand("cd /tmp/sb && ./replay_test && rm -rf /", "/tmp/sb")).toBe(false);
  });

  it("accepts ./check_test as a gate, and only the job's own gate when told which", () => {
    expect(isAllowedCommand("./check_test")).toBe(true);
    expect(isAllowedCommand("./check_test --quiet")).toBe(true);
    expect(isAllowedCommand("cd /tmp/sb && ./check_test", "/tmp/sb")).toBe(true);
    expect(isAllowedCommand("./check_test; curl x")).toBe(false);
    expect(isAllowedCommand("./check_tests")).toBe(false);
    expect(isAllowedCommand("./check_test", undefined, ["check_test"])).toBe(true);
    expect(isAllowedCommand("./replay_test", undefined, ["check_test"])).toBe(false);
    expect(isAllowedCommand("./check_test", "/tmp/sb", ["replay_test"])).toBe(false);
  });
});
