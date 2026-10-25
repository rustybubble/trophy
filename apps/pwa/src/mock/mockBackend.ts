// `?mock=1`: the judging demo with no backend. Every row here is SYNTHETIC (hand-made for UI development, not
// measurements or real calls) and the UI shows a "Mock data" chip. The videos in public/mock/ are generated test
// patterns (a white dot over a drawn table), and the ball track below follows the same formula, so the overlay dot
// lines up with the picture.
import {
  MockState,
  type AiVote,
  type Call,
  type Camera,
  type Challenge,
  type DroidRun,
  type Feed,
  type HouseRule,
  type MockScript,
  type Observation,
  type Score,
  type TableName,
  type TableRows,
  type Viewer,
} from "@trophy/state-client";
import type { AskAnswer, LiveScenario, Scenario } from "../lib/api.ts";
import type { Backend } from "../lib/backend.ts";

export const MOCK_GAME = "g_mockdemo";
const LABEL = "SYNTHETIC mock data: no backend, nothing here is a real call";
const BASE = import.meta.env.BASE_URL;
const TEAMS = [
  { team_id: "A", name: "Mu", color: "#f97316" },
  { team_id: "B", name: "Vedansh", color: "#38bdf8" },
];
const nameOf = (t: string) => TEAMS.find((x) => x.team_id === t)!.name;
const other = (t: string) => (t === "A" ? "B" : "A");

const ANGLES: Record<string, { cam_id: string; file: string }> = {
  Side: { cam_id: "c_mockside", file: "side.mp4" },
  Diagonal: { cam_id: "c_mockdiag", file: "diagonal.mp4" },
};

export const MOCK_SCENARIOS: Scenario[] = [
  {
    id: "tt-two-angle",
    title: "Ping pong · 2 angles",
    sport: "table_tennis",
    source: "synthetic",
    credit: null,
    annotated: false,
    angles: [{ label: "Side" }, { label: "Diagonal" }],
  },
  {
    id: "pickleball-rec-doubles",
    title: "Pickleball · rec doubles",
    sport: "pickleball",
    source: "cc_by_online",
    credit: "Mock credit line (the mock plays a synthetic test video, not the CC BY clip)",
    annotated: true,
    angles: [{ label: "Side" }],
  },
];

/** The synthetic ball path, in source pixels of the 640×360 mock videos (mirrors the ffmpeg expressions). */
export function mockBallPx(label: string, t: number): [number, number] {
  const tri = 1 - Math.abs(1 - (((t % 2) + 2) % 2));
  const h = ((t % 1) + 1) % 1;
  if (label === "Diagonal") return [230 + 180 * tri, 250 - 40 * tri - 420 * h * (1 - h)];
  return [140 + 360 * tri, 232 - 560 * h * (1 - h)];
}

let seq = 0;
const id = (p: string) => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`.toUpperCase();

class DemoMockState extends MockState {
  inject<T extends TableName>(table: T, row: TableRows[T]): void {
    this.put(table, row);
  }
}

function initialScript(t0: number): MockScript {
  const at = (ms: number) => t0 + ms;
  const interpreter: DroidRun = {
    schema: "trophy.droid_run.v1",
    run_id: "MOCKRUNINTERP01",
    game_id: MOCK_GAME,
    sport: "pickleball",
    base_sport: "table_tennis",
    kind: "interpreter",
    trigger: { source: "session", text: "Scenario sport pickleball has no approved interpreter" },
    status: "approved",
    backend: "droid",
    model: "droid (mock)",
    attempt: 1,
    max_attempts: 3,
    plan_md:
      "## Plan\n1. Read `sports/pickleball/RULES.md` and the event vocabulary.\n2. Write `rules.yaml`: kitchen volley = fault, out = point to the other team.\n3. Gate on the labelled fixtures.",
    steps: [
      { t_ms: 400, kind: "plan", text: "Read RULES.md, config.yaml and table tennis's golden rules.yaml" },
      { t_ms: 9_000, kind: "edit", text: "Wrote sports/pickleball/rules.yaml (4 rules)", path: "rules.yaml" },
      { t_ms: 31_000, kind: "test", text: "replay_test: 5/5 labelled calls reproduced" },
    ],
    diff: "--- a/sports/pickleball/rules.yaml\n+++ b/sports/pickleball/rules.yaml\n@@ -0,0 +1,6 @@\n+rules:\n+  - id: kitchen_volley\n+    when: contact.zone == 'kitchen' && contact.volley\n+    outcome: fault\n+  - id: out\n+    when: bounce.side == 'out'",
    results: {
      passed: true,
      tests: [
        { name: "rec-doubles · 00:04 out", before: "", after: "point_B", pass: true },
        { name: "rec-doubles · 00:19 kitchen", before: "", after: "fault_A", pass: true },
        { name: "rec-doubles · 00:33 out", before: "", after: "point_A", pass: true },
      ],
      calls_changed: [],
      engine: "events+rules",
      summary: "5/5 labelled calls reproduced (synthetic)",
    },
    allowlist: ["sports/pickleball/rules.yaml"],
    blocked: [],
    started_at_ms: at(-120_000),
    updated_at_ms: at(-72_000),
    finished_at_ms: at(-72_000),
    duration_ms: 48_000,
  };
  return {
    schema: "trophy.mock_script.v1",
    synthetic: true,
    label: LABEL,
    sport: "table_tennis",
    game_id: MOCK_GAME,
    t0_ms: t0,
    steps: [
      {
        at_ms: 0,
        table: "game",
        row: {
          game_id: MOCK_GAME,
          sport: "table_tennis",
          pack_version: "table_tennis@1",
          status: "live",
          t0_ms: t0,
          period_no: 1,
          rally_no: 0,
          server_team_id: "A",
          teams: TEAMS,
          params: { points_to_win: 11, win_by: 2, synthetic: true, label: LABEL },
          created_at_ms: t0,
        },
      },
      ...(["A", "B"] as const).map((team_id) => ({
        at_ms: 0,
        table: "score" as const,
        row: { game_id: MOCK_GAME, team_id, points: 0, display: "0–0", updated_at_ms: t0 },
      })),
      { at_ms: 0, table: "droid_run", row: interpreter },
    ],
  };
}

/** The mock gateway + engine: answers ctl like the real services would, by writing synthetic rows. */
export class MockBackend implements Backend {
  readonly mock = true;
  readonly state: DemoMockState;
  private t0 = Date.now();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private gen: ReturnType<typeof setInterval> | undefined;
  private feeds: Feed[] = [];
  private calls = new Map<string, Call>();
  private score = { A: 0, B: 0 };
  private rules = new Map<string, { hr: HouseRule; run: DroidRun; apply?: ReturnType<typeof setTimeout> }>();

  constructor(private readonly meId: string) {
    this.state = new DemoMockState(initialScript(this.t0));
  }

  private put<T extends TableName>(table: T, row: TableRows[T]): void {
    this.state.inject(table, row);
  }
  private after(ms: number, f: () => void): ReturnType<typeof setTimeout> {
    const t = setTimeout(f, ms);
    this.timers.push(t);
    return t;
  }
  private tGame(ms = Date.now()): number {
    return (ms - this.t0) / 1000;
  }

  scenarios(): Promise<Scenario[]> {
    return Promise.resolve(MOCK_SCENARIOS);
  }

  goLive(scenarioId: string): Promise<LiveScenario> {
    this.stopTimers();
    const sc = MOCK_SCENARIOS.find((s) => s.id === scenarioId) ?? MOCK_SCENARIOS[0]!;
    const wall0 = Date.now() + 4000;
    const now = Date.now();
    this.feeds = sc.angles.map(({ label }) => ({
      cam_id: ANGLES[label]!.cam_id,
      game_id: MOCK_GAME,
      label,
      status: "scheduled",
      scenario_id: sc.id,
      video_url: `${BASE}mock/${ANGLES[label]!.file}`,
      offset_s: 0,
      duration_s: 38,
      wall0_ms: wall0,
      t_game0_s: this.tGame(wall0),
      source: sc.source,
      credit: sc.credit ?? null,
      annotated: sc.annotated,
      calibrated: !sc.annotated,
      updated_at_ms: now,
    }));
    this.feeds.forEach((f) => this.put("feed", f));
    this.after(wall0 - now, () => this.setFeeds("playing"));
    this.after(wall0 - now + 38_000, () => this.stopTimers("ended"));
    this.startGenerator(wall0);
    this.scriptCalls(wall0);
    return Promise.resolve({ live_id: id("LIVE"), wall0_ms: wall0, feeds: this.feeds as never });
  }

  stop(): Promise<unknown> {
    this.stopTimers("ended");
    return Promise.resolve({ ok: true });
  }

  private setFeeds(status: Feed["status"]): void {
    this.feeds = this.feeds.map((f) => ({ ...f, status, updated_at_ms: Date.now() }));
    this.feeds.forEach((f) => this.put("feed", f));
  }

  private stopTimers(feedStatus?: Feed["status"]): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    clearInterval(this.gen);
    this.gen = undefined;
    if (feedStatus && this.feeds.length) this.setFeeds(feedStatus);
  }

  /** 10 Hz ball samples per angle, camera health, a bounce per second, and another phone reporting its drift. */
  private startGenerator(wall0: number): void {
    let tick = 0;
    this.gen = setInterval(() => {
      const now = Date.now();
      const clip = (now - wall0) / 1000;
      tick++;
      for (const f of this.feeds) {
        const live = clip >= 0 && clip < f.duration_s;
        if (live) {
          this.put("track_sample", {
            cam_id: f.cam_id,
            game_id: MOCK_GAME,
            t_game_s: Math.round((f.t_game0_s + clip - f.offset_s) * 10) / 10,
            object: "ball",
            px: mockBallPx(f.label, Math.round(clip * 10) / 10),
            pos_m: null,
            conf: 0.9,
          });
        }
        if (tick % 10 === 0) {
          const cam: Camera = {
            cam_id: f.cam_id,
            game_id: MOCK_GAME,
            label: f.label,
            role: "cam",
            device: { ua: "stream_clips (mock)" },
            calibration: null,
            calib_trusted: !!f.calibrated,
            connected: true,
            fps_in: live ? 29.6 + Math.random() * 0.5 : 0,
            sync_err_ms: 0,
            last_seen_ms: now,
          };
          this.put("camera", cam);
        }
      }
      if (tick % 10 === 0 && clip >= 0) {
        const s = Math.floor(clip);
        const both = s % 4 !== 3;
        const end = s % 2 === 0 ? -1 : 1;
        const obs: Observation = {
          schema: "trophy.event.v1",
          id: id("OBS"),
          game_id: MOCK_GAME,
          t_game_s: Math.round((this.feeds[0]!.t_game0_s + s) * 100) / 100,
          sport: "table_tennis",
          type: "bounce",
          source: "synthetic",
          cams: both ? this.feeds.map((f) => f.cam_id) : [this.feeds[0]!.cam_id],
          conf: 0.95,
          side: end < 0 ? "A" : "B",
          pos_m: { x: end * (0.95 + 0.3 * Math.random()), y: (Math.random() - 0.5) * 1.2 },
          sigma_m: both ? 0.008 + Math.random() * 0.006 : 0.024 + Math.random() * 0.01,
        };
        this.put("observation", obs);
      }
      if (tick % 20 === 0) {
        const other: Viewer = {
          viewer_id: "c_mockpx01",
          game_id: MOCK_GAME,
          cam_id: this.feeds.at(-1)!.cam_id,
          name: "Pixel 9",
          connected: true,
          playing: clip >= 0,
          drift_ms: Math.round((Math.random() - 0.5) * 40),
          last_seen_ms: now,
        };
        this.put("viewer", other);
      }
    }, 100);
  }

  private setScore(team: "A" | "B", delta: number): void {
    this.score[team] += delta;
    const display = `${this.score.A}–${this.score.B}`;
    for (const t of ["A", "B"] as const) {
      const row: Score = {
        game_id: MOCK_GAME,
        team_id: t,
        points: this.score[t],
        display,
        updated_at_ms: Date.now(),
      };
      this.put("score", row);
    }
  }

  private postCall(c: Partial<Call> & Pick<Call, "outcome" | "kind" | "text" | "speech" | "tier" | "p">): Call {
    const now = Date.now();
    const t = this.tGame(now);
    const call: Call = {
      schema: "trophy.call.v1",
      id: id("CAL"),
      game_id: MOCK_GAME,
      t_game_s: Math.round(t * 100) / 100,
      rule_id: c.rule_id ?? c.outcome,
      rule_version: "table_tennis@1",
      p_source: "geometry",
      shown: c.tier === "AUTO" ? "auto" : "challengeable",
      cue: { beep: c.tier === "AUTO" ? "short" : "double", flash: c.team_id ?? "none" },
      event_ids: [],
      evidence: this.feeds.map((f) => ({ cam_id: f.cam_id, t0_s: Math.max(0, t - 3), t1_s: t + 0.5 })),
      status: "final",
      created_at_ms: now,
      source: "sensed",
      ...c,
    };
    this.calls.set(call.id, call);
    this.put("call", call);
    if (call.points && call.team_id) this.setScore(call.team_id as "A" | "B", call.points);
    return call;
  }

  private scriptCalls(wall0: number): void {
    const at = (clipS: number, f: () => void) => this.after(wall0 - Date.now() + clipS * 1000, f);
    at(6.2, () =>
      this.postCall({
        kind: "line_call",
        outcome: "point_A",
        team_id: "A",
        points: 1,
        text: "Out — point Mu",
        speech: "Out.",
        at_fault: { team_id: "B", name: "Vedansh" },
        tier: "AUTO",
        p: 0.97,
        rule_id: "rally_point",
      }),
    );
    at(13.1, () =>
      this.postCall({
        kind: "edge_call",
        outcome: "edge_good",
        team_id: "B",
        points: 1,
        text: "Edge ball — good",
        speech: "Edge ball, good.",
        at_fault: { team_id: "A", name: "Mu" },
        tier: "BETA",
        p: 0.71,
        rule_id: "edge_ball",
      }),
    );
    at(21.4, () =>
      this.postCall({
        kind: "violation",
        outcome: "illegal_toss_height",
        team_id: "A",
        points: 1,
        text: "Fault — toss too low",
        speech: "Fault, toss too low.",
        at_fault: { team_id: "B", name: "Vedansh" },
        tier: "BETA",
        p: 0.84,
        rule_id: "serve_toss_height",
      }),
    );
    at(30, () =>
      this.postCall({
        kind: "foul_flag",
        outcome: "net_touch",
        text: "Net touch? Players decide",
        speech: "Possible net touch. Players decide.",
        at_fault: null,
        tier: "PLAYERS",
        p: 0.55,
        rule_id: "net_touch",
        source: "annotated",
        p_source: "heuristic",
      }),
    );
  }

  // ------------------------------------------------------------------ ctl
  ctl(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const now = Date.now();
    switch (cmd) {
      case "viewer_status":
        this.put("viewer", {
          viewer_id: this.meId,
          game_id: MOCK_GAME,
          cam_id: String(args.cam_id),
          name: typeof args.name === "string" ? args.name : "This phone",
          connected: true,
          playing: !!args.playing,
          drift_ms: Number(args.drift_ms ?? 0),
          last_seen_ms: now,
        });
        break;
      case "challenge":
        this.challenge(String(args.call_id));
        break;
      case "submit_house_rule":
        this.houseRule(String(args.text), args.source === "voice" ? "voice" : "typed");
        break;
      case "reject_house_rule":
      case "revert_house_rule":
        this.endRule(String(args.rule_version), cmd === "reject_house_rule" ? "rejected" : "reverted");
        break;
    }
    return Promise.resolve({ req_id: id("REQ") });
  }

  ask(question: string): Promise<AskAnswer> {
    return Promise.resolve({
      answer: `[Mock] The referee would answer “${question}” from the rulebook here.`,
      citations: [
        {
          rule_id: "MOCK-1",
          title: "Synthetic placeholder clause",
          url: "https://example.invalid/mock",
          quote: "Placeholder text, not an official rule.",
        },
      ],
      latency_ms: 0,
      kind: "rule",
    });
  }

  feedSrc(feed: Feed): string {
    return feed.video_url;
  }
  clipSrc(): string | undefined {
    return undefined;
  }

  private challenge(callId: string): void {
    const call = this.calls.get(callId);
    if (!call) return;
    const now = Date.now();
    const ch: Challenge = {
      challenge_id: id("CHL"),
      game_id: MOCK_GAME,
      call_id: callId,
      by_cam_id: this.meId,
      status: "open",
      result: null,
      created_at_ms: now,
      resolved_at_ms: null,
    };
    this.put("challenge", ch);
    this.put("call", { ...call, status: "challenged" });
    // like the engine: an info call voices the challenge on every phone
    this.info(`Challenge: ${call.text}`, "Challenge. Let's look at the replay.", "challenge");
    const edge = call.outcome === "edge_good";
    const players = call.tier === "PLAYERS";
    const claude: AiVote = {
      call_id: callId,
      challenge_id: ch.challenge_id,
      game_id: MOCK_GAME,
      backend: "claude",
      model: "claude-opus-5-5 (mock)",
      choice: edge ? "SIDE_FAULT" : players ? "UNSURE" : call.outcome.toUpperCase(),
      probs: edge ? { SIDE_FAULT: 0.81, EDGE_GOOD: 0.19 } : players ? { YES: 0.52, NO: 0.48 } : { KEEP: 0.9, CHANGE: 0.1 },
      latency_ms: 1700,
      error: null,
      rationale: edge
        ? "Synthetic: the ball drops off the side face below the top edge in both angles."
        : players
          ? "Synthetic: the net is hidden in both angles; can't tell."
          : "Synthetic: both angles agree with the original call.",
      created_at_ms: now + 1700,
    };
    this.after(1700, () => this.put("ai_vote", { ...claude, created_at_ms: Date.now() }));
    this.after(3800, () => {
      const resolved = { status: "resolved" as const, resolved_at_ms: Date.now(), decided_by: "auto" as const };
      if (edge) {
        const explanation =
          "Overturned: the ball hit the side face, not the edge. Claude: drops off the side face in both angles. Confidence 19% (uncalibrated). Point Mu. (synthetic)";
        this.put("call", { ...call, status: "overturned", explanation });
        this.put("challenge", { ...ch, ...resolved, result: "overturned", p_original: 0.19, explanation });
        this.setScore("B", -1);
        this.postCall({
          kind: "edge_call",
          outcome: "side_fault",
          team_id: "A",
          points: 1,
          text: "Overturned: side fault — point Mu",
          speech: explanation,
          at_fault: null,
          tier: "AUTO",
          p: 1,
          p_source: "decide:ensemble",
          supersedes: call.id,
          explanation,
          rule_id: "edge_ball",
          cue: { beep: "double", flash: "none" },
        });
      } else if (players) {
        const explanation =
          "Too close to call: possible net touch. The net is hidden in both angles. Confidence 52% (uncalibrated). Players decide. (synthetic)";
        this.put("call", { ...call, status: "players_decide", explanation });
        this.put("challenge", { ...ch, ...resolved, result: "players_decide", p_original: 0.52, explanation });
        this.info(`Players decide: ${call.text}`, explanation, "challenge_verdict");
      } else {
        const explanation = `The call stands: ${call.text}. Both angles agree. Confidence 90% (uncalibrated). (synthetic)`;
        this.put("call", { ...call, status: "upheld", explanation });
        this.put("challenge", { ...ch, ...resolved, result: "upheld", p_original: 0.9, explanation });
        this.info(`Upheld: ${call.text}`, explanation, "challenge_verdict");
      }
    });
  }

  private info(text: string, speech: string, rule_id: string): void {
    this.postCall({
      kind: "info",
      outcome: rule_id,
      text: text.slice(0, 80),
      speech,
      tier: "AUTO",
      p: 1,
      rule_id,
      at_fault: null,
      cue: { beep: "short", flash: "none" },
      p_source: "manual",
      source: "manual",
      evidence: [],
    });
  }

  private houseRule(text: string, source: "typed" | "voice"): void {
    const t0 = Date.now();
    const rv = id("HR");
    let hr: HouseRule = {
      rule_version: rv,
      game_id: MOCK_GAME,
      sport: "table_tennis",
      text,
      source,
      status: "pending",
      backend: "droid",
      plan_md: "",
      steps: [],
      diff: "",
      results: null,
      pack_path: null,
      error: null,
      created_at_ms: t0,
      updated_at_ms: t0,
      decision: null,
    };
    let run: DroidRun = {
      schema: "trophy.droid_run.v1",
      run_id: id("RUN"),
      game_id: MOCK_GAME,
      sport: "table_tennis",
      kind: "house_rule",
      trigger: { source: "house_rule", rule_version: rv, text },
      status: "queued",
      backend: "droid",
      model: "droid (mock)",
      attempt: 0,
      max_attempts: 3,
      plan_md: "",
      steps: [],
      diff: "",
      results: null,
      allowlist: ["rules/table_tennis.yaml"],
      blocked: [],
      started_at_ms: t0,
      updated_at_ms: t0,
    };
    const entry: { hr: HouseRule; run: DroidRun; apply?: ReturnType<typeof setTimeout> } = { hr, run };
    this.rules.set(rv, entry);
    const push = (h: Partial<HouseRule>, r: Partial<DroidRun>) => {
      const now = Date.now();
      hr = { ...hr, ...h, updated_at_ms: now };
      run = { ...run, ...r, updated_at_ms: now };
      entry.hr = hr;
      entry.run = run;
      this.put("house_rule", hr);
      this.put("droid_run", run);
    };
    push({}, {});
    const step = (kind: DroidRun["steps"][number]["kind"], s: string, path?: string) => {
      const st = { t_ms: Date.now() - t0, kind, text: s, ...(path ? { path } : {}) };
      return { steps: [...run.steps, st] };
    };
    const plan = `## Plan\n1. Read \`rules/table_tennis.yaml\` and the request: “${text}”.\n2. Change **scoring.params** only.\n3. Run \`replay_test\` against this session's plays.`;
    const diff = `--- a/rules/table_tennis.yaml\n+++ b/rules/table_tennis.yaml\n@@ -12,6 +12,7 @@ scoring:\n   params:\n-    points_to_win: 11\n-    win_by: 2\n+    # house rule: ${text}\n+    points_to_win: 7\n+    win_by: 1\n   serve_rotation: 2`;
    this.after(700, () => push({ status: "compiling", plan_md: plan }, { status: "running", attempt: 1, plan_md: plan, ...step("plan", "Plan: edit scoring.params, then gate") }));
    this.after(1600, () => {
      const s = step("tool", "Read rules/table_tennis.yaml", "rules/table_tennis.yaml");
      push({ steps: s.steps }, s);
    });
    this.after(2700, () => {
      const s = step("edit", "points_to_win 11 → 7, win_by 2 → 1", "rules/table_tennis.yaml");
      push({ steps: s.steps, diff }, { ...s, diff });
    });
    this.after(3500, () => {
      const s = step("blocked", "Refused: curl example.invalid (no network in the sandbox)");
      push({ steps: s.steps }, { ...s, blocked: ["curl example.invalid"] });
    });
    this.after(4400, () => {
      const s = step("test", "replay_test: 6 tests over this session's 4 rallies");
      push({ steps: s.steps }, s);
    });
    this.after(5600, () => {
      const tests = [
        { name: "schema valid", before: "", after: "ok", pass: true },
        { name: "golden fixtures unchanged", before: "12/12", after: "12/12", pass: true },
        { name: "game ends at 7-x (win by 1)", before: "11", after: "7", pass: true },
        { name: "session re-judged", before: "4 rallies", after: "4 rallies", pass: true },
      ];
      const calls_changed = [{ rally_no: 3, before: "Game continues", after: "Game point Mu" }];
      const decision = {
        applies: true,
        rationale: "A scoring change for this match; the gate passed and only the game-end threshold moved.",
        decided_by: "droid" as const,
        rejudged_rallies: 4,
        calls_changed: 1,
        decided_at_ms: Date.now(),
      };
      const s = step("message", "Gate passed. Decision: apply.");
      push(
        { status: "ready", steps: s.steps, results: { tests, calls_changed }, decision },
        {
          ...s,
          status: "ready",
          results: { passed: true, tests, calls_changed, engine: "events+rules", summary: "4/4 pass (synthetic)" },
          finished_at_ms: Date.now(),
          duration_ms: Date.now() - t0,
          gate_ms: [820],
        },
      );
      entry.apply = this.after(3500, () => {
        push({ status: "applied" }, { status: "approved" });
        this.postCall({
          kind: "info",
          outcome: "house_rule_applied",
          text: `House rule applied · 1 call changed`,
          speech: `House rule applied: ${text}. 1 call changed.`,
          tier: "AUTO",
          p: 1,
          rule_id: "house_rule",
          rule_version: rv,
          cue: { beep: "long", flash: "none" },
          p_source: "manual",
          source: "manual",
        });
      });
    });
  }

  private endRule(rv: string, status: "rejected" | "reverted"): void {
    const e = this.rules.get(rv);
    if (!e) return;
    if (e.apply) clearTimeout(e.apply);
    const now = Date.now();
    e.hr = { ...e.hr, status, updated_at_ms: now };
    e.run = { ...e.run, status: status === "rejected" ? "rejected" : e.run.status, updated_at_ms: now };
    this.put("house_rule", e.hr);
    this.put("droid_run", e.run);
    if (status === "reverted") {
      this.postCall({
        kind: "info",
        outcome: "house_rule_reverted",
        text: "House rule undone",
        speech: "House rule undone. The previous rules are back.",
        tier: "AUTO",
        p: 1,
        rule_id: "house_rule",
        cue: { beep: "long", flash: "none" },
        p_source: "manual",
        source: "manual",
      });
    }
  }

  dispose(): void {
    this.stopTimers();
    this.state.disconnect();
  }

  /** for other modules that want the team names */
  static teamName = nameOf;
  static otherTeam = other;
}
