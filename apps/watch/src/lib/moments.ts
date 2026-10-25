// Post-game logic over Spacetime rows (interfaces-v1 §19), pure so it can be tested without a DOM. Times are game
// seconds (t_game_s); the player maps them to each recording's media time.
import type { Call, Moment, Observation, Rally } from "@trophy/state-client";

export interface Range {
  t0: number;
  t1: number;
  label: string;
  momentId?: string;
}

// ---------------------------------------------------------------- filters
export type FilterId = "all" | "points" | "serve_faults" | "edges" | "challenges" | "long_rallies" | "bookmarks";

export const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "points", label: "Points" },
  { id: "serve_faults", label: "Serve faults" },
  { id: "edges", label: "Edge balls" },
  { id: "challenges", label: "Challenges" },
  { id: "long_rallies", label: "Rallies > 8 shots" },
  { id: "bookmarks", label: "Bookmarks" },
];

/** Shots in a rally window, counted from table bounces (a measurement, not a guess; 0 if none were seen). */
export function shotsIn(observations: Observation[], t0: number, t1: number): number {
  return observations.filter((o) => o.type === "bounce" && o.t_game_s >= t0 && o.t_game_s <= t1).length;
}

export function matches(m: Moment, f: FilterId, observations: Observation[] = []): boolean {
  switch (f) {
    case "all":
      return true;
    case "points":
      return m.kind === "point" || m.kind === "edge" || m.kind === "serve_fault";
    case "serve_faults":
      return m.kind === "serve_fault";
    case "edges":
      return m.kind === "edge" || m.tags.includes("edge");
    case "challenges":
      return m.kind === "challenge" || m.tags.includes("challenge");
    case "long_rallies":
      return shotsIn(observations, m.t_start_s, m.t_end_s) > 8;
    case "bookmarks":
      return m.kind === "bookmark";
  }
}

export const byTime = (a: Moment, b: Moment) => a.t_game_s - b.t_game_s;

// ---------------------------------------------------------------- highlights + condensed
/** Highlights: the top moments by highlight_score, in game order, always ending on the Play of the game. */
export function highlights(moments: Moment[], max = 6): Moment[] {
  const best = moments.find((m) => m.is_best_play);
  const ranked = moments
    .filter((m) => m !== best && m.kind !== "house_rule" && m.highlight_score > 0)
    .sort((a, b) => b.highlight_score - a.highlight_score)
    .slice(0, best ? max - 1 : max)
    .sort(byTime);
  return best ? [...ranked, best] : ranked;
}

/** A moment's clip: the rally around it, with a little lead-in and tail. */
export function momentRange(m: Moment): Range {
  const t0 = Math.min(m.t_start_s, m.t_game_s) - 1;
  const t1 = Math.max(m.t_end_s, m.t_game_s) + 1.5;
  return { t0: Math.max(0, t0), t1, label: m.label, momentId: m.moment_id };
}

/** Condensed game: each closed rally from 0.5 s before it starts to 1 s after it ends; overlaps merge. */
export function condensed(rallies: Rally[]): Range[] {
  const out: Range[] = [];
  for (const r of [...rallies].filter((r) => r.t_end_s != null).sort((a, b) => a.t_start_s - b.t_start_s)) {
    const t0 = Math.max(0, r.t_start_s - 0.5);
    const t1 = (r.t_end_s as number) + 1;
    const last = out[out.length - 1];
    if (last && t0 <= last.t1) last.t1 = Math.max(last.t1, t1);
    else out.push({ t0, t1, label: `Rally ${r.rally_no}` });
  }
  return out;
}

/** Where a playlist goes next: the index of the range containing t, or the next one, or -1 at the end. */
export function playlistStep(ranges: Range[], i: number, t: number): { index: number; seek?: number } {
  const cur = ranges[i];
  if (!cur) return { index: -1 };
  if (t < cur.t1) return { index: i };
  const next = ranges[i + 1];
  return next ? { index: i + 1, seek: next.t0 } : { index: -1 };
}

// ---------------------------------------------------------------- stats (auto-detected; "not detected", never a guessed 0)
export type Stat = number | null;

export interface SideStats {
  points: Stat;
  onServe: Stat;
  onReceive: Stat;
  serveFaults: Stat;
  edgesFor: Stat;
  challengesWon: Stat;
  challengesLost: Stat;
}

export interface GameStats {
  sides: Record<string, SideStats>;
  longestRally: Stat;
  bounces: { x: number; y: number; side?: string }[];
}

const SERVE_FAULT = /^illegal_|serve_/;

export function stats(
  teams: string[],
  calls: Call[],
  rallies: Rally[],
  observations: Observation[],
  servers: Record<number, string> = {},
): GameStats {
  const live = calls.filter((c) => c.status !== "voided" && c.status !== "overturned" && c.kind !== "info");
  const scoring = live.filter((c) => c.team_id && (c.points ?? 0) > 0);
  const anyServer = Object.keys(servers).length > 0;
  const sides: Record<string, SideStats> = {};
  for (const t of teams) {
    const won = scoring.filter((c) => c.team_id === t);
    const onServe = anyServer ? won.filter((c) => c.rally_no != null && servers[c.rally_no] === t).length : null;
    sides[t] = {
      points: scoring.length ? won.reduce((n, c) => n + (c.points ?? 1), 0) : null,
      onServe,
      onReceive: onServe === null ? null : won.length - onServe,
      // a serve fault awards the point to the other side, so count faults against the side that didn't score
      serveFaults: live.some((c) => SERVE_FAULT.test(c.outcome) || SERVE_FAULT.test(c.rule_id))
        ? live.filter(
            (c) => (SERVE_FAULT.test(c.outcome) || SERVE_FAULT.test(c.rule_id)) && c.team_id && c.team_id !== t,
          ).length
        : null,
      edgesFor: live.some((c) => c.kind === "edge_call")
        ? live.filter((c) => c.kind === "edge_call" && c.team_id === t).length
        : null,
      challengesWon: null,
      challengesLost: null,
    };
  }
  const shots = rallies
    .filter((r) => r.t_end_s != null)
    .map((r) => shotsIn(observations, r.t_start_s, r.t_end_s as number));
  const longest = shots.length && Math.max(...shots) > 0 ? Math.max(...shots) : null;
  const bounces = observations
    .filter((o) => o.type === "bounce" && o.pos_m)
    .map((o) => ({ x: o.pos_m!.x, y: o.pos_m!.y, ...(o.side ? { side: o.side } : {}) }));
  return { sides, longestRally: longest, bounces };
}

export const fmtStat = (v: Stat) => (v === null ? "not detected" : String(v));

// ---------------------------------------------------------------- search (keyword fallback; Moss search when the rules service runs)
const SYNONYMS: Record<string, string[]> = {
  edge: ["edge"],
  serve: ["serve_fault", "toss", "serve"],
  fault: ["serve_fault", "fault"],
  challenge: ["challenge", "upheld", "overturned"],
  point: ["point"],
  rally: ["rally"],
  best: ["best"],
};

export function keywordSearch(moments: Moment[], q: string): Moment[] {
  const words = q
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length > 1 && !["the", "every", "all", "by", "of", "show", "me", "side"].includes(w));
  if (!words.length) return [];
  const sideWord = q
    .toLowerCase()
    .match(/\b(?:side|team)\s+([ab])\b/)?.[1]
    ?.toUpperCase();
  return moments
    .map((m) => {
      const hay = [m.label, m.kind, ...m.tags, ...m.reasons, m.is_best_play ? "best play of the game" : ""]
        .join(" ")
        .toLowerCase();
      const score = words.reduce((n, w) => n + ((SYNONYMS[w] ?? [w]).some((s) => hay.includes(s)) ? 1 : 0), 0);
      return { m, score: sideWord && m.team_id !== sideWord ? 0 : score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.m.t_game_s - b.m.t_game_s)
    .map((x) => x.m);
}

// ---------------------------------------------------------------- seek-bar notches + storyboard sprite
export type NotchKind = "tall" | "short" | "diamond";

export function notchKind(m: Moment): NotchKind {
  if (m.kind === "bookmark") return "diamond";
  if (m.kind === "point" || m.kind === "basket") return "tall";
  return "short";
}

export interface SpriteSpec {
  url_template: string;
  cols: number;
  rows: number;
  every_s: number;
  w: number;
  h: number;
}

/** The storyboard cell for a media time: which sheet, and the cell's offset inside it. */
export function spriteCell(spec: SpriteSpec, mediaT: number): { sheet: number; x: number; y: number } {
  const idx = Math.max(0, Math.floor(mediaT / spec.every_s));
  const per = spec.cols * spec.rows;
  const cell = idx % per;
  return { sheet: Math.floor(idx / per), x: (cell % spec.cols) * spec.w, y: Math.floor(cell / spec.cols) * spec.h };
}
