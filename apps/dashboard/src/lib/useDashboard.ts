// Everything the dashboard shows, from @trophy/state-client (Spacetime, or a labelled-synthetic MockState script).
import { useEffect, useState } from "react";
import {
  createState,
  type AiVote,
  type Ask,
  type Call,
  type Camera,
  type Challenge,
  type Game,
  type HouseRule,
  type MockScript,
  type Observation,
  type Score,
  type TrackSample,
  type TrophyState,
} from "@trophy/state-client";

export interface DashboardView {
  ready: boolean;
  error?: string;
  synthetic: boolean;
  label?: string;
  game?: Game;
  scores: Score[];
  calls: Call[]; // newest first
  votes: AiVote[];
  challenges: Challenge[];
  houseRules: HouseRule[]; // newest first
  asks: Ask[]; // newest first
  cameras: Camera[];
  observations: Observation[]; // newest first, capped
  trail: TrackSample[]; // oldest first, capped
}

export type Source =
  | { kind: "spacetime"; uri: string; module: string; gameId: string }
  | { kind: "mock"; script: MockScript };

const MAX_OBS = 200;
const MAX_TRAIL = 120; // 12 s at 10 Hz

export function upsert<T>(list: T[], item: T, key: (t: T) => string): T[] {
  const k = key(item);
  const i = list.findIndex((x) => key(x) === k);
  if (i < 0) return [item, ...list];
  const out = list.slice();
  out[i] = item;
  return out;
}

const empty: DashboardView = {
  ready: false,
  synthetic: false,
  scores: [],
  calls: [],
  votes: [],
  challenges: [],
  houseRules: [],
  asks: [],
  cameras: [],
  observations: [],
  trail: [],
};

export function useDashboard(source: Source | undefined): DashboardView {
  const [v, setV] = useState<DashboardView>(empty);

  useEffect(() => {
    if (!source) return;
    setV(empty);
    const state: TrophyState =
      source.kind === "mock"
        ? createState("mock", { script: source.script, loop: true })
        : createState("spacetime", { uri: source.uri, module: source.module });
    const set = (patch: (p: DashboardView) => Partial<DashboardView>) => setV((p) => ({ ...p, ...patch(p) }));
    const byNewest = <T extends { created_at_ms: number }>(a: T, b: T) => b.created_at_ms - a.created_at_ms;

    const offs = [
      state.onGame((game) => set(() => ({ game, synthetic: state.synthetic, label: state.label }))),
      state.onScore((scores) => set(() => ({ scores }))),
      state.onCameras((cameras) => set(() => ({ cameras }))),
      state.onCall((c) => set((p) => ({ calls: upsert(p.calls, c, (x) => x.id).sort(byNewest) }))),
      state.onAiVote((vote) => set((p) => ({ votes: upsert(p.votes, vote, (x) => `${x.call_id}/${x.backend}`) }))),
      state.onChallenge((c) => set((p) => ({ challenges: upsert(p.challenges, c, (x) => x.challenge_id) }))),
      state.onHouseRule((h) =>
        set((p) => ({ houseRules: upsert(p.houseRules, h, (x) => x.rule_version).sort(byNewest) })),
      ),
      state.onAsk((a) => set((p) => ({ asks: upsert(p.asks, a, (x) => x.ask_id).sort(byNewest) }))),
      state.onObservation((o) =>
        set((p) => ({ observations: upsert(p.observations, o, (x) => x.id).slice(0, MAX_OBS) })),
      ),
      state.onTrackSample((s) =>
        set((p) => ({
          trail: [...p.trail, s].sort((a, b) => a.t_game_s - b.t_game_s).slice(-MAX_TRAIL),
        })),
      ),
    ];
    state
      .connect(source.kind === "mock" ? source.script.game_id : source.gameId)
      .then(() => set(() => ({ ready: true, error: undefined, synthetic: state.synthetic, label: state.label })))
      .catch((e: unknown) => set(() => ({ error: String(e instanceof Error ? e.message : e) })));
    return () => {
      offs.forEach((off) => off());
      state.disconnect();
    };
  }, [source]);

  return v;
}
