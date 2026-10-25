import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createState, type Ask, type Call, type Challenge, type RowChange } from "@trophy/state-client";
import { Api, forgetSession, type AskAnswer, type Session } from "../lib/api.ts";
import { buildAskContext } from "../lib/askContext.ts";
import { beep } from "../lib/audio.ts";
import { GatewayBackend, type Backend } from "../lib/backend.ts";
import { CtlSocket, type SyncState } from "../lib/ctl.ts";
import {
  bannerCall,
  challengeTarget,
  liveViewers,
  pickAngle,
  shouldAnnounce,
  sortFeeds,
  spokenLine,
  SpeechGate,
} from "../lib/demo.ts";
import { parseIntent } from "../lib/intent.ts";
import { serverNow } from "../lib/sync.ts";
import { useTrophy } from "../lib/useTrophy.ts";
import { Voice } from "../lib/voice.ts";
import type { MockBackend } from "../mock/mockBackend.ts";
import { AngleVideo, type PlayStatus } from "./AngleVideo.tsx";
import { DroidSheet, droidItems } from "./DroidSheet.tsx";
import { GameSheet } from "./GameSheet.tsx";
import { ChevronIcon, DroidIcon, SpeakerIcon } from "./icons.tsx";
import { NetworkSheet } from "./NetworkSheet.tsx";
import { AnswerCard, CallCard, HoldToTalk, TopBar } from "./parts.tsx";
import { ReplaySheet } from "./ReplaySheet.tsx";

const FRESH_CALL_MS = 15_000; // older calls (a reconnect, a late join) are shown, not announced
const FRESH_CHALLENGE_MS = 30_000;
const params = new URLSearchParams(location.search);

const pref = (k: string, d: boolean) => {
  try {
    const v = localStorage.getItem(`trophy.pref.${k}`);
    return v === null ? d : v === "1";
  } catch {
    return d;
  }
};
const savePref = (k: string, v: boolean) => {
  try {
    localStorage.setItem(`trophy.pref.${k}`, v ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
};

type SheetName = "replay" | "network" | "droid" | "game";

/** The angle view: this phone's replayed angle in sync, the latest call, and two controls. */
export function Main(props: {
  session: Session;
  name: string;
  mock?: MockBackend;
  joinLink?: string;
  onLeave: () => void;
}) {
  const { session, mock } = props;
  const api = useMemo(() => new Api(session), [session]);
  const backend: Backend = useMemo(() => mock ?? new GatewayBackend(api), [mock, api]);
  const state = useMemo(
    () => mock?.state ?? createState("spacetime", { uri: session.stdb.uri, module: session.stdb.module }),
    [mock, session.stdb.uri, session.stdb.module],
  );
  const voice = useMemo(() => (mock ? undefined : new Voice(api)), [api, mock]);
  const [sync, setSync] = useState<SyncState>({ connected: false, offsetMs: null, syncErrMs: null });
  const ctl = useMemo(() => (mock ? undefined : new CtlSocket(api.wsUrl("ctl"), setSync)), [api, mock]);
  const syncRef = useRef(sync);
  syncRef.current = sync;
  const now = useCallback(() => serverNow(syncRef.current.offsetMs), []);

  const [soundOn, setSoundOn] = useState(() => pref("sound", true));
  const soundRef = useRef(soundOn);
  soundRef.current = soundOn;
  useEffect(() => {
    if (voice) voice.enabled = soundOn;
  }, [voice, soundOn]);

  const [toast, setToast] = useState<string>();
  const say = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast((t) => (t === m ? undefined : t)), 3500);
  }, []);
  const [sheet, setSheet] = useState<SheetName>();
  const [replayId, setReplayId] = useState<string>();
  const [freshId, setFreshId] = useState<string>();
  const [ticker, setTicker] = useState<string>();
  const [answer, setAnswer] = useState<{ q: string; a?: AskAnswer; err?: string }>();
  const pendingAsk = useRef<{ q: string; sinceMs: number } | undefined>(undefined);
  const gate = useRef(new SpeechGate());
  const challenged = useRef(new Set<string>());
  const timers = useRef<{ fresh?: ReturnType<typeof setTimeout>; ticker?: ReturnType<typeof setTimeout> }>({});

  // ---------------------------------------------------------------- calls: beep, then speak with who is at fault
  const announce = (c: Call) => {
    setFreshId(c.id);
    clearTimeout(timers.current.fresh);
    timers.current.fresh = setTimeout(() => setFreshId(undefined), 1500);
    if (c.kind === "info") {
      setTicker(c.text);
      clearTimeout(timers.current.ticker);
      timers.current.ticker = setTimeout(() => setTicker(undefined), 8000);
    }
    if (soundRef.current) beep(c.cue.beep === "none" ? "short" : c.cue.beep);
    ctl?.callAck(c.id);
    const line = spokenLine(c);
    if (line && gate.current.allow(line)) {
      void voice
        ?.speak(line, {
          voice: c.kind === "info" ? "ref" : "calls",
          interrupt: true,
          ...(c.emotion ? { emotion: c.emotion } : {}),
        })
        .catch(() => {});
    }
  };

  const events = {
    onCall: (c: Call, change: RowChange) => {
      if (change !== "insert" || Date.now() - c.created_at_ms > FRESH_CALL_MS) return;
      if (shouldAnnounce(c, challenged.current)) announce(c);
    },
    onChallenge: (ch: Challenge, change: RowChange) => {
      challenged.current.add(ch.call_id);
      if (change === "insert" && ch.status === "open" && Date.now() - ch.created_at_ms < FRESH_CHALLENGE_MS) {
        setReplayId(ch.challenge_id);
        setSheet("replay");
      }
    },
    onAsk: (a: Ask) => {
      // a question answered late (the Droid wrote a check): the referee logs it as an ask row
      const p = pendingAsk.current;
      if (!p || a.question !== p.q || a.created_at_ms < p.sinceMs || !a.answer || a.kind === "pending") return;
      pendingAsk.current = undefined;
      setAnswer({ q: p.q, a: { answer: a.answer, citations: a.citations, latency_ms: a.latency_ms, kind: "check" } });
      const line = a.speech || a.answer;
      if (gate.current.allow(line)) void voice?.speak(line, { voice: "ref", interrupt: true }).catch(() => {});
    },
  };
  const { v, track } = useTrophy(state, session.gameId, events);

  // ---------------------------------------------------------------- clock sync, voice warm-up, wake lock
  useEffect(() => {
    if (!ctl) return;
    ctl.start();
    void voice?.warm().catch(() => say("Voice is unavailable"));
    let lock: { release: () => Promise<void> } | undefined;
    const want = async () => {
      try {
        lock = await (
          navigator as Navigator & { wakeLock?: { request: (t: string) => Promise<typeof lock> } }
        ).wakeLock?.request("screen");
      } catch {
        /* not supported */
      }
    };
    void want();
    const onVis = () => document.visibilityState === "visible" && void want();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      ctl.stop();
      document.removeEventListener("visibilitychange", onVis);
      void lock?.release();
    };
  }, [ctl, voice, say]);

  // mock: go live with the first scenario, so the screen is alive without a host (?mock=1&idle=1 to skip)
  useEffect(() => {
    if (!mock || params.get("idle") === "1") return;
    const t = setTimeout(() => void mock.goLive("tt-two-angle"), 500);
    return () => clearTimeout(t);
  }, [mock]);

  // a 1 s tick for "seen recently" readouts
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // ---------------------------------------------------------------- the angle this phone hosts
  const feeds = useMemo(() => {
    const wall0 = Math.max(...v.feeds.map((f) => f.wall0_ms));
    return sortFeeds(v.feeds.filter((f) => f.wall0_ms === wall0));
  }, [v.feeds]);
  const [angle, setAngle] = useState<string>();
  // the game's phones (joined with a display role; not the dashboard, not the streamed cameras)
  const joinedPhones = useMemo(
    () =>
      v.cameras.filter((c) => c.role.split(",").includes("display") && c.label !== "dashboard").map((c) => c.cam_id),
    [v.cameras],
  );
  useEffect(() => {
    const next = pickAngle(feeds, v.viewers, session.camId, angle, Date.now(), joinedPhones);
    if (next !== angle) setAngle(next);
  }, [feeds, v.viewers, session.camId, angle, joinedPhones]);
  const feed = feeds.find((f) => f.cam_id === angle);

  // report playback drift every 2 s (the engine writes this phone's viewer row)
  const play = useRef<PlayStatus>({ playing: false, driftMs: null });
  const [reportErr, setReportErr] = useState<string>();
  useEffect(() => {
    if (!angle) return;
    const send = () => {
      const p = play.current;
      backend
        .ctl("viewer_status", {
          cam_id: angle,
          playing: p.playing,
          drift_ms: p.driftMs === null ? 0 : Math.round(p.driftMs * 10) / 10,
          name: props.name,
          connected: true,
        })
        .then(
          () => setReportErr(undefined),
          (e: unknown) => setReportErr(e instanceof Error ? e.message : String(e)),
        );
    };
    send();
    const id = setInterval(send, 2000);
    return () => clearInterval(id);
  }, [angle, backend, props.name]);

  // ---------------------------------------------------------------- actions
  // a scenario restarts the game on the same id: only calls since the current scenario began are "now"
  const t0Now = feeds.length ? Math.min(...feeds.map((f) => f.t_game0_s)) - 2 : -Infinity;
  const nowCalls = v.calls.filter((c) => c.t_game_s >= t0Now);
  const target = challengeTarget(nowCalls);
  const openChallengeFor = (callId: string) =>
    [...v.challenges].sort((a, b) => b.created_at_ms - a.created_at_ms).find((c) => c.call_id === callId);

  const challenge = async () => {
    if (!target) return say("Nothing to challenge yet");
    const existing = openChallengeFor(target.id);
    if (target.status === "challenged" && existing) {
      setReplayId(existing.challenge_id);
      setSheet("replay");
      return;
    }
    try {
      await backend.ctl("challenge", { call_id: target.id });
    } catch (e) {
      say(`Challenge failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const submitRule = async (text: string, source: "typed" | "voice"): Promise<boolean> => {
    try {
      await backend.ctl("submit_house_rule", { text, source });
      say("Sent to the Droid");
      return true;
    } catch (e) {
      say(`House rule failed: ${e instanceof Error ? e.message : String(e)}`);
      return false;
    }
  };

  const ruleAction = async (cmd: "revert_house_rule" | "reject_house_rule", rule_version: string) => {
    try {
      await backend.ctl(cmd, { rule_version });
      say(cmd === "revert_house_rule" ? "Undoing the house rule" : "House rule rejected");
    } catch (e) {
      say(`${cmd === "revert_house_rule" ? "Undo" : "Reject"} failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const onTranscript = async (text: string) => {
    const intent = parseIntent(text);
    switch (intent.kind) {
      case "none":
        return;
      case "challenge":
        return challenge();
      case "undo":
        try {
          await backend.ctl("undo_last_call");
        } catch (e) {
          say(`Undo failed: ${e instanceof Error ? e.message : String(e)}`);
        }
        return;
      case "score": {
        const teams = v.game?.teams ?? [];
        const line = v.scores.length
          ? `${v.scores.map((s) => `${teams.find((t) => t.team_id === s.team_id)?.name ?? s.team_id} ${s.points}`).join(", ")}.`
          : "No score yet.";
        return void voice?.speak(line, { voice: "ref", interrupt: true }).catch(() => {});
      }
      case "house_rule":
        if (await submitRule(intent.text, "voice")) setSheet("droid");
        return;
      case "ask":
        setAnswer({ q: intent.question });
        try {
          const a = await backend.ask(intent.question, buildAskContext(v));
          setAnswer({ q: intent.question, a });
          const line = a.speech || a.answer;
          if (gate.current.allow(line)) void voice?.speak(line, { voice: "ref", interrupt: true }).catch(() => {});
          if (a.kind === "pending") pendingAsk.current = { q: intent.question, sinceMs: Date.now() - 2000 };
        } catch (e) {
          setAnswer({ q: intent.question, err: e instanceof Error ? e.message : String(e) });
        }
    }
  };

  const leave = () => {
    forgetSession(session.gameId);
    props.onLeave();
  };

  // ---------------------------------------------------------------- derived readouts
  const phones = liveViewers(v.viewers, nowMs);
  const playingPhones = phones.filter((p) => p.playing);
  const maxDrift = playingPhones.reduce((m, p) => Math.max(m, Math.abs(p.drift_ms)), 0);
  const netState = !feeds.length ? "" : maxDrift < 40 ? "ok" : maxDrift < 120 ? "warn" : "bad";
  const items = droidItems(v.houseRules, v.droidRuns);
  const lastRun = items[0];
  const banner = bannerCall(nowCalls);
  const replayChallenge = v.challenges.find((c) => c.challenge_id === replayId);
  const otherViewers = (cam: string) => phones.filter((p) => p.cam_id === cam && p.viewer_id !== session.camId).length;

  return (
    <div className="app">
      <TopBar
        game={v.game}
        scores={v.scores}
        feed={feed}
        synthetic={v.synthetic || !!v.game?.params?.synthetic}
        onMenu={() => setSheet("game")}
      />

      {feed ? (
        <AngleVideo
          key={feed.cam_id}
          feed={feed}
          src={backend.feedSrc(feed)}
          serverNow={now}
          track={track}
          onStatus={(s) => (play.current = s)}
        />
      ) : (
        <div className="stage">
          <div className="overlay clear">
            <div>
              <p>
                <b>{v.error ? "Can't reach the game state" : v.ready ? "No scenario is live" : "Connecting…"}</b>
              </p>
              <p className="small muted">{v.error ?? "Pick a recording, then press Go live."}</p>
              {v.ready && (
                <p>
                  <button className="btn primary" onClick={() => setSheet("game")}>
                    Choose scenario
                  </button>
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {feeds.length > 1 && (
        <nav className="angles" aria-label="Camera angle">
          {feeds.map((f) => {
            const n = otherViewers(f.cam_id);
            return (
              <button
                key={f.cam_id}
                className={f.cam_id === angle ? "pill on" : "pill"}
                aria-pressed={f.cam_id === angle}
                onClick={() => setAngle(f.cam_id)}
              >
                {f.label}
                {n > 0 && (
                  <span className="n">
                    · {n} phone{n === 1 ? "" : "s"}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      )}

      <main className="body">
        {answer && <AnswerCard q={answer.q} a={answer.a} err={answer.err} onClose={() => setAnswer(undefined)} />}
        {ticker && (
          <div className="ticker" role="status">
            <SpeakerIcon /> {ticker}
          </div>
        )}
        <CallCard call={banner} fresh={!!banner && banner.id === freshId} />

        <button className="row-link" onClick={() => setSheet("network")}>
          <span className={`status-dot ${netState}`} />
          <span className="t">
            <b>Network</b>
            <span>
              {phones.length} phone{phones.length === 1 ? "" : "s"} · {feeds.length} angle
              {feeds.length === 1 ? "" : "s"}
              {playingPhones.length ? ` · in sync ±${Math.round(maxDrift)} ms` : ""}
            </span>
          </span>
          <ChevronIcon />
        </button>
        <button className="row-link" onClick={() => setSheet("droid")}>
          <DroidIcon />
          <span className="t">
            <b>Droid</b>
            <span>
              {lastRun
                ? `${lastRun.rule ? `“${lastRun.rule.text}”` : (lastRun.run?.kind ?? "run")} · ${
                    lastRun.rule?.status === "reverted" ? "undone" : (lastRun.rule?.status ?? lastRun.run?.status)
                  }`
                : "Add a house rule"}
            </span>
          </span>
          <ChevronIcon />
        </button>
      </main>

      <footer className="controls">
        <button className="challenge-btn" disabled={!target} onClick={() => void challenge()}>
          <b>{target?.status === "challenged" ? "Under review" : "Challenge"}</b>
          <span>{target ? target.text : "No call to challenge yet"}</span>
        </button>
        <HoldToTalk
          voice={voice}
          hint="Say “challenge”, “house rule: …”, or ask the ref"
          onTranscript={(t) => void onTranscript(t)}
          onError={say}
        />
      </footer>

      {sheet === "replay" && replayChallenge && (
        <ReplaySheet
          challenge={replayChallenge}
          calls={v.calls}
          feeds={feeds}
          votes={v.votes}
          backend={backend}
          onClose={() => setSheet(undefined)}
        />
      )}
      {sheet === "network" && (
        <NetworkSheet
          feeds={feeds}
          cameras={v.cameras}
          viewers={v.viewers}
          observations={v.observations}
          track={track}
          meId={session.camId}
          sport={v.game?.sport}
          clock={mock ? undefined : sync}
          reportError={reportErr}
          nowMs={nowMs}
          onClose={() => setSheet(undefined)}
        />
      )}
      {sheet === "droid" && (
        <DroidSheet
          rules={v.houseRules}
          runs={v.droidRuns}
          voice={voice}
          onSubmit={submitRule}
          onAct={(cmd, rv) => void ruleAction(cmd, rv)}
          onError={say}
          onClose={() => setSheet(undefined)}
        />
      )}
      {sheet === "game" && (
        <GameSheet
          backend={backend}
          feeds={feeds}
          gameId={session.gameId}
          joinLink={props.joinLink}
          soundOn={soundOn}
          onSound={(on) => {
            setSoundOn(on);
            savePref("sound", on);
          }}
          onLeave={leave}
          say={say}
          onClose={() => setSheet(undefined)}
        />
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
