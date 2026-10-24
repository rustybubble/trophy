// Builds fixtures/table-tennis-demo.json and fixtures/basketball-demo.json: LABELLED SYNTHETIC MockScripts
// for UI work before the real pipeline exists. Nothing here is a measurement. Rerun after contract changes:
//   node --experimental-strip-types packages/state-client/scripts/build-fixtures.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type {
  AiVote,
  Call,
  Camera,
  Event,
  Game,
  HouseRule,
  MockScript,
  MockStep,
  Rally,
  Score,
  TrackSample,
} from "../src/types.ts";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures");
const T0 = 1_792_000_000_000; // arbitrary fixed epoch; MockState shifts it to connect time
const LABEL = "SYNTHETIC demo script: hand-made rows for UI development, not measurements or real calls";

let n = 0;
const ulid = (tag: string) => `01JDEM${tag.toUpperCase().padEnd(4, "0").slice(0, 4)}${String(++n).padStart(16, "0")}`;

class Script {
  steps: MockStep[] = [];
  readonly game_id: string;
  readonly sport: string;
  constructor(game_id: string, sport: string) {
    this.game_id = game_id;
    this.sport = sport;
  }
  add<T extends MockStep["table"]>(at_ms: number, table: T, row: Extract<MockStep, { table: T }>["row"]) {
    this.steps.push({ at_ms, table, row } as MockStep);
  }
  build(): MockScript {
    return {
      schema: "trophy.mock_script.v1",
      synthetic: true,
      label: LABEL,
      sport: this.sport,
      game_id: this.game_id,
      t0_ms: T0,
      steps: this.steps,
    };
  }
}

// ---------------------------------------------------------------- table tennis
function tableTennis(): MockScript {
  const G = "g_demtt001";
  const CAM = "c_demca1";
  const s = new Script(G, "table_tennis");
  const ms = (t_s: number) => Math.round(t_s * 1000);
  const game: Game = {
    game_id: G,
    sport: "table_tennis",
    pack_version: "table_tennis@1",
    status: "lobby",
    t0_ms: T0,
    period_no: 1,
    rally_no: 0,
    server_team_id: "A",
    teams: [
      { team_id: "A", name: "Team A", color: "#e4572e" },
      { team_id: "B", name: "Team B", color: "#2e86ab" },
    ],
    params: { points_to_win: 11, win_by: 2 },
    created_at_ms: T0,
  };
  const camera: Camera = {
    cam_id: CAM,
    game_id: G,
    label: "Side cam (net line)",
    role: "cam",
    device: { ua: "synthetic", w: 1280, h: 720 },
    calibration: null,
    calib_trusted: true,
    connected: true,
    fps_in: 29.8,
    sync_err_ms: 4.1,
    last_seen_ms: T0 + 500,
  };
  s.add(0, "game", game);
  s.add(200, "camera", camera);
  s.add(500, "game", { ...game, status: "live" });
  const score = (a: number, b: number, at: number) => {
    const sc = (team_id: string, points: number): Score => ({
      game_id: G,
      team_id,
      points,
      display: `${a}–${b}`,
      updated_at_ms: T0 + at,
    });
    s.add(at, "score", sc("A", a));
    s.add(at, "score", sc("B", b));
  };
  score(0, 0, 500);

  const ev = (t: number, type: Event["type"], payload: Record<string, unknown>, extra: Partial<Event> = {}): Event => {
    const e: Event = {
      schema: "trophy.event.v1",
      id: ulid("obs"),
      game_id: G,
      t_game_s: t,
      sport: "table_tennis",
      type,
      source: "synthetic",
      cams: [CAM],
      conf: 0.95,
      payload,
      ...extra,
    };
    s.add(ms(t) + 80, "observation", e);
    return e;
  };
  const track = (t0: number, t1: number, path: (u: number) => [number, number, number]) => {
    for (let t = t0; t <= t1 + 1e-9; t += 0.1) {
      const u = (t - t0) / Math.max(t1 - t0, 1e-6);
      const row: TrackSample = {
        cam_id: CAM,
        t_game_s: Math.round(t * 10) / 10,
        game_id: G,
        object: "ball",
        pos_m: path(u).map((v) => Math.round(v * 1000) / 1000) as [number, number, number],
        px: null,
        conf: 0.9,
      };
      s.add(ms(t) + 60, "track_sample", row);
    }
  };
  const toss = (t: number, height: number, angleDeg: number, side: "A" | "B") => {
    const x = side === "A" ? -1.5 : 1.5;
    const a = (angleDeg * Math.PI) / 180;
    return ev(t + 0.6, "serve_toss", {
      server_side: side,
      release: { t_s: t, pos_m: { x, y: 0.3, z: 0.0 } },
      apex: { t_s: t + 0.3, pos_m: { x, y: 0.3, z: height } },
      contact: { t_s: t + 0.6, pos_m: { x: x + Math.sin(a) * height * 0.5, y: 0.3, z: height * 0.4 } },
      height_m: height,
      sigma_height_m: 0.012,
      rise_angle_rad: 0.05,
      fall_angle_rad: a,
      angle_from_vertical_rad: a,
      sigma_angle_rad: 0.06,
      palm_still_s: 0.6,
      observable_plane: "xz",
    });
  };
  const bounce = (t: number, side: "A" | "B", x: number, y: number, edge?: Record<string, number>) =>
    ev(
      t,
      "bounce",
      {
        surface: "table",
        side,
        d_lines_m: { [side === "A" ? "end_A" : "end_B"]: 1.37 - Math.abs(x), side_left: 0.7625 - y },
        p_in: edge ? edge.top_edge! + edge.surface! : 0.99,
        edge: edge ?? null,
        timing: "audio",
      },
      { side, pos_m: { x, y, z: 0 }, sigma_m: 0.018 },
    );
  const call = (at: number, c: Partial<Call> & Pick<Call, "outcome" | "kind" | "p" | "tier" | "shown" | "text" | "speech">, ids: string[], t: number): Call => {
    const row: Call = {
      schema: "trophy.call.v1",
      id: ulid("cal"),
      game_id: G,
      t_game_s: t,
      rule_id: "rally_point",
      rule_version: "table_tennis@1",
      p_source: "geometry",
      cue: { beep: "short", flash: c.team_id ?? "none" },
      event_ids: ids,
      evidence: [{ cam_id: CAM, t0_s: t - 3, t1_s: t + 0.5 }],
      status: "final",
      created_at_ms: T0 + at,
      ...c,
    };
    s.add(at, "call", row);
    return row;
  };
  const rally = (no: number, t_start: number, t_end: number | null, winner: string | null) => {
    const r: Rally = {
      game_id: G,
      rally_no: no,
      status: t_end === null ? "open" : "closed",
      t_start_s: t_start,
      t_end_s: t_end,
      winner_team_id: winner,
      summary: null,
    };
    s.add(ms(t_end ?? t_start), "rally", r);
  };

  // Rally 1 (t 1.0 - 4.6): legal serve, B wins on a long ball.
  rally(1, 1.0, null, null);
  const t1 = toss(1.0, 0.22, 12, "A");
  track(1.6, 4.4, (u) => [-1.4 + 3.2 * u, 0.3 - 0.2 * u, 0.25 * Math.abs(Math.sin(u * Math.PI * 3))]);
  const b1 = bounce(2.0, "A", -0.9, 0.3);
  const b2 = bounce(2.5, "B", 0.8, 0.1);
  const b3 = bounce(3.4, "A", -1.0, -0.2);
  const d1 = ev(4.4, "ball_dead", { reason: "floor", last_side: "B" });
  rally(1, 1.0, 4.6, "B");
  call(4800, { outcome: "point_B", kind: "point", team_id: "B", points: 1, p: 0.97, tier: "AUTO", shown: "auto", text: "Out — point B (97%)", speech: "Out. Point, B.", why: "Return landed 0.31 m past end B." }, [t1.id, b1.id, b2.id, b3.id, d1.id], 4.6);
  score(0, 1, 4800);

  // Rally 2 (t 7.0 - 7.8): toss too low -> illegal serve, AUTO.
  rally(2, 7.0, null, null);
  const t2 = toss(7.0, 0.09, 8, "A");
  rally(2, 7.0, 7.8, "B");
  call(8000, { rule_id: "serve_toss_height", kind: "violation", outcome: "illegal_toss_height", team_id: "B", points: 1, p: 0.96, tier: "AUTO", shown: "auto", text: "Fault: toss too low (9 cm < 15.2 cm) — point B", speech: "Fault. Toss too low. Point, B.", overlay: { serve_toss_event_id: t2.id }, why: "Toss rose 0.09 m; the rule needs more than 0.1524 m." }, [t2.id], 7.6);
  score(0, 2, 8000);

  // Rally 3 (t 10.0 - 13.2): edge ball, BETA 71%; speculative AI votes; challenged; upheld.
  rally(3, 10.0, null, null);
  const t3 = toss(10.0, 0.24, 6, "B");
  track(10.6, 13.0, (u) => [1.4 - 2.75 * u, 0.1 + 0.6 * u, 0.22 * Math.abs(Math.sin(u * Math.PI * 2))]);
  const b4 = bounce(11.2, "B", 0.7, 0.2);
  const b5 = bounce(12.4, "A", -1.362, 0.66, { top_edge: 0.71, side_face: 0.2, surface: 0.09 });
  const d3 = ev(13.0, "ball_dead", { reason: "floor", last_side: "A" });
  rally(3, 10.0, 13.2, "A");
  const edge = call(13400, { rule_id: "edge_ball", kind: "edge_call", outcome: "edge_good", team_id: "B", points: 1, p: 0.71, tier: "BETA", shown: "challengeable", text: "Edge ball — good. Point B (71%)", speech: "Edge ball. Good. Point, B.", cue: { beep: "double", flash: "B" }, overlay: { bounce_marks: [{ pos_m: [-1.362, 0.66], sigma_m: 0.018, t_game_s: 12.4 }], lines: ["end_A"] }, why: "Bounce 8 mm inside end A, within the edge band." }, [t3.id, b4.id, b5.id, d3.id], 13.2);
  score(0, 3, 13400);
  const vote = (at: number, v: Omit<AiVote, "call_id" | "game_id" | "created_at_ms">) =>
    s.add(at, "ai_vote", { call_id: edge.id, game_id: G, created_at_ms: T0 + at, ...v });
  vote(15200, { backend: "claude", model: "claude-opus-5-5", challenge_id: null, choice: "EDGE_GOOD", probs: { EDGE_GOOD: 0.78, SIDE_FAULT: 0.22 }, latency_ms: 1800, rationale: "Ball deflects upward off the top edge (synthetic)." });
  vote(15800, { backend: "gemini", model: "gemini (synthetic)", challenge_id: null, choice: "EDGE_GOOD", probs: { EDGE_GOOD: 0.66, SIDE_FAULT: 0.34 }, latency_ms: 2400, rationale: "Trajectory after contact suggests top edge (synthetic)." });
  const CH = ulid("chl");
  s.add(16000, "challenge", { challenge_id: CH, game_id: G, call_id: edge.id, by_cam_id: CAM, status: "open", result: null, created_at_ms: T0 + 16000, resolved_at_ms: null });
  s.add(16000, "call", { ...edge, status: "challenged" });
  vote(16500, { backend: "bitdeer", model: "Qwen/Qwen3.5-397B-A17B", challenge_id: CH, choice: "SIDE_FAULT", probs: { EDGE_GOOD: 0.45, SIDE_FAULT: 0.55 }, latency_ms: 3100, rationale: "Blurred crop; slight lean to side face (synthetic)." });
  s.add(20000, "challenge", { challenge_id: CH, game_id: G, call_id: edge.id, by_cam_id: CAM, status: "resolved", result: "upheld", created_at_ms: T0 + 16000, resolved_at_ms: T0 + 20000 });
  s.add(20000, "call", { ...edge, status: "upheld", suggested: "EDGE_GOOD" });

  // House rule via the Droid (synthetic progress).
  const RV = ulid("hr");
  const hr: HouseRule = {
    rule_version: RV,
    game_id: G,
    sport: "table_tennis",
    text: "First to 7, win by 1",
    source: "typed",
    status: "pending",
    backend: "droid",
    plan_md: "",
    steps: [],
    diff: "",
    results: null,
    pack_path: null,
    error: null,
    created_at_ms: T0 + 22000,
    updated_at_ms: T0 + 22000,
  };
  s.add(22000, "house_rule", hr);
  const plan = "1. Set scoring.params.points_to_win to 7.\n2. Set scoring.params.win_by to 1.\n3. Run replay_test.";
  s.add(23000, "house_rule", { ...hr, status: "compiling", plan_md: plan, steps: [{ t_ms: 1000, kind: "plan", text: "Read rules/table_tennis.yaml and the request" }], updated_at_ms: T0 + 23000 });
  const steps: HouseRule["steps"] = [
    { t_ms: 1000, kind: "plan", text: "Read rules/table_tennis.yaml and the request" },
    { t_ms: 2600, kind: "edit", text: "scoring.params: points_to_win 11 → 7, win_by 2 → 1" },
    { t_ms: 4100, kind: "test", text: "replay_test: 3 rallies, schema ok" },
  ];
  const ready: HouseRule = {
    ...hr,
    status: "ready",
    plan_md: plan,
    steps,
    diff: "--- a/rules/table_tennis.yaml\n+++ b/rules/table_tennis.yaml\n@@ scoring.params @@\n-    points_to_win: 11\n-    win_by: 2\n+    points_to_win: 7\n+    win_by: 1\n",
    results: {
      tests: [
        { name: "schema", pass: true },
        { name: "replay rallies 1-3", before: "0–3", after: "0–3", pass: true },
      ],
      calls_changed: [],
    },
    pack_path: `rulepacks/house/${G}/table_tennis.v2.yaml`,
    updated_at_ms: T0 + 26000,
  };
  s.add(26000, "house_rule", ready);
  s.add(29000, "house_rule", { ...ready, status: "approved", updated_at_ms: T0 + 29000 });
  call(29200, { rule_id: "house_rule", rule_version: RV, kind: "info", outcome: "house_rule_added", p: 1, p_source: "manual", tier: "AUTO", shown: "auto", text: "House rule added: first to 7, win by 1", speech: "House rule added. First to seven, win by one.", cue: { beep: "long", flash: "none" } }, [], 29.2);

  // Ask the ref (synthetic answer; the citation is a placeholder, not a real clause).
  s.add(32000, "ask", {
    ask_id: ulid("ask"),
    game_id: G,
    sport: "table_tennis",
    question: "Can the serve clip the net?",
    answer: "[Synthetic] A serve that touches the net assembly and then lands correctly is a let and is replayed.",
    citations: [{ rule_id: "SYNTH-1", title: "Synthetic placeholder clause", url: "https://example.invalid/synthetic", quote: "Synthetic placeholder text, not an official rule." }],
    moss_ms: 42,
    latency_ms: 2100,
    created_at_ms: T0 + 32000,
  });
  return s.build();
}

// ---------------------------------------------------------------- basketball (SHOULD)
function basketball(): MockScript {
  const G = "g_dembb001";
  const CAM = "c_demca2";
  const s = new Script(G, "basketball");
  const game: Game = {
    game_id: G,
    sport: "basketball",
    pack_version: "basketball@1",
    status: "live",
    t0_ms: T0,
    period_no: 1,
    rally_no: 0,
    server_team_id: null,
    teams: [
      { team_id: "home", name: "Home", color: "#f2a541" },
      { team_id: "away", name: "Away", color: "#5c4d7d" },
    ],
    params: { points_to_win: 21 },
    created_at_ms: T0,
  };
  s.add(0, "game", game);
  s.add(100, "camera", { cam_id: CAM, game_id: G, label: "Baseline cam", role: "cam", calib_trusted: true, connected: true, fps_in: 30, sync_err_ms: 5, last_seen_ms: T0 + 100 });
  const sc = (home: number, away: number, at: number) => {
    for (const [team_id, points] of [["home", home], ["away", away]] as const)
      s.add(at, "score", { game_id: G, team_id, points, display: `${home}–${away}`, updated_at_ms: T0 + at });
  };
  sc(0, 0, 100);
  const shot = (t: number, behind: number, made: boolean | null, team: string, pts: number, p: number, home: number, away: number) => {
    const e: Event = { schema: "trophy.event.v1", id: ulid("obs"), game_id: G, t_game_s: t, sport: "basketball", type: "shot", source: "synthetic", cams: [CAM], conf: 0.9, team_id: team, payload: { shooter_track_id: `${CAM}:3`, team_id: team, release_pos_m: [6.9, 2.1], behind_arc_p: behind, made, made_p: 0.9, attempt_points_hint: pts as 2 | 3 } };
    s.add(t * 1000 + 50, "observation", e);
    const at = t * 1000 + 400;
    s.add(at, "call", { schema: "trophy.call.v1", id: ulid("cal"), game_id: G, t_game_s: t, rule_id: "basket", rule_version: "basketball@1", kind: "basket", outcome: `made_${pts}`, team_id: team, points: pts, p, p_source: "geometry", tier: p >= 0.9 ? "AUTO" : "BETA", shown: p >= 0.9 ? "auto" : "challengeable", text: `${pts === 3 ? "Three" : "Two"} — ${team} (${Math.round(p * 100)}%)`, speech: `${pts === 3 ? "Three" : "Two"}. ${team}.`, cue: { beep: "short", flash: team }, event_ids: [e.id], evidence: [{ cam_id: CAM, t0_s: t - 2, t1_s: t + 1.5 }], status: "final", created_at_ms: T0 + at });
    sc(home, away, at);
  };
  shot(3, 0.04, true, "home", 2, 0.95, 2, 0);
  shot(9, 0.97, true, "away", 3, 0.93, 2, 3);
  shot(15, 0.62, true, "home", 3, 0.62, 5, 3);
  return s.build();
}

for (const [name, script] of [
  ["table-tennis-demo.json", tableTennis()],
  ["basketball-demo.json", basketball()],
] as const) {
  writeFileSync(join(out, name), JSON.stringify(script, null, 1) + "\n");
  console.log(`wrote ${name}: ${script.steps.length} steps`);
}
