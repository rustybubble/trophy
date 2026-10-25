// Every Spacetime table the judging UI reads (D-21, D-42): the same rows on every device. Side effects (beep, speech)
// are handed to the caller through `events`, so this hook only mirrors state.
import { useEffect, useRef, useState } from "react";
import type {
  AiVote,
  Ask,
  Call,
  Camera,
  Challenge,
  DroidRun,
  Feed,
  Game,
  HouseRule,
  Observation,
  RowChange,
  Score,
  TrackSample,
  TrophyState,
  Viewer,
} from "@trophy/state-client";

export interface TrophyView {
  ready: boolean;
  error?: string;
  synthetic: boolean;
  label?: string;
  game?: Game;
  scores: Score[];
  /** newest first */
  calls: Call[];
  cameras: Camera[];
  challenges: Challenge[];
  houseRules: HouseRule[];
  droidRuns: DroidRun[];
  asks: Ask[];
  votes: AiVote[];
  feeds: Feed[];
  viewers: Viewer[];
  /** newest first, the last 40 */
  observations: Observation[];
}

export interface TrophyEvents {
  onCall?: (c: Call, change: RowChange) => void;
  onChallenge?: (c: Challenge, change: RowChange) => void;
  onAsk?: (a: Ask, change: RowChange) => void;
}

/** Ball track per camera, kept outside React state (10 Hz per camera would re-render too often). */
export class TrackBuffer {
  private byCam = new Map<string, TrackSample[]>();
  /** phone ms of the newest ball sample per camera */
  lastSeen = new Map<string, number>();

  add(s: TrackSample): void {
    if (s.object !== "ball") return;
    let list = this.byCam.get(s.cam_id);
    if (!list) this.byCam.set(s.cam_id, (list = []));
    let i = list.length;
    while (i > 0 && list[i - 1]!.t_game_s > s.t_game_s) i--;
    if (list[i - 1]?.t_game_s === s.t_game_s) list[i - 1] = s;
    else list.splice(i, 0, s);
    if (list.length > 400) list.splice(0, list.length - 400);
    this.lastSeen.set(s.cam_id, Date.now());
  }

  /** The ball's image position at game time t, interpolated between samples at most `gapS` apart. */
  pxAt(camId: string, t: number, gapS = 0.25): [number, number] | undefined {
    const list = this.byCam.get(camId);
    if (!list?.length) return undefined;
    let hi = list.findIndex((s) => s.t_game_s >= t);
    if (hi < 0) hi = list.length;
    const a = list[hi - 1];
    const b = list[hi];
    if (a?.px && b?.px && b.t_game_s - a.t_game_s <= gapS) {
      const k = (t - a.t_game_s) / (b.t_game_s - a.t_game_s);
      return [a.px[0] + (b.px[0] - a.px[0]) * k, a.px[1] + (b.px[1] - a.px[1]) * k];
    }
    // past the newest sample (the live edge): extrapolate from the last two for up to 150 ms
    const p = list[hi - 2];
    if (!b && a?.px && p?.px && t - a.t_game_s <= 0.15 && a.t_game_s - p.t_game_s <= gapS) {
      const k = (t - a.t_game_s) / (a.t_game_s - p.t_game_s);
      return [a.px[0] + (a.px[0] - p.px[0]) * k, a.px[1] + (a.px[1] - p.px[1]) * k];
    }
    const near = [a, b].find((s) => s?.px && Math.abs(s.t_game_s - t) <= gapS / 2);
    return near?.px ? [near.px[0], near.px[1]] : undefined;
  }

  clear(): void {
    this.byCam.clear();
    this.lastSeen.clear();
  }
}

function upsert<T>(list: T[], item: T, key: (t: T) => string): T[] {
  const k = key(item);
  const i = list.findIndex((x) => key(x) === k);
  if (i < 0) return [item, ...list];
  const out = list.slice();
  out[i] = item;
  return out;
}

const EMPTY: TrophyView = {
  ready: false,
  synthetic: false,
  scores: [],
  calls: [],
  cameras: [],
  challenges: [],
  houseRules: [],
  droidRuns: [],
  asks: [],
  votes: [],
  feeds: [],
  viewers: [],
  observations: [],
};

export function useTrophy(
  state: TrophyState | undefined,
  gameId: string,
  events: TrophyEvents,
): { v: TrophyView; track: TrackBuffer } {
  const [v, setV] = useState<TrophyView>(EMPTY);
  const [track] = useState(() => new TrackBuffer());
  const ev = useRef(events);
  ev.current = events;

  useEffect(() => {
    if (!state) return;
    setV(EMPTY);
    track.clear();
    const seenChallenges = new Set<string>();
    const seenAsks = new Set<string>();
    const set = (patch: Partial<TrophyView> | ((p: TrophyView) => Partial<TrophyView>)) =>
      setV((p) => ({ ...p, ...(typeof patch === "function" ? patch(p) : patch) }));
    const offs = [
      // rows arriving means the live state works, even if the subscription was slow to confirm or needed a retry
      state.onGame((game) =>
        set({ game, ready: true, error: undefined, synthetic: state.synthetic, label: state.label }),
      ),
      state.onScore((scores) => set({ scores })),
      state.onCameras((cameras) => set({ cameras })),
      state.onFeeds((feeds) => set({ feeds })),
      state.onViewers((viewers) => set({ viewers })),
      state.onCall((c, change) => {
        set((p) => ({ calls: upsert(p.calls, c, (x) => x.id).sort((a, b) => b.created_at_ms - a.created_at_ms) }));
        ev.current.onCall?.(c, change);
      }),
      state.onChallenge((c) => {
        const change: RowChange = seenChallenges.has(c.challenge_id) ? "update" : "insert";
        seenChallenges.add(c.challenge_id);
        set((p) => ({ challenges: upsert(p.challenges, c, (x) => x.challenge_id) }));
        ev.current.onChallenge?.(c, change);
      }),
      state.onHouseRule((h) => set((p) => ({ houseRules: upsert(p.houseRules, h, (x) => x.rule_version) }))),
      state.onDroidRun((r) => set((p) => ({ droidRuns: upsert(p.droidRuns, r, (x) => x.run_id) }))),
      state.onAiVote((a) => set((p) => ({ votes: upsert(p.votes, a, (x) => `${x.call_id}/${x.backend}`) }))),
      state.onAsk((a) => {
        const change: RowChange = seenAsks.has(a.ask_id) ? "update" : "insert";
        seenAsks.add(a.ask_id);
        set((p) => ({ asks: upsert(p.asks, a, (x) => x.ask_id) }));
        ev.current.onAsk?.(a, change);
      }),
      state.onObservation((o) =>
        set((p) => ({
          observations: upsert(p.observations, o, (x) => x.id)
            .sort((a, b) => b.t_game_s - a.t_game_s)
            .slice(0, 40),
        })),
      ),
      state.onTrackSample((s) => track.add(s)),
    ];
    state
      .connect(gameId)
      .then(() => set({ ready: true, error: undefined, synthetic: state.synthetic, label: state.label }))
      // a slow confirmation is not an outage: only report it when no row ever arrived
      .catch((e: unknown) => {
        if (!state.game()) set({ error: String(e instanceof Error ? e.message : e) });
      });
    return () => {
      offs.forEach((off) => off());
      state.disconnect();
    };
  }, [state, gameId, track]);

  return { v, track };
}
