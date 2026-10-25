import { describe, expect, it } from "vitest";
import type { Call, Moment, Observation, Rally } from "@trophy/state-client";
import {
  condensed,
  fmtStat,
  highlights,
  keywordSearch,
  matches,
  notchKind,
  playlistStep,
  spriteCell,
  stats,
} from "../src/lib/moments.ts";

const mom = (id: string, t: number, kind: Moment["kind"], score: number, extra: Partial<Moment> = {}): Moment => ({
  moment_id: id,
  game_id: "g_test0001",
  kind,
  t_game_s: t,
  t_start_s: t - 2,
  t_end_s: t,
  label: `${kind} ${id}`,
  score_after: "0–0",
  tags: [kind],
  highlight_score: score,
  reasons: [],
  is_best_play: false,
  thumb_t_s: t,
  ...extra,
});

describe("highlights", () => {
  it("keeps the top moments in game order and always ends on the Play of the game", () => {
    const ms = [
      mom("a", 10, "point", 0.9, { is_best_play: true }),
      mom("b", 5, "edge", 0.5),
      mom("c", 20, "point", 0.7),
    ];
    expect(highlights(ms).map((m) => m.moment_id)).toEqual(["b", "c", "a"]);
    expect(highlights(ms, 2).map((m) => m.moment_id)).toEqual(["c", "a"]);
  });
  it("leaves out house rules and zero scores", () => {
    expect(highlights([mom("h", 1, "house_rule", 0.5), mom("z", 2, "point", 0)])).toEqual([]);
  });
});

describe("condensed", () => {
  it("pads each closed rally and merges overlaps", () => {
    const r = (no: number, t0: number, t1: number | null): Rally => ({
      game_id: "g_test0001",
      rally_no: no,
      status: t1 == null ? "open" : "closed",
      t_start_s: t0,
      t_end_s: t1,
      winner_team_id: null,
      summary: null,
    });
    expect(condensed([r(2, 5, 6), r(1, 1, 4.6), r(3, 20, null)])).toEqual([{ t0: 0.5, t1: 7, label: "Rally 1" }]);
  });
  it("steps through a playlist", () => {
    const ranges = [
      { t0: 0, t1: 5, label: "1" },
      { t0: 10, t1: 12, label: "2" },
    ];
    expect(playlistStep(ranges, 0, 4)).toEqual({ index: 0 });
    expect(playlistStep(ranges, 0, 5)).toEqual({ index: 1, seek: 10 });
    expect(playlistStep(ranges, 1, 12)).toEqual({ index: -1 });
  });
});

describe("filters and search", () => {
  const ms = [
    mom("p", 4, "point", 0.3, { team_id: "B" }),
    mom("s", 7, "serve_fault", 0.4, {
      team_id: "B",
      label: "Serve fault A: toss 9 cm",
      tags: ["serve_fault", "toss_low"],
    }),
    mom("e", 12, "edge", 0.8, { team_id: "B", tags: ["edge", "challenge"], is_best_play: true }),
  ];
  it("filters by kind and tag", () => {
    expect(ms.filter((m) => matches(m, "serve_faults")).map((m) => m.moment_id)).toEqual(["s"]);
    expect(ms.filter((m) => matches(m, "challenges")).map((m) => m.moment_id)).toEqual(["e"]);
    expect(ms.filter((m) => matches(m, "points")).length).toBe(3);
  });
  it("finds moments by keyword, synonym and side", () => {
    expect(keywordSearch(ms, "every edge ball").map((m) => m.moment_id)).toEqual(["e"]);
    expect(keywordSearch(ms, "serve faults").map((m) => m.moment_id)).toEqual(["s"]);
    expect(keywordSearch(ms, "edge by side A")).toEqual([]);
    expect(keywordSearch(ms, "best play").map((m) => m.moment_id)).toEqual(["e"]);
  });
  it("draws points tall and faults short", () => {
    expect([notchKind(ms[0]!), notchKind(ms[1]!), notchKind(mom("b", 1, "bookmark", 0))]).toEqual([
      "tall",
      "short",
      "diamond",
    ]);
  });
});

describe("stats", () => {
  const call = (id: string, team: string, extra: Partial<Call> = {}): Call =>
    ({
      schema: "trophy.call.v1",
      id,
      game_id: "g_test0001",
      t_game_s: 1,
      rule_id: "rally_point",
      rule_version: "table_tennis@1",
      kind: "point",
      outcome: `point_${team}`,
      team_id: team,
      points: 1,
      p: 0.9,
      p_source: "geometry",
      tier: "AUTO",
      shown: "auto",
      text: "",
      speech: "",
      cue: { beep: "none", flash: "none" },
      event_ids: [],
      evidence: [],
      status: "final",
      created_at_ms: 0,
      ...extra,
    }) as Call;
  it("counts what was detected and says 'not detected' for the rest", () => {
    const s = stats(
      ["A", "B"],
      [
        call("1", "B"),
        call("2", "B", { rule_id: "serve_toss_height", outcome: "illegal_toss_height", kind: "violation" }),
      ],
      [],
      [],
    );
    expect(s.sides.B!.points).toBe(2);
    expect(s.sides.A!.serveFaults).toBe(1);
    expect(s.sides.B!.serveFaults).toBe(0);
    expect(fmtStat(s.sides.A!.edgesFor)).toBe("not detected");
    expect(fmtStat(s.longestRally)).toBe("not detected");
  });
  it("ignores overturned and voided calls", () => {
    const s = stats(["A"], [call("1", "A", { status: "overturned" })], [], [] as Observation[]);
    expect(s.sides.A!.points).toBeNull();
  });
});

describe("spriteCell", () => {
  const spec = { url_template: "sprite_{n}.jpg", cols: 10, rows: 10, every_s: 2, w: 160, h: 90 };
  it("finds the sheet and cell for a media time", () => {
    expect(spriteCell(spec, 0)).toEqual({ sheet: 0, x: 0, y: 0 });
    expect(spriteCell(spec, 25)).toEqual({ sheet: 0, x: 320, y: 90 });
    expect(spriteCell(spec, 201)).toEqual({ sheet: 1, x: 0, y: 0 });
  });
});
