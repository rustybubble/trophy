import { describe, expect, it } from "vitest";

import { decide } from "../src/droidAgent.ts";

const ctx = { sandboxDir: "/tmp/sb", allowlist: ["sports/table_tennis/rules.yaml"], model: "x" };

describe("permission decisions", () => {
  it("proceeds for allowlisted edits and the gate, cancels everything else", () => {
    const blocked: string[] = [];
    const b = (w: string) => blocked.push(w);
    expect(decide(ctx, [{ details: { type: "edit", filePath: "/tmp/sb/sports/table_tennis/rules.yaml" } }], b)).toBe(
      true,
    );
    expect(decide(ctx, [{ details: { type: "create", filePath: "/tmp/sb/sports/table_tennis/rules.yaml" } }], b)).toBe(
      true,
    );
    expect(decide(ctx, [{ details: { type: "exec", fullCommand: "./replay_test" } }], b)).toBe(true);
    expect(decide(ctx, [{ details: { type: "edit", filePath: "/tmp/sb/sports/table_tennis/events.py" } }], b)).toBe(
      false,
    );
    expect(decide(ctx, [{ details: { type: "exec", fullCommand: "curl http://x" } }], b)).toBe(false);
    expect(decide(ctx, [{ details: { type: "mcp_tool" } }], b)).toBe(false);
    expect(
      decide(
        ctx,
        [
          { details: { type: "edit", filePath: "/tmp/sb/sports/table_tennis/rules.yaml" } },
          { details: { type: "exec", fullCommand: "rm -rf /" } },
        ],
        b,
      ),
    ).toBe(false);
    expect(decide(ctx, [], b)).toBe(false);
    expect(blocked).toEqual([
      "edit outside the allowlist: /tmp/sb/sports/table_tennis/events.py",
      "command refused: curl http://x",
      "tool refused: mcp_tool",
      "command refused: rm -rf /",
    ]);
  });
});
