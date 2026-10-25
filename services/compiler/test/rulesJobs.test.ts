import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { editableFiles, gateScript } from "../src/allowlist.ts";
import { REPO_ROOT } from "../src/config.ts";
import { createSandbox, emptyRulesList } from "../src/sandbox.ts";

const ENGINE_PY = join(REPO_ROOT, "services/engine/.venv/bin/python");

describe("correction / compile_rules jobs", () => {
  it("only rules.yaml is editable and replay_test is the gate", () => {
    for (const kind of ["correction", "compile_rules"] as const) {
      expect(editableFiles(kind, "table_tennis")).toEqual(["sports/table_tennis/rules.yaml"]);
      expect(gateScript(kind)).toBe("replay_test");
    }
  });

  it("emptyRulesList keeps everything before rules: and leaves an empty list", () => {
    const out = emptyRulesList("sport: x\nparams:\n  a: 1\nrules:\n  - id: one\n    when: x\n");
    expect(out).toBe("sport: x\nparams:\n  a: 1\nrules: []\n");
    expect(emptyRulesList("sport: x\n")).toBe("sport: x\nrules: []\n");
  });

  it.skipIf(!existsSync(ENGINE_PY))(
    "a correction sandbox carries the laws, the vocabulary and the recorded samples",
    () => {
      const dir = mkdtempSync(join(tmpdir(), "trophy-correction-"));
      const sb = createSandbox(
        {
          kind: "correction",
          sport: "table_tennis",
          text: "that span was one rally, won by B",
          samplesDir: join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis"),
          extraSamplesDirs: [join(REPO_ROOT, "evals/fixtures/recorded/table_tennis")],
        },
        dir,
        ENGINE_PY,
      );
      expect(sb.allowlist).toEqual(["sports/table_tennis/rules.yaml"]);
      expect(readFileSync(join(dir, "context/laws.md"), "utf8")).toContain("ittf:2.10");
      const vocab = readFileSync(join(dir, "context/events.md"), "utf8");
      expect(vocab).toContain("`rally.hit_since_last_bounce`");
      expect(vocab).toContain("`ev.side_p`");
      expect(existsSync(join(dir, "samples/g_6ghx0t5z_rally1_live.l2.jsonl"))).toBe(true);
      expect(existsSync(join(dir, "samples/rally_01.l1.jsonl"))).toBe(true);
      const task = readFileSync(join(dir, "TASK.md"), "utf8");
      expect(task).toContain("context/events.md");
      expect(task).toContain("one rally, won by B");
    },
  );

  it.skipIf(!existsSync(ENGINE_PY))("a compile_rules sandbox starts from an empty rules list", () => {
    const dir = mkdtempSync(join(tmpdir(), "trophy-compile-rules-"));
    createSandbox(
      {
        kind: "compile_rules",
        sport: "table_tennis",
        samplesDir: join(REPO_ROOT, "evals/fixtures/synthetic/table_tennis"),
        emptyRules: true,
      },
      dir,
      ENGINE_PY,
    );
    const pack = readFileSync(join(dir, "sports/table_tennis/rules.yaml"), "utf8");
    expect(pack).toMatch(/\nrules: \[\]\n$/);
    expect(pack).toContain("scoring:");
  });
});
