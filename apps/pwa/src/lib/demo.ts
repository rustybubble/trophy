// Judging-demo helpers (docs/plan/judging-demo.md): angle assignment, spoken lines, challenge verdicts, replay
// windows, and the Droid's plan/diff rendering. Pure, so they are unit-tested.
import type { Call, Challenge, Feed, Viewer } from "@trophy/state-client";

/** A viewer row counts as live when it is connected and was seen recently. */
export const VIEWER_STALE_MS = 8000;

export function liveViewers(viewers: Viewer[], nowMs: number): Viewer[] {
  return viewers.filter((v) => v.connected && nowMs - v.last_seen_ms < VIEWER_STALE_MS);
}

/** Feeds in a stable order every device agrees on (Spacetime doesn't keep insertion order). */
export function sortFeeds(feeds: Feed[]): Feed[] {
  return [...feeds].sort((a, b) => a.label.localeCompare(b.label) || a.cam_id.localeCompare(b.cam_id));
}

/**
 * The angle this phone should show: keep the current one while it exists, else the first angle no other live phone
 * shows yet, else the first angle.
 */
export function pickAngle(
  feeds: Feed[],
  viewers: Viewer[],
  meId: string,
  current: string | undefined,
  nowMs: number,
): string | undefined {
  const sorted = sortFeeds(feeds.filter((f) => f.status !== "failed"));
  if (current && sorted.some((f) => f.cam_id === current)) return current;
  const taken = new Set(
    liveViewers(viewers, nowMs)
      .filter((v) => v.viewer_id !== meId)
      .map((v) => v.cam_id),
  );
  return (sorted.find((f) => !taken.has(f.cam_id)) ?? sorted[0])?.cam_id;
}

/** Every call is spoken with who is at fault: append the name when the engine's line lacks it. */
export function spokenLine(call: Pick<Call, "speech" | "text" | "at_fault">): string {
  const base = (call.speech || call.text || "").trim();
  const name = call.at_fault?.name?.trim();
  if (!name || base.toLowerCase().includes(name.toLowerCase())) return base;
  const sep = !base ? "" : /[.!?]$/.test(base) ? " " : ". ";
  return `${base}${sep}${name}.`;
}

/** Drops a line already spoken in the last `windowMs` (the engine and the phone may both voice the same text). */
export class SpeechGate {
  private recent = new Map<string, number>();
  constructor(private readonly windowMs = 6000) {}
  allow(text: string, nowMs: number = Date.now()): boolean {
    const k = text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
    if (!k) return false;
    for (const [t, at] of this.recent) if (nowMs - at > this.windowMs) this.recent.delete(t);
    if (this.recent.has(k)) return false;
    this.recent.set(k, nowMs);
    return true;
  }
}

export type Verdict = "reviewing" | "upheld" | "overturned" | "players";

/** An open challenge is under review; resolved as players_decide (or without a result) means the players decide. */
export function verdictOf(ch: Pick<Challenge, "status" | "result">): Verdict {
  if (ch.status !== "resolved") return "reviewing";
  return ch.result === "upheld" ? "upheld" : ch.result === "overturned" ? "overturned" : "players";
}

export const VERDICT_TEXT: Record<Verdict, string> = {
  reviewing: "Reviewing…",
  upheld: "Call stands",
  overturned: "Overturned",
  players: "Players decide",
};

/** The engine writes the verdict's explanation on the challenge row, the challenged call and any replacement call. */
export function explanationFor(
  ch: Pick<Challenge, "call_id" | "explanation">,
  calls: Call[],
): { text?: string; replacement?: Call } {
  const replacement = calls.find((c) => c.supersedes === ch.call_id);
  const original = calls.find((c) => c.id === ch.call_id);
  return { text: ch.explanation ?? replacement?.explanation ?? original?.explanation ?? undefined, replacement };
}

/**
 * Whether a freshly inserted call is announced (beep + speech). Everything the engine posts is, including its info
 * calls ("Challenge. Let's look at the replay.", the verdict) and a challenge's replacement call, whose speech is the
 * explanation. Calls a house rule re-judged (superseding a call nobody challenged) are not: the engine announces the
 * rule once with an info call instead.
 */
export function shouldAnnounce(c: Call, challengedCallIds: Set<string>): boolean {
  if (c.supersedes && !challengedCallIds.has(c.supersedes)) return false;
  return !!(c.speech || c.text);
}

/** The newest call a challenge can target: any tier, not info, not already superseded or voided. */
export function challengeTarget(calls: Call[]): Call | undefined {
  return [...calls]
    .sort((a, b) => b.created_at_ms - a.created_at_ms)
    .find((c) => c.kind !== "info" && c.kind !== "score_update" && c.status !== "voided" && c.status !== "overturned");
}

/** The call the big banner shows: the newest decision (info lines are shown separately). */
export function bannerCall(calls: Call[]): Call | undefined {
  return [...calls]
    .sort((a, b) => b.created_at_ms - a.created_at_ms)
    .find((c) => c.kind !== "info" && c.status !== "voided");
}

export interface ClipWindow {
  cam_id: string;
  t0_s: number;
  t1_s: number;
}

/**
 * The replay window per angle (game seconds): the call's evidence for that camera, else its evidence for any camera,
 * else t_game_s ± 3 s. Clamped to t ≥ 0 and the recorder's 30 s maximum.
 */
export function replayWindows(call: Pick<Call, "evidence" | "t_game_s">, camIds: string[]): ClipWindow[] {
  return camIds.map((cam_id) => {
    const ev = call.evidence.find((e) => e.cam_id === cam_id) ?? call.evidence[0];
    let t0 = ev?.t0_s ?? call.t_game_s - 3;
    let t1 = ev?.t1_s ?? call.t_game_s + 3;
    t0 = Math.max(0, t0);
    if (t1 <= t0) t1 = t0 + 3;
    if (t1 - t0 > 30) t0 = t1 - 30;
    return { cam_id, t0_s: Math.round(t0 * 1000) / 1000, t1_s: Math.round(t1 * 1000) / 1000 };
  });
}

/** Markdown → plain text for the Droid's plan (headings, emphasis, code and links stripped; bullets kept). */
export function mdToText(md: string): string {
  return md
    .replace(/```[a-z]*\n?/gi, "")
    .split("\n")
    .filter((l) => !/^\s{0,3}#{1,6}\s+plan\s*:?\s*$/i.test(l)) // the sheet already labels it "Plan"
    .map((l) =>
      l
        .replace(/^\s{0,3}#{1,6}\s+/, "")
        .replace(/^\s*[-*+]\s+/, "• ")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/(\*\*|__)(.+?)\1/g, "$2")
        .replace(/(\*|_)(.+?)\1/g, "$2")
        .replace(/`([^`]+)`/g, "$1")
        .trimEnd(),
    )
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export type DiffKind = "add" | "del" | "hunk" | "meta" | "ctx";

export function diffLineKind(line: string): DiffKind {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") || line.startsWith("index "))
    return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "ctx";
}

export function fmtDrift(ms: number | undefined | null): string {
  if (ms === undefined || ms === null || !Number.isFinite(ms)) return "—";
  const r = Math.round(ms);
  return `${r > 0 ? "+" : ""}${r} ms`;
}
