// The game's post-game rows from @trophy/state-client: Spacetime, or a labelled-synthetic MockState script.
import { useEffect, useState } from "react";
import {
  createState,
  type AiVote,
  type Call,
  type Commentary,
  type Game,
  type MockScript,
  type Moment,
  type Observation,
  type Rally,
  type Score,
  type TrackSample,
  type TrophyState,
} from "@trophy/state-client";

export interface GameData {
  ready: boolean;
  error?: string;
  synthetic: boolean;
  label?: string;
  game?: Game;
  scores: Score[];
  calls: Call[];
  rallies: Rally[];
  moments: Moment[]; // in game order
  votes: AiVote[];
  observations: Observation[];
  trail: TrackSample[];
  commentary: Commentary[];
}

export type Source =
  | { kind: "spacetime"; uri: string; module: string; gameId: string }
  | { kind: "mock"; script: MockScript };

function upsert<T>(list: T[], item: T, key: (t: T) => string): T[] {
  const k = key(item);
  const i = list.findIndex((x) => key(x) === k);
  if (i < 0) return [...list, item];
  const out = list.slice();
  out[i] = item;
  return out;
}

const empty: GameData = {
  ready: false,
  synthetic: false,
  scores: [],
  calls: [],
  rallies: [],
  moments: [],
  votes: [],
  observations: [],
  trail: [],
  commentary: [],
};

export function useGameData(source: Source | undefined): GameData {
  const [d, setD] = useState<GameData>(empty);
  useEffect(() => {
    if (!source) return;
    setD(empty);
    // a finished game is static: play the synthetic script once, fast, rather than in real time
    const state: TrophyState =
      source.kind === "mock"
        ? createState("mock", { script: source.script, speed: 50 })
        : createState("spacetime", { uri: source.uri, module: source.module });
    const set = (f: (p: GameData) => Partial<GameData>) => setD((p) => ({ ...p, ...f(p) }));
    const offs = [
      state.onGame((game) => set(() => ({ game, synthetic: state.synthetic, label: state.label }))),
      state.onScore((scores) => set(() => ({ scores }))),
      state.onCall((c) => set((p) => ({ calls: upsert(p.calls, c, (x) => x.id) }))),
      state.onRally((r) => set((p) => ({ rallies: upsert(p.rallies, r, (x) => String(x.rally_no)) }))),
      state.onMoment((m) =>
        set((p) => ({
          moments: upsert(p.moments, m, (x) => x.moment_id).sort((a, b) => a.t_game_s - b.t_game_s),
        })),
      ),
      state.onAiVote((v) => set((p) => ({ votes: upsert(p.votes, v, (x) => `${x.call_id}/${x.backend}`) }))),
      state.onObservation((o) => set((p) => ({ observations: upsert(p.observations, o, (x) => x.id) }))),
      state.onTrackSample((s) => set((p) => ({ trail: upsert(p.trail, s, (x) => `${x.cam_id}/${x.t_game_s}`) }))),
      state.onCommentary((c) =>
        set((p) => ({ commentary: upsert(p.commentary, c, (x) => `${x.moment_id}/${x.voice}`) })),
      ),
    ];
    state
      .connect(source.kind === "mock" ? source.script.game_id : source.gameId)
      .then(() => set(() => ({ ready: true, synthetic: state.synthetic, label: state.label })))
      .catch((e: unknown) => set(() => ({ error: String(e instanceof Error ? e.message : e) })));
    return () => {
      offs.forEach((off) => off());
      state.disconnect();
    };
  }, [source]);
  return d;
}
