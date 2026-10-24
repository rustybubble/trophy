// Game state from @trophy/state-client, plus the call UX side effects: banner, beep, flash, spoken line,
// and the call_ack that lets the gateway measure call -> phone latency.
import { useEffect, useRef, useState } from "react";
import {
  createState,
  type Ask,
  type Call,
  type Camera,
  type Challenge,
  type Game,
  type HouseRule,
  type MockScript,
  type Score,
  type TrophyState,
} from "@trophy/state-client";
import { beep } from "./audio.ts";
import type { Session } from "./api.ts";
import type { CtlSocket } from "./ctl.ts";
import type { Voice } from "./voice.ts";

export interface GameView {
  ready: boolean;
  error?: string;
  synthetic: boolean;
  label?: string;
  game?: Game;
  scores: Score[];
  calls: Call[]; // newest first
  cameras: Camera[];
  challenges: Challenge[];
  houseRules: HouseRule[];
  asks: Ask[];
  banner?: Call;
  flash?: string;
}

const FRESH_MS = 15_000; // calls older than this when they arrive (e.g. on reconnect) are listed, not announced

function upsert<T>(list: T[], item: T, key: (t: T) => string): T[] {
  const k = key(item);
  const i = list.findIndex((x) => key(x) === k);
  if (i < 0) return [item, ...list];
  const out = list.slice();
  out[i] = item;
  return out;
}

export function useGame(
  session: Session | undefined,
  deps: { voice?: Voice; ctl?: CtlSocket; readEverything: boolean; mock?: MockScript },
): GameView {
  const [v, setV] = useState<GameView>({
    ready: false,
    synthetic: false,
    scores: [],
    calls: [],
    cameras: [],
    challenges: [],
    houseRules: [],
    asks: [],
  });
  const depsRef = useRef(deps);
  depsRef.current = deps;

  useEffect(() => {
    if (!session) return;
    const state: TrophyState = deps.mock
      ? createState("mock", { script: deps.mock, loop: true })
      : createState("spacetime", { uri: session.stdb.uri, module: session.stdb.module });
    let bannerTimer: ReturnType<typeof setTimeout> | undefined;
    let flashTimer: ReturnType<typeof setTimeout> | undefined;
    const set = (patch: Partial<GameView> | ((p: GameView) => Partial<GameView>)) =>
      setV((p) => ({ ...p, ...(typeof patch === "function" ? patch(p) : patch) }));

    const announce = (c: Call) => {
      const { voice, ctl } = depsRef.current;
      set({ banner: c });
      clearTimeout(bannerTimer);
      bannerTimer = setTimeout(() => set({ banner: undefined }), 6000);
      beep(c.cue.beep);
      if (c.cue.flash !== "none") {
        set({ flash: c.cue.flash });
        clearTimeout(flashTimer);
        flashTimer = setTimeout(() => set({ flash: undefined }), 450);
      }
      ctl?.callAck(c.id);
      void voice?.speak(c.speech, { voice: "calls", interrupt: true, ...(c.emotion ? { emotion: c.emotion } : {}) });
    };

    const offs = [
      state.onGame((game) => set({ game, synthetic: state.synthetic, label: state.label })),
      state.onScore((scores) => {
        set({ scores });
        if (depsRef.current.readEverything && scores.length) {
          void depsRef.current.voice?.speak(`Score ${scores.map((s) => s.points).join(" to ")}.`, { voice: "ref" });
        }
      }),
      state.onCameras((cameras) => set({ cameras })),
      state.onCall((c, change) => {
        set((p) => ({ calls: upsert(p.calls, c, (x) => x.id).sort((a, b) => b.created_at_ms - a.created_at_ms) }));
        if (change === "insert" && Date.now() - c.created_at_ms < FRESH_MS) announce(c);
        if (change === "update" && (c.status === "upheld" || c.status === "overturned")) {
          void depsRef.current.voice?.speak(`Call ${c.status}.`, { voice: "ref", interrupt: true });
        }
      }),
      state.onChallenge((c) => set((p) => ({ challenges: upsert(p.challenges, c, (x) => x.challenge_id) }))),
      state.onHouseRule((h) => set((p) => ({ houseRules: upsert(p.houseRules, h, (x) => x.rule_version) }))),
      state.onAsk((a) => set((p) => ({ asks: upsert(p.asks, a, (x) => x.ask_id) }))),
    ];
    state
      .connect(session.gameId)
      .then(() => set({ ready: true, error: undefined, synthetic: state.synthetic, label: state.label }))
      .catch((e: unknown) => set({ error: String(e instanceof Error ? e.message : e) }));
    return () => {
      offs.forEach((off) => off());
      state.disconnect();
      clearTimeout(bannerTimer);
      clearTimeout(flashTimer);
    };
  }, [session, deps.mock]);

  return v;
}
