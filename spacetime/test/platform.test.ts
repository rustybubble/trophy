import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("spacetimedb/server", () => {
  const col = () => {
    const c: any = {};
    for (const k of ["primaryKey", "index", "autoInc", "default", "optional"]) c[k] = () => c;
    return c;
  };
  return {
    SenderError: Error,
    t: { string: col, u32: col, u64: col, f64: col, i32: col, bool: col },
    table: () => ({}),
    schema: () => ({ init: (fn: unknown) => fn, reducer: (_: unknown, fn: unknown) => fn }),
  };
});
import * as reducers from "../src/index";
function table(key: string) {
  const rows = new Map<string, any>();
  const api: any = { insert: (r: any) => rows.set(r[key], r), iter: () => rows.values() };
  for (const k of [key, "game_id", "status", "sport"])
    api[k] = {
      find: (v: string) => rows.get(v),
      update: (r: any) => rows.set(r[key], r),
      delete: (v: string) => rows.delete(v),
      filter: (v: string) => [...rows.values()].filter((r) => r[k] === v),
    };
  return api;
}
let ctx: any;
function call(name: keyof typeof reducers, payload: unknown, role = "engine") {
  ctx.sender = { toHexString: () => role };
  return (reducers[name] as any)(ctx, { json: typeof payload === "string" ? payload : JSON.stringify(payload) });
}
const moment = (id = "m1", game_id = "g1") => ({
  moment_id: id,
  game_id,
  kind: "point",
  t_game_s: 2,
  t_start_s: 0,
  t_end_s: 3,
  label: "Point A",
  score_after: "1–0",
  tags: [],
  reasons: [],
  highlight_score: 0.5,
  is_best_play: false,
  thumb_t_s: 2,
});
const run = (status = "ready") => ({
  schema: "trophy.droid_run.v1",
  run_id: "r1",
  sport: "table_tennis",
  kind: "compile",
  trigger: { source: "cli" },
  status,
  backend: "droid",
  model: "test",
  attempt: 1,
  max_attempts: 3,
  plan_md: "",
  steps: [],
  diff: "",
  results: { passed: true, tests: [], calls_changed: [], engine: "test", summary: "ok" },
  commit: "abc",
  started_at_ms: 1,
  updated_at_ms: 2,
});
beforeEach(() => {
  ctx = { timestamp: { toMillis: () => 100 }, db: {} };
  for (const [t, k] of Object.entries({
    owner: "key",
    service: "identity_hex",
    moment: "moment_id",
    commentary: "commentary_key",
    droid_run: "run_id",
    sport_module: "module_key",
    ask: "ask_id",
  }))
    ctx.db[t] = table(k);
  for (const role of ["engine", "compiler", "vision"]) ctx.db.service.insert({ identity_hex: role, role });
});
describe("platform reducer boundaries", () => {
  it("rejects wrong and anonymous identities on every new reducer before parsing", () => {
    for (const name of [
      "upsert_moment",
      "set_best_play",
      "post_commentary",
      "set_droid_run_status",
      "upsert_sport_module",
    ] as const) {
      for (const role of ["compiler", "vision", "anonymous"])
        expect(() => call(name, "bad", role)).toThrow("unauthorized");
    }
    for (const role of ["engine", "vision", "anonymous"])
      expect(() => call("update_droid_run", "bad", role)).toThrow("unauthorized");
  });
  it("updates moments idempotently and keeps best play scoped to a game", () => {
    call("upsert_moment", moment());
    call("upsert_moment", { ...moment(), label: "Updated" });
    call("upsert_moment", moment("m2"));
    call("upsert_moment", { ...moment("other", "g2"), is_best_play: true });
    call("set_best_play", { game_id: "g1", moment_id: "m1", reasons: ["long rally"] });
    call("set_best_play", { game_id: "g1", moment_id: "m2", reasons: ["game point"] });
    expect(ctx.db.moment.moment_id.find("m1").is_best_play).toBe(false);
    expect(JSON.parse(ctx.db.moment.moment_id.find("m2").json).reasons).toEqual(["game point"]);
    expect(ctx.db.moment.moment_id.find("other").is_best_play).toBe(true);
    expect(() => call("set_best_play", { game_id: "g2", moment_id: "m1", reasons: [] })).toThrow("no such moment");
    expect(() => call("upsert_moment", moment("m1", "g2"))).toThrow("immutable");
  });
  it("rejects malformed moments and JSON", () => {
    for (const bad of ["no", "[]", "null"]) expect(() => call("upsert_moment", bad)).toThrow();
    for (const patch of [
      { highlight_score: 2 },
      { t_end_s: -1 },
      { tags: [1] },
      { is_best_play: "yes" },
      { label: "x".repeat(81) },
    ]) {
      expect(() => call("upsert_moment", { ...moment(), ...patch })).toThrow();
    }
  });
  it("retains both commentary voices and rejects cross-game or invalid rows", () => {
    call("upsert_moment", moment());
    const c = {
      moment_id: "m1",
      game_id: "g1",
      voice: "pbp",
      text: "Point A",
      facts: {},
      validated: true,
      source: "template",
      created_at_ms: 1,
    };
    call("post_commentary", c);
    call("post_commentary", { ...c, voice: "colour" });
    call("post_commentary", { ...c, text: "Updated" });
    expect([...ctx.db.commentary.iter()]).toHaveLength(2);
    expect(() => call("post_commentary", { ...c, game_id: "g2" })).toThrow();
    expect(() => call("post_commentary", { ...c, voice: "other" })).toThrow();
    expect(() => call("post_commentary", { ...c, validated: "true" })).toThrow();
  });
  it("compiler streams runs but cannot approve or mutate finalized runs", () => {
    call("update_droid_run", run("running"), "compiler");
    call("update_droid_run", run(), "compiler");
    expect(() => call("update_droid_run", run("approved"), "compiler")).toThrow();
    expect(() => call("update_droid_run", { ...run(), updated_at_ms: 0 }, "compiler")).toThrow("stale");
    expect(() => call("update_droid_run", { ...run(), sport: "tennis" }, "compiler")).toThrow("immutable");
    call("set_droid_run_status", { run_id: "r1", status: "approved" });
    call("set_droid_run_status", { run_id: "r1", status: "approved" });
    expect(() => call("update_droid_run", run(), "compiler")).toThrow("final");
    expect(() => call("set_droid_run_status", { run_id: "r1", status: "rejected" })).toThrow("final");
  });
  it.each([
    run("running"),
    { ...run(), results: null },
    { ...run(), results: { passed: false } },
    { ...run(), commit: null },
  ])("requires a passing ready run and pinned commit", (r) => {
    call("update_droid_run", r, "compiler");
    expect(() => call("set_droid_run_status", { run_id: "r1", status: "approved" })).toThrow();
  });
  it("publishes only approved modules and requires increasing versions", () => {
    const m = {
      sport: "table_tennis",
      version: 1,
      backend: "droid",
      run_id: "r1",
      commit: "abc",
      path: "local/module",
      approved_at_ms: 100,
    };
    expect(() => call("upsert_sport_module", m)).toThrow("approved");
    call("update_droid_run", run(), "compiler");
    call("set_droid_run_status", { run_id: "r1", status: "approved" });
    call("upsert_sport_module", m);
    call("upsert_sport_module", m);
    expect(() => call("upsert_sport_module", { ...m, commit: "mutable" })).toThrow();
    expect(() => call("upsert_sport_module", { ...m, path: "changed" })).toThrow("increase");
    call("upsert_sport_module", { ...m, version: 2 });
    call("upsert_sport_module", { ...m, game_id: "g1", backend: "handwritten" });
    expect([...ctx.db.sport_module.iter()]).toHaveLength(2);
  });
  it("fills the ask columns from the referee's fields and keeps older asks readable", () => {
    const ask = {
      ask_id: "a1",
      game_id: "g1",
      sport: "table_tennis",
      question: "Was that on the edge?",
      answer: "Edge, BETA.",
      citations: [],
      latency_ms: 900,
      created_at_ms: 5,
    };
    call("post_ask", { ...ask, speech: "Edge. Beta.", kind: "check", check: "edge", p: 0.71, calibrated: false });
    const row = ctx.db.ask.ask_id.find("a1");
    expect([row.speech, row.kind, row.check, row.p, row.calibrated]).toEqual([
      "Edge. Beta.",
      "check",
      "edge",
      0.71,
      false,
    ]);
    call("post_ask", { ...ask, ask_id: "a2" });
    const old = ctx.db.ask.ask_id.find("a2");
    expect([old.speech, old.kind, old.check, old.p, old.calibrated]).toEqual(["", "", "", undefined, undefined]);
    for (const patch of [{ p: 1.5 }, { p: "high" }, { calibrated: "yes" }, { kind: 3 }])
      expect(() => call("post_ask", { ...ask, ask_id: "a3", ...patch })).toThrow();
    expect(() => call("post_ask", ask, "vision")).toThrow("unauthorized");
  });
});
