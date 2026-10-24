import { useEffect, useMemo, useRef, useState } from "react";
import type { MockScript } from "@trophy/state-client";
import { Api, forgetSession, type AskAnswer, type Session } from "../lib/api.ts";
import { beep, startOnsets } from "../lib/audio.ts";
import { fakeCamera, openRearCamera, type CameraInfo } from "../lib/camera.ts";
import { CtlSocket, type SyncState } from "../lib/ctl.ts";
import { parseIntent } from "../lib/intent.ts";
import { FrameStreamer, type StreamStats } from "../lib/streamer.ts";
import { useGame } from "../lib/useGame.ts";
import { Voice } from "../lib/voice.ts";
import { CalibrateView } from "./CalibrateView.tsx";
import { JudgePanel } from "./JudgePanel.tsx";
import { PushToTalk } from "./PushToTalk.tsx";
import { Scoreboard } from "./Scoreboard.tsx";

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

export function LiveView({ session, mock, onLeave }: { session: Session; mock?: MockScript; onLeave?: () => void }) {
  const roles = useMemo(() => new Set(session.role.split(",")), [session.role]);
  const isCam = roles.has("cam") && !mock;
  const isJudge = roles.has("judge");
  const api = useMemo(() => new Api(session), [session]);
  const voice = useMemo(() => (mock ? undefined : new Voice(api)), [api, mock]);
  const [sync, setSync] = useState<SyncState>({ connected: false, offsetMs: null, syncErrMs: null });
  const ctl = useMemo(() => (mock ? undefined : new CtlSocket(api.wsUrl("ctl"), setSync)), [api, mock]);
  const [speakOn, setSpeakOn] = useState(() => pref("speak", true));
  const [readAll, setReadAll] = useState(() => pref("readall", false));
  const [stats, setStats] = useState<StreamStats>();
  const [cam, setCam] = useState<CameraInfo>();
  const [onsets, setOnsets] = useState(0);
  const [toast, setToast] = useState<string>();
  const [answer, setAnswer] = useState<{ q: string; a?: AskAnswer; err?: string }>();
  const [calibrating, setCalibrating] = useState(false);
  const [calibratedHere, setCalibratedHere] = useState(false);
  const [sheet, setSheet] = useState<"menu" | "judge" | "stats" | undefined>(
    params.get("test") === "1" ? "stats" : undefined,
  );
  const [hiddenGuide, setHiddenGuide] = useState<string>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const g = useGame(session, { voice, ctl, readEverything: readAll, mock });

  useEffect(() => {
    if (voice) voice.enabled = speakOn;
  }, [voice, speakOn]);

  const say = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast((t) => (t === msg ? undefined : t)), 4000);
  };

  // control socket (clock sync) + screen wake lock
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
  }, [ctl, voice]);

  // camera -> frames WS, plus onsets on the raw mic
  useEffect(() => {
    if (!isCam) return;
    let streamer: FrameStreamer | undefined;
    let stopOnsets: (() => void) | undefined;
    let stopped = false;
    (async () => {
      try {
        const info =
          params.get("fake") === "1"
            ? fakeCamera()
            : await openRearCamera(session.frame.w, session.frame.h, session.frame.fps);
        if (stopped) return;
        setCam(info);
        const v = videoRef.current!;
        v.srcObject = info.stream;
        await v.play();
        streamer = new FrameStreamer(v, api.wsUrl("frames"), session.frame.quality, setStats);
        streamer.start();
        try {
          stopOnsets = await startOnsets((t, peak, energy) => {
            ctl?.onset(t, peak, energy);
            setOnsets((n) => n + 1);
          });
        } catch {
          say("Microphone unavailable: no audio onsets");
        }
      } catch (e) {
        say(`Camera: ${e instanceof Error ? e.message : String(e)}`);
      }
    })();
    return () => {
      stopped = true;
      streamer?.stop();
      stopOnsets?.();
      (videoRef.current?.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
    };
  }, [isCam, api, ctl, session.frame]);

  // health every 5 s
  useEffect(() => {
    if (!ctl || !isCam) return;
    const id = setInterval(() => {
      if (stats) ctl.health({ fps: Math.round(stats.sentFps * 10) / 10, w: stats.w, h: stats.h });
    }, 5000);
    return () => clearInterval(id);
  }, [ctl, isCam, stats]);

  const latestChallengeable = g.calls.find((c) => c.tier === "BETA" && c.status === "final" && c.kind !== "info");

  const run = async (label: string, f: () => Promise<unknown>) => {
    try {
      await f();
    } catch (e) {
      say(`${label}: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const challenge = () =>
    run("Challenge", async () => {
      if (!latestChallengeable) {
        say("No challengeable call");
        return;
      }
      await api.ctl("challenge", { call_id: latestChallengeable.id });
      beep("double");
      void voice?.speak("Challenge. Let's look at the replay.", { voice: "ref", interrupt: true });
    });

  const onTranscript = async (text: string) => {
    const intent = parseIntent(text);
    switch (intent.kind) {
      case "none":
        return;
      case "challenge":
        return challenge();
      case "undo":
        if (!isJudge) return void voice?.speak("Only the judge can undo a call.", { voice: "ref" });
        return run("Undo", () => api.ctl("undo_last_call"));
      case "score": {
        const line = g.scores.length
          ? `${g.scores.map((s) => `${s.team_id} ${s.points}`).join(", ")}.`
          : "No score yet.";
        return void voice?.speak(line, { voice: "ref" });
      }
      case "house_rule":
        if (!isJudge) return void voice?.speak("Only the judge can add house rules.", { voice: "ref" });
        await run("House rule", () => api.ctl("submit_house_rule", { text: intent.text, source: "voice" }));
        return void voice?.speak("House rule sent to the rule compiler.", { voice: "ref" });
      case "ask":
        setAnswer({ q: intent.question });
        try {
          const a = await api.ask(intent.question);
          setAnswer({ q: intent.question, a });
          void voice?.speak(a.speech || a.answer, { voice: "ref", interrupt: true });
        } catch (e) {
          setAnswer({ q: intent.question, err: e instanceof Error ? e.message : String(e) });
        }
    }
  };

  const flashColor = g.flash
    ? (g.game?.teams.find((t) => t.team_id === g.flash)?.color ?? (g.flash.startsWith("#") ? g.flash : "#f59e0b"))
    : undefined;

  // what this phone should do next, in plain words
  const me = g.cameras.find((c) => c.cam_id === session.camId);
  const tableSet = calibratedHere || !!me?.calibration;
  const needsDecision = g.challenges.some((c) => c.status === "open") || g.houseRules.some((h) => h.status === "ready");
  let guide: { title: string; body?: string; action?: { label: string; run: () => void } } | undefined;
  if (!mock && !sync.connected) {
    guide = {
      title: "Connecting to the referee…",
      body: "This phone must be on the same Wi-Fi as the referee laptop.",
    };
  } else if (isCam && !stats?.connected) {
    guide = { title: "Starting the camera…", body: "Allow camera and microphone access if asked." };
  } else if (isCam && !tableSet) {
    guide = {
      title: "Set up the table",
      body: "Turn the phone sideways at the net line, about 2 m back, with the whole table in view. Then mark its corners.",
      action: { label: "Set up table", run: () => setCalibrating(true) },
    };
  } else if (g.game?.status === "lobby") {
    guide = isJudge
      ? {
          title: "Ready to play",
          action: {
            label: "Start game",
            run: () => void run("Start", () => api.ctl("start_game", { first_server: "A" })),
          },
        }
      : { title: "Ready to play", body: "Waiting for the judge to start the game." };
  }
  if (guide && hiddenGuide === guide.title) guide = undefined;

  const status = mock
    ? { cls: "ok", text: "Demo" }
    : !sync.connected
      ? { cls: "bad", text: "Offline" }
      : isCam && stats
        ? { cls: stats.sentFps >= 25 ? "ok" : "warn", text: `Live · ${stats.sentFps.toFixed(0)} fps` }
        : { cls: "ok", text: "Live" };

  const leave = () => {
    forgetSession(session.gameId);
    onLeave?.();
  };

  return (
    <div className={isCam ? "live cam" : "live"}>
      {isCam && <video ref={videoRef} className="preview" muted playsInline autoPlay />}

      <header className="top">
        <Scoreboard game={g.game} scores={g.scores} compact />
        <button className={`status ${status.cls}`} onClick={() => setSheet("stats")} aria-label="Connection details">
          <span className="dot" /> {status.text}
        </button>
      </header>
      {g.synthetic && <div className="synthetic">{g.label ?? "SYNTHETIC demo data"}</div>}

      {!isCam && (
        <section className="board">
          <Scoreboard game={g.game} scores={g.scores} />
          <ol className="feed" aria-label="Recent calls">
            {g.calls.slice(0, 4).map((c) => (
              <li key={c.id} className={`tier-${c.tier.toLowerCase()}`}>
                <span className="tier">{c.tier === "PLAYERS" ? "PLAYERS" : c.tier}</span> {c.text}
                {c.status !== "final" && <em> · {c.status}</em>}
              </li>
            ))}
          </ol>
        </section>
      )}

      {guide && !g.banner && (
        <div className="guide" role="status">
          <strong>{guide.title}</strong>
          {guide.body && <p>{guide.body}</p>}
          <div className="row">
            {guide.action && (
              <button className="primary" onClick={guide.action.run}>
                {guide.action.label}
              </button>
            )}
            <button className="ghost" onClick={() => setHiddenGuide(guide.title)}>
              Hide
            </button>
          </div>
        </div>
      )}

      {g.banner && (
        <div className={`banner tier-${g.banner.tier.toLowerCase()}`} role="status" aria-live="assertive">
          <span className="tier">{g.banner.tier === "PLAYERS" ? "PLAYERS DECIDE" : g.banner.tier}</span>
          <span className="text">{g.banner.text}</span>
          {g.banner.tier !== "AUTO" && <span className="p">{Math.round(g.banner.p * 100)}% sure</span>}
        </div>
      )}

      {flashColor && <div className="flash" style={{ background: flashColor }} />}

      <footer className="bottom">
        {!mock ? <PushToTalk voice={voice} onTranscript={onTranscript} onError={say} /> : <span />}
        {latestChallengeable ? (
          <button className="challenge" onClick={() => void challenge()}>
            Challenge · {Math.round(latestChallengeable.p * 100)}%
          </button>
        ) : (
          <span />
        )}
        <button className="menu-btn" aria-label="Menu" onClick={() => setSheet("menu")}>
          ☰ Menu
        </button>
      </footer>

      {answer && (
        <aside className="answer" aria-live="polite">
          <button className="close" aria-label="Close" onClick={() => setAnswer(undefined)}>
            ×
          </button>
          <p className="q">“{answer.q}”</p>
          {answer.err ? (
            <p className="error">{answer.err}</p>
          ) : answer.a ? (
            <>
              <p>{answer.a.answer}</p>
              <ul className="cites">
                {answer.a.citations.map((c) => (
                  <li key={c.rule_id}>
                    <strong>{c.rule_id}</strong> {c.title}: “{c.quote}”
                  </li>
                ))}
              </ul>
              <p className="muted small">
                {answer.a.latency_ms.toFixed(0)} ms
                {answer.a.moss_ms !== undefined ? ` · Moss ${answer.a.moss_ms.toFixed(0)} ms` : ""}
              </p>
            </>
          ) : (
            <p className="muted">Looking it up…</p>
          )}
        </aside>
      )}

      {sheet === "menu" && (
        <div className="sheet-wrap" onClick={() => setSheet(undefined)}>
          <nav className="sheet" aria-label="Menu" onClick={(e) => e.stopPropagation()}>
            {isCam && (
              <button
                onClick={() => {
                  setSheet(undefined);
                  setCalibrating(true);
                }}
              >
                Set up table{tableSet ? " (done)" : ""}
              </button>
            )}
            {isJudge && <button onClick={() => setSheet("judge")}>Judge controls</button>}
            <label className="toggle">
              <input
                type="checkbox"
                checked={speakOn}
                onChange={(e) => {
                  setSpeakOn(e.target.checked);
                  savePref("speak", e.target.checked);
                }}
              />
              Speak calls out loud
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={readAll}
                onChange={(e) => {
                  setReadAll(e.target.checked);
                  savePref("readall", e.target.checked);
                }}
              />
              Also read every score change
            </label>
            <button onClick={() => setSheet("stats")}>Connection details</button>
            {onLeave && (
              <button className="ghost" onClick={leave}>
                Leave game
              </button>
            )}
            <p className="muted small">
              Hold to talk: say “challenge”, “undo”, “house rule: …”, or ask a rules question.
            </p>
          </nav>
        </div>
      )}

      {isJudge && (sheet === "judge" || needsDecision) && (
        <JudgePanel api={mock ? undefined : api} g={g} onError={say} onClose={() => setSheet(undefined)} />
      )}

      {sheet === "stats" && (
        <div className="sheet-wrap" onClick={() => setSheet(undefined)}>
          <aside className="sheet stats mono small" onClick={(e) => e.stopPropagation()}>
            <div>camera: {cam ? cam.label : "—"}</div>
            {stats && (
              <div>
                sending {stats.sentFps.toFixed(1)} fps · {stats.w}×{stats.h} · encode {stats.encodeMs.toFixed(1)} ms ·{" "}
                {stats.kbPerFrame.toFixed(0)} KB/frame · skipped {stats.skipped}
              </div>
            )}
            <div>
              clock: offset {sync.offsetMs?.toFixed(1) ?? "—"} ms · error ±{sync.syncErrMs?.toFixed(1) ?? "—"} ms ·
              sound onsets {onsets}
            </div>
            <div>
              {session.role} · {session.camId} · {session.gameId}
            </div>
            {g.error && <div className="error">state: {g.error}</div>}
            <div className="row">
              <button onClick={() => beep("short")}>Beep</button>
              <button
                onClick={() =>
                  void voice
                    ?.speak("Edge ball. Good. Point, B.", { voice: "calls", interrupt: true })
                    .then((ms) => say(`First audio after ${ms.toFixed(0)} ms`))
                }
              >
                Test voice
              </button>
              <button className="ghost" onClick={() => setSheet(undefined)}>
                Close
              </button>
            </div>
          </aside>
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}
      {isCam && <div className="rotate">Turn the phone sideways (landscape)</div>}
      {calibrating && (
        <CalibrateView
          api={api}
          sport={g.game?.sport ?? "table_tennis"}
          onClose={(ok) => {
            setCalibrating(false);
            if (ok) setCalibratedHere(true);
          }}
        />
      )}
    </div>
  );
}
