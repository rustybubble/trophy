import { describe, expect, it } from "vitest";
import type { Call, Challenge, Feed, TrackSample, Viewer } from "@trophy/state-client";
import {
  bannerCall,
  challengeTarget,
  diffLineKind,
  explanationFor,
  mdToText,
  pickAngle,
  replayWindows,
  shouldAnnounce,
  SpeechGate,
  spokenLine,
  verdictOf,
} from "../src/lib/demo.ts";
import { clipToGame, correctionFor, gameToClip, phaseAt, serverNow, targetClipTime } from "../src/lib/sync.ts";
import { TrackBuffer } from "../src/lib/useTrophy.ts";

const feed = (cam_id: string, label: string, extra: Partial<Feed> = {}): Feed => ({
  cam_id,
  game_id: "g",
  label,
  status: "playing",
  scenario_id: "s",
  video_url: `/api/scenarios/s/media/${label}.mp4`,
  offset_s: 2,
  duration_s: 30,
  wall0_ms: 10_000,
  t_game0_s: 100,
  source: "team_recording",
  updated_at_ms: 0,
  ...extra,
});

const viewer = (viewer_id: string, cam_id: string, last_seen_ms = 1000): Viewer => ({
  viewer_id,
  game_id: "g",
  cam_id,
  connected: true,
  drift_ms: 0,
  last_seen_ms,
});

const call = (id: string, extra: Partial<Call> = {}): Call => ({
  schema: "trophy.call.v1",
  id,
  game_id: "g",
  t_game_s: 50,
  rule_id: "r",
  rule_version: "v",
  kind: "point",
  outcome: "point_A",
  p: 0.9,
  p_source: "geometry",
  tier: "AUTO",
  shown: "auto",
  text: "Out — point A",
  speech: "Out.",
  cue: { beep: "short", flash: "none" },
  event_ids: [],
  evidence: [],
  status: "final",
  created_at_ms: 0,
  ...extra,
});

describe("feed sync", () => {
  const f = feed("c1", "Side");
  it("maps server time to clip time and game time", () => {
    expect(targetClipTime(f, 10_000)).toBe(2);
    expect(targetClipTime(f, 11_500)).toBe(3.5);
    expect(clipToGame(f, 3.5)).toBe(101.5);
    expect(gameToClip(f, 101.5)).toBe(3.5);
  });
  it("counts down, plays, then ends", () => {
    expect(phaseAt(f, 7_100)).toEqual({ kind: "countdown", seconds: 3 });
    expect(phaseAt(f, 9_999)).toEqual({ kind: "countdown", seconds: 1 });
    expect(phaseAt(f, 10_000)).toEqual({ kind: "playing", t: 2 });
    expect(phaseAt(f, 40_000)).toEqual({ kind: "ended" });
  });
  it("seeks past 120 ms and nudges the rate (0.97-1.03) below that", () => {
    expect(correctionFor(121)).toEqual({ kind: "seek" });
    expect(correctionFor(-500)).toEqual({ kind: "seek" });
    expect(correctionFor(NaN)).toEqual({ kind: "seek" });
    expect(correctionFor(10)).toEqual({ kind: "rate", rate: 1 });
    expect(correctionFor(120)).toEqual({ kind: "rate", rate: 0.97 });
    expect(correctionFor(-120)).toEqual({ kind: "rate", rate: 1.03 });
    const r = correctionFor(60);
    expect(r.kind === "rate" && r.rate).toBeCloseTo(0.985);
  });
  it("adds the ctl clock offset (server - phone)", () => {
    expect(serverNow(25, 1000)).toBe(1025);
    expect(serverNow(null, 1000)).toBe(1000);
  });
});

describe("pickAngle", () => {
  const feeds = [feed("c2", "Side"), feed("c1", "Diagonal")];
  it("takes the first angle (by label) nobody shows yet", () => {
    expect(pickAngle(feeds, [], "me", undefined, 2000)).toBe("c1");
    expect(pickAngle(feeds, [viewer("p1", "c1")], "me", undefined, 2000)).toBe("c2");
  });
  it("ignores this phone's own row and stale or disconnected phones", () => {
    expect(pickAngle(feeds, [viewer("me", "c1")], "me", undefined, 2000)).toBe("c1");
    expect(pickAngle(feeds, [viewer("p1", "c1", 0)], "me", undefined, 60_000)).toBe("c1");
    expect(pickAngle(feeds, [{ ...viewer("p1", "c1"), connected: false }], "me", undefined, 2000)).toBe("c1");
  });
  it("keeps the current angle, and falls back to the first when every angle is taken", () => {
    expect(pickAngle(feeds, [viewer("p1", "c2")], "me", "c2", 2000)).toBe("c2");
    expect(pickAngle(feeds, [viewer("p1", "c1"), viewer("p2", "c2")], "me", undefined, 2000)).toBe("c1");
    expect(pickAngle([], [], "me", "c1", 0)).toBeUndefined();
  });
});

describe("spoken calls", () => {
  it("appends who is at fault when the line lacks the name", () => {
    expect(spokenLine({ speech: "Out.", text: "", at_fault: { team_id: "B", name: "Mu" } })).toBe("Out. Mu.");
    expect(spokenLine({ speech: "Fault, toss too low", text: "", at_fault: { team_id: "A", name: "Vedansh" } })).toBe(
      "Fault, toss too low. Vedansh.",
    );
    expect(spokenLine({ speech: "Out. Mu's fault.", text: "", at_fault: { team_id: "B", name: "Mu" } })).toBe(
      "Out. Mu's fault.",
    );
    expect(spokenLine({ speech: "Let.", text: "", at_fault: null })).toBe("Let.");
  });
  it("drops a line spoken moments ago", () => {
    const g = new SpeechGate(5000);
    expect(g.allow("Challenge. Let's look at the replay.", 0)).toBe(true);
    expect(g.allow("challenge, let's look at the replay", 1000)).toBe(false);
    expect(g.allow("Challenge. Let's look at the replay.", 7000)).toBe(true);
    expect(g.allow("  ", 0)).toBe(false);
  });
  it("announces engine lines and challenge replacements, not house-rule re-judging", () => {
    expect(shouldAnnounce(call("a"), new Set())).toBe(true);
    expect(shouldAnnounce(call("b", { supersedes: "a" }), new Set(["a"]))).toBe(true);
    expect(shouldAnnounce(call("b", { supersedes: "a" }), new Set())).toBe(false);
  });
});

describe("challenges", () => {
  const ch = (extra: Partial<Challenge>): Challenge => ({
    challenge_id: "ch",
    game_id: "g",
    call_id: "a",
    by_cam_id: "me",
    status: "resolved",
    created_at_ms: 0,
    ...extra,
  });
  it("reads the verdict", () => {
    expect(verdictOf(ch({ status: "open" }))).toBe("reviewing");
    expect(verdictOf(ch({ result: "upheld" }))).toBe("upheld");
    expect(verdictOf(ch({ result: "overturned" }))).toBe("overturned");
    expect(verdictOf(ch({ result: "players_decide" }))).toBe("players");
    expect(verdictOf(ch({ result: null }))).toBe("players");
  });
  it("finds the explanation on the challenge, the replacement or the original call", () => {
    const calls = [call("a", { explanation: "orig" }), call("b", { supersedes: "a", explanation: "rep" })];
    expect(explanationFor(ch({ explanation: "row" }), calls).text).toBe("row");
    expect(explanationFor(ch({}), calls)).toEqual({ text: "rep", replacement: calls[1] });
    expect(explanationFor(ch({}), [calls[0]!]).text).toBe("orig");
  });
  it("targets the newest decision of any tier, skipping info, voided and overturned calls", () => {
    const calls = [
      call("old", { created_at_ms: 1, tier: "PLAYERS" }),
      call("over", { created_at_ms: 2, status: "overturned" }),
      call("info", { created_at_ms: 3, kind: "info" }),
    ];
    expect(challengeTarget(calls)?.id).toBe("old");
    expect(bannerCall(calls)?.id).toBe("over");
    expect(challengeTarget([])).toBeUndefined();
  });
  it("builds a replay window per angle", () => {
    const c = call("a", { t_game_s: 2, evidence: [{ cam_id: "c1", t0_s: 10, t1_s: 14 }] });
    expect(replayWindows(c, ["c1", "c2"])).toEqual([
      { cam_id: "c1", t0_s: 10, t1_s: 14 },
      { cam_id: "c2", t0_s: 10, t1_s: 14 },
    ]);
    expect(replayWindows(call("b", { t_game_s: 2 }), ["c1"])).toEqual([{ cam_id: "c1", t0_s: 0, t1_s: 5 }]);
    const long = call("c", { evidence: [{ cam_id: "c1", t0_s: 0, t1_s: 50 }] });
    expect(replayWindows(long, ["c1"])).toEqual([{ cam_id: "c1", t0_s: 20, t1_s: 50 }]);
  });
});

describe("Droid rendering", () => {
  it("turns the plan into plain text", () => {
    expect(mdToText("## Plan\n1. Read `rules.yaml`.\n- **Edit** [params](x)\n\n\n\nDone")).toBe(
      "1. Read rules.yaml.\n• Edit params\n\nDone",
    );
  });
  it("classifies diff lines", () => {
    expect(["--- a/x", "+++ b/x", "@@ -1 +1 @@", "+new", "-old", " ctx"].map(diffLineKind)).toEqual([
      "meta",
      "meta",
      "hunk",
      "add",
      "del",
      "ctx",
    ]);
  });
});

describe("TrackBuffer", () => {
  const s = (t: number, x: number): TrackSample => ({
    cam_id: "c1",
    t_game_s: t,
    game_id: "g",
    object: "ball",
    px: [x, 0],
    conf: 1,
  });
  it("interpolates, extrapolates briefly at the live edge, and gives up on gaps", () => {
    const b = new TrackBuffer();
    [s(1.2, 120), s(1.0, 100), s(1.1, 110)].forEach((x) => b.add(x));
    expect(b.pxAt("c1", 1.05)?.[0]).toBeCloseTo(105);
    expect(b.pxAt("c1", 1.25)?.[0]).toBeCloseTo(125);
    expect(b.pxAt("c1", 2)).toBeUndefined();
    expect(b.pxAt("c2", 1)).toBeUndefined();
    b.add({ ...s(1.3, 0), object: "player:1" });
    expect(b.pxAt("c1", 1.3)?.[0]).toBeCloseTo(130);
  });
});

describe("pickAngle at Go live", () => {
  it("gives phones that choose together different angles by their rank", () => {
    const f = (cam_id: string, label: string) =>
      ({ cam_id, label, status: "playing", wall0_ms: 1, offset_s: 0, t_game0_s: 0 }) as never;
    const feeds = [f("c_side", "Side"), f("c_diag", "Diagonal")];
    const phones = ["c_phone2", "c_phone1"];
    const a = pickAngle(feeds, [], "c_phone1", undefined, 0, phones);
    const b = pickAngle(feeds, [], "c_phone2", undefined, 0, phones);
    expect(a).not.toBe(b);
  });
});
