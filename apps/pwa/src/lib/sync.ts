// Replayed-feed playback sync (D-42, docs/plan/judging-demo.md "Timing"). Pure functions so they can be tested.
//   clip time shown at server time `now`:  offset_s + (now - wall0_ms) / 1000
//   game time of clip time t:              t_game0_s + (t - offset_s)
import type { Feed } from "@trophy/state-client";

export type FeedTiming = Pick<Feed, "wall0_ms" | "offset_s" | "duration_s">;

/** Seek when the local video is further than this from the schedule; smaller drift is corrected with playbackRate. */
export const SEEK_MS = 120;
/** No correction inside this band (iOS rate changes cost a little smoothness). */
export const DEADBAND_MS = 15;
export const RATE_MIN = 0.97;
export const RATE_MAX = 1.03;

export function targetClipTime(feed: FeedTiming, serverNowMs: number): number {
  return feed.offset_s + (serverNowMs - feed.wall0_ms) / 1000;
}

export function clipToGame(feed: Pick<Feed, "offset_s" | "t_game0_s">, clipS: number): number {
  return feed.t_game0_s + (clipS - feed.offset_s);
}

export function gameToClip(feed: Pick<Feed, "offset_s" | "t_game0_s">, gameS: number): number {
  return feed.offset_s + (gameS - feed.t_game0_s);
}

export type Phase = { kind: "countdown"; seconds: number } | { kind: "playing"; t: number } | { kind: "ended" };

/** Where the schedule says this angle is at `serverNowMs`. */
export function phaseAt(feed: FeedTiming, serverNowMs: number): Phase {
  if (serverNowMs < feed.wall0_ms)
    return { kind: "countdown", seconds: Math.ceil((feed.wall0_ms - serverNowMs) / 1000) };
  const t = targetClipTime(feed, serverNowMs);
  if (t >= feed.offset_s + feed.duration_s) return { kind: "ended" };
  return { kind: "playing", t };
}

export type Correction = { kind: "seek" } | { kind: "rate"; rate: number };

/**
 * What to do about a drift (local video time minus scheduled time, ms; positive = ahead). Large drift seeks; small
 * drift nudges playbackRate so that 120 ms is worked off in about 4 s, clamped to 0.97-1.03.
 */
export function correctionFor(driftMs: number): Correction {
  if (!Number.isFinite(driftMs) || Math.abs(driftMs) > SEEK_MS) return { kind: "seek" };
  if (Math.abs(driftMs) <= DEADBAND_MS) return { kind: "rate", rate: 1 };
  const rate = 1 - driftMs * 0.00025;
  return { kind: "rate", rate: Math.min(RATE_MAX, Math.max(RATE_MIN, rate)) };
}

/** Server-clock now from the ctl socket's fit (offset = server - phone, ms). */
export function serverNow(offsetMs: number | null | undefined, phoneNowMs: number = Date.now()): number {
  return phoneNowMs + (offsetMs ?? 0);
}
