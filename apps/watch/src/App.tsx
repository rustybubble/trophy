import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MockScript, Moment } from "@trophy/state-client";
import { joinViewer, manifest as fetchManifest, spriteUrl, type Manifest, type Session } from "./lib/api.ts";
import {
  condensed,
  highlights,
  keywordSearch,
  momentRange,
  playlistStep,
  spriteCell,
  stats as computeStats,
  type Range,
} from "./lib/moments.ts";
import { VideoTransport, VirtualTransport, gameClock, type Transport } from "./lib/playback.ts";
import { useGameData, type Source } from "./lib/useGameData.ts";
import { MomentsList } from "./components/MomentsList.tsx";
import { ReplayCard } from "./components/ReplayCard.tsx";
import { SeekBar } from "./components/SeekBar.tsx";
import { StatsPanel } from "./components/StatsPanel.tsx";
import { Table, metres, toPx } from "./components/Table.tsx";

type Mode =
  | { kind: "full" }
  | { kind: "playlist"; name: "Highlights" | "Condensed" | "Replay"; ranges: Range[]; index: number };
const RATES = [1, 0.5, 0.25];

async function loadDemo(): Promise<MockScript> {
  const mod = await import("@trophy/state-client/fixtures/table-tennis-demo.json");
  return mod.default as unknown as MockScript;
}

export function App() {
  const params = new URLSearchParams(location.search);
  const [session, setSession] = useState<Session>();
  const [demo, setDemo] = useState<MockScript>();
  const [err, setErr] = useState<string>();
  const [man, setMan] = useState<Manifest>();

  useEffect(() => {
    const g = params.get("g");
    const k = params.get("k");
    if (g && k)
      joinViewer(g, k)
        .then(async (s) => {
          setSession(s);
          setMan(await fetchManifest(s));
        })
        .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    else if (params.get("demo")) void loadDemo().then(setDemo);
  }, []); // once, on load

  const source = useMemo<Source | undefined>(
    () =>
      demo
        ? { kind: "mock", script: demo }
        : session && { kind: "spacetime", uri: session.stdb.uri, module: session.stdb.module, gameId: session.gameId },
    [demo, session],
  );
  const d = useGameData(source);

  if (!source) {
    return (
      <main className="lobby">
        <h1>Trophy Watch</h1>
        <p className="muted">
          The post-game view: recap, highlights with the Play of the game, the condensed game, every call with its
          replay, and stats. Open it from a game's link (<code>/watch/?g=…&amp;k=…</code>).
        </p>
        {err && <p className="bad">Couldn't open the game: {err}</p>}
        <a className="button" href="?demo=table_tennis">
          Watch the synthetic demo game
        </a>
      </main>
    );
  }
  return <Watch d={d} man={man} />;
}

function Watch({ d, man }: { d: ReturnType<typeof useGameData>; man?: Manifest }) {
  const cam = man?.cams[0];
  const videoRef = useRef<HTMLVideoElement>(null);
  const [transport, setTransport] = useState<Transport>();
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState(1);
  const [mode, setMode] = useState<Mode>({ kind: "full" });
  const [current, setCurrent] = useState<Moment>();
  const [tab, setTab] = useState<"moments" | "stats">("moments");
  const [q, setQ] = useState("");
  const modeRef = useRef(mode);
  modeRef.current = mode;

  // the game's time range, from the recording or else from what happened in it
  const span = useMemo(() => {
    if (cam) return { start: cam.t0_game_s, end: cam.t0_game_s + cam.duration_s };
    const ts = [...d.moments.map((m) => m.t_end_s), ...d.rallies.map((r) => r.t_end_s ?? r.t_start_s), 0];
    return { start: 0, end: Math.max(...ts) + 3 };
  }, [cam, d.moments, d.rallies]);

  useEffect(() => {
    if (!d.ready) return;
    const t =
      cam && videoRef.current
        ? new VideoTransport(videoRef.current, cam.hls_url, cam.t0_game_s, cam.duration_s)
        : new VirtualTransport(span.start, span.end);
    setTransport(t);
    const clock = gameClock(t);
    const tick = (g: number) => {
      // advance or end the playlist first, so the play state shown is the one after that
      const m = modeRef.current;
      if (m.kind === "playlist") {
        const step = playlistStep(m.ranges, m.index, g);
        if (step.index < 0) {
          t.pause();
          t.seekGame(Math.min(g, m.ranges[m.index]?.t1 ?? g));
          modeRef.current = { kind: "full" };
          setMode(modeRef.current);
        } else if (step.index !== m.index) {
          modeRef.current = { ...m, index: step.index };
          setMode(modeRef.current);
          if (step.seek != null) t.seekGame(step.seek);
        }
      }
      setNow(t.gameTime());
      setPlaying(!t.paused());
    };
    const off = clock.subscribe(tick);
    // animation frames stop in a hidden or occluded tab; the playlist still has to stop at the clip's end
    const timer = setInterval(() => tick(t.gameTime()), 250);
    return () => {
      off();
      clearInterval(timer);
      clock.stop();
      t.destroy();
    };
  }, [d.ready, cam, span.start, span.end]);

  const playRanges = useCallback(
    (name: "Highlights" | "Condensed", ranges: Range[]) => {
      if (!transport || !ranges.length) return;
      setMode({ kind: "playlist", name, ranges, index: 0 });
      transport.seekGame(ranges[0]!.t0);
      transport.play();
    },
    [transport],
  );
  const playMoment = useCallback(
    (m: Moment) => {
      if (!transport) return;
      setCurrent(m);
      setMode({ kind: "playlist", name: "Replay", ranges: [momentRange(m)], index: 0 });
      transport.seekGame(momentRange(m).t0);
      transport.play();
    },
    [transport],
  );
  const jump = useCallback(
    (dir: 1 | -1) => {
      const list =
        dir > 0
          ? d.moments.filter((m) => m.t_game_s > now + 0.5)
          : d.moments.filter((m) => m.t_game_s < now - 1.5).reverse();
      if (list[0]) playMoment(list[0]);
    },
    [d.moments, now, playMoment],
  );

  // which moment the card shows: the playlist's, or during full-game playback the one at the playhead
  useEffect(() => {
    const listed = mode.kind === "playlist" ? mode.ranges[mode.index]?.momentId : undefined;
    const next = listed
      ? d.moments.find((m) => m.moment_id === listed)
      : mode.kind === "full" && playing
        ? d.moments.find((m) => now >= m.t_start_s && now <= m.t_end_s + 1)
        : undefined;
    if (next && next.moment_id !== current?.moment_id) setCurrent(next);
  }, [now, d.moments, current, mode, playing]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!transport || (e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === " ") {
        e.preventDefault();
        if (transport.paused()) transport.play();
        else transport.pause();
      } else if (e.key === "ArrowLeft") transport.seekGame(transport.gameTime() - 5);
      else if (e.key === "ArrowRight") transport.seekGame(transport.gameTime() + 5);
      else if (e.key === "j" || e.key === "J") jump(-1);
      else if (e.key === "l" || e.key === "L") jump(1);
      else if (e.key === "s" || e.key === "S") {
        const r = RATES[(RATES.indexOf(transport.rate()) + 1) % RATES.length]!;
        transport.setRate(r);
        setRateState(r);
      } else if (e.key === ",") transport.step(-1);
      else if (e.key === ".") transport.step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [transport, jump]);

  const teams = d.game?.teams ?? [];
  const best = d.moments.find((m) => m.is_best_play);
  const stats = useMemo(
    () =>
      computeStats(
        teams.map((t) => t.team_id),
        d.calls,
        d.rallies,
        d.observations,
      ),
    [teams, d.calls, d.rallies, d.observations],
  );
  const hits = q ? keywordSearch(d.moments, q) : [];
  const call = current?.call_id ? d.calls.find((c) => c.id === current.call_id) : undefined;
  const final = d.scores.length
    ? teams.map((t) => d.scores.find((s) => s.team_id === t.team_id)?.points ?? 0).join("–")
    : "–";
  const bestThumb = best && cam ? spriteCell(cam.sprite, best.thumb_t_s - cam.t0_game_s) : undefined;

  return (
    <div className="watch">
      {d.synthetic && (
        <div className="synthetic" role="status">
          {d.label && /synthetic/i.test(d.label)
            ? d.label
            : `SYNTHETIC DATA: ${d.label ?? "a scripted demo, not a real game"}`}
        </div>
      )}
      <header className="recap">
        <div>
          <div className="muted small">
            {d.game
              ? `${d.game.sport.replace("_", " ")} · ${d.game.status}`
              : d.ready
                ? "game state not published yet (no engine running)"
                : "loading…"}
          </div>
          <div className="final">
            {teams.map((t, i) => (
              <span key={t.team_id} style={{ color: t.color }}>
                {i ? " " : ""}
                {t.name}
              </span>
            ))}
            <strong> {final}</strong>
          </div>
          {best && (
            <button className="hero" onClick={() => playMoment(best)}>
              {bestThumb && cam && (
                <span
                  className="sprite"
                  style={{
                    backgroundImage: `url(${spriteUrl(cam, bestThumb.sheet)})`,
                    backgroundPosition: `-${bestThumb.x}px -${bestThumb.y}px`,
                    width: cam.sprite.w,
                    height: cam.sprite.h,
                  }}
                />
              )}
              <span>
                ★ Play of the game: {best.label}
                <span className="muted small"> · {best.reasons.join(" · ")}</span>
              </span>
            </button>
          )}
        </div>
        <div className="ways">
          <button
            className="primary"
            onClick={() => {
              setMode({ kind: "full" });
              transport?.seekGame(span.start);
              transport?.play();
            }}
          >
            Play full game
          </button>
          <button
            disabled={!d.moments.length}
            onClick={() => playRanges("Highlights", highlights(d.moments).map(momentRange))}
          >
            Highlights
          </button>
          <button disabled={!d.rallies.length} onClick={() => playRanges("Condensed", condensed(d.rallies))}>
            Condensed
          </button>
          <button onClick={() => setTab("stats")}>Stats</button>
        </div>
      </header>

      <section className="main">
        <div className="col wide">
          <div className="stage">
            {cam ? (
              <video ref={videoRef} playsInline muted className="video" />
            ) : (
              <div className="novideo">
                <Table label="Reconstructed top-down view">
                  <Reconstruction now={now} d={d} />
                </Table>
                <div className="badge">no recording for this game · reconstructed from tracking, not video</div>
              </div>
            )}
            {mode.kind === "playlist" && (
              <div className="playlist-bug">
                {mode.name} {mode.index + 1}/{mode.ranges.length}: {mode.ranges[mode.index]?.label}
              </div>
            )}
          </div>
          <SeekBar
            start={span.start}
            end={span.end}
            now={now}
            moments={d.moments}
            cam={cam}
            onSeek={(t) => transport?.seekGame(t)}
          />
          <div className="controls">
            <button onClick={() => (transport?.paused() ? transport.play() : transport?.pause())}>
              {playing ? "Pause" : "Play"}
            </button>
            <button onClick={() => jump(-1)} title="J">
              ◀ Moment
            </button>
            <button onClick={() => jump(1)} title="L">
              Moment ▶
            </button>
            <button onClick={() => transport?.step(-1)} title=",">
              ◀ frame
            </button>
            <button onClick={() => transport?.step(1)} title=".">
              frame ▶
            </button>
            {RATES.map((r) => (
              <button
                key={r}
                className={r === rate ? "chip on" : "chip"}
                onClick={() => {
                  transport?.setRate(r);
                  setRateState(r);
                }}
              >
                {r}×
              </button>
            ))}
            <span className="muted small keys">Space · ←/→ 5 s · J/L moments · S slow-mo · , . frames</span>
          </div>
          <ReplayCard
            moment={current}
            call={call}
            votes={d.votes}
            observations={d.observations}
            commentary={d.commentary}
          />
        </div>
        <div className="col">
          <div className="panel">
            <input
              className="search"
              placeholder="Search the game: “every edge ball”, “serve faults by side B”…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            {q && (
              <>
                <div className="muted small">Keyword search (Moss semantic search isn't connected yet)</div>
                {!hits.length && <p className="muted small">No matching moments.</p>}
                <ul className="hits">
                  {hits.map((m) => (
                    <li key={m.moment_id}>
                      <button className="link" onClick={() => playMoment(m)}>
                        {m.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
          <div className="tabs">
            <button className={tab === "moments" ? "chip on" : "chip"} onClick={() => setTab("moments")}>
              Moments
            </button>
            <button className={tab === "stats" ? "chip on" : "chip"} onClick={() => setTab("stats")}>
              Stats
            </button>
          </div>
          {tab === "moments" ? (
            <MomentsList
              moments={d.moments}
              observations={d.observations}
              start={span.start}
              current={current?.moment_id}
              onPlay={playMoment}
            />
          ) : (
            <StatsPanel stats={stats} teams={teams} />
          )}
        </div>
      </section>
    </div>
  );
}

/** The ball's last second and this rally's bounces, at the playhead (no-video games). */
function Reconstruction({ now, d }: { now: number; d: ReturnType<typeof useGameData> }) {
  const trail = d.trail
    .filter((s) => s.object === "ball" && s.pos_m && s.t_game_s <= now && s.t_game_s > now - 1)
    .sort((a, b) => a.t_game_s - b.t_game_s);
  const path = trail
    .map((s, i) => {
      const [x, y] = toPx(s.pos_m![0], s.pos_m![1]);
      return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const rally = d.rallies.find((r) => now >= r.t_start_s && now <= (r.t_end_s ?? Infinity) + 1);
  const bounces = rally
    ? d.observations.filter((o) => o.type === "bounce" && o.pos_m && o.t_game_s >= rally.t_start_s && o.t_game_s <= now)
    : [];
  const ball = trail[trail.length - 1];
  return (
    <>
      {path && <path d={path} className="trail" />}
      {bounces.map((o) => {
        const [x, y] = toPx(o.pos_m!.x, o.pos_m!.y);
        return <circle key={o.id} cx={x} cy={y} r={Math.max(4, metres(o.sigma_m ?? 0.02))} className="bounce" />;
      })}
      {ball &&
        (() => {
          const [x, y] = toPx(ball.pos_m![0], ball.pos_m![1]);
          return <circle cx={x} cy={y} r={6} className="ball" />;
        })()}
    </>
  );
}
