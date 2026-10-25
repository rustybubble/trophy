import { useEffect, useMemo, useState } from "react";
import type { MockScript } from "@trophy/state-client";
import { createGame, ctl, joinDashboard, watchLink, type Session } from "./lib/api.ts";
import { useDashboard, type Source } from "./lib/useDashboard.ts";
import { AskPanel } from "./components/AskPanel.tsx";
import { CallFeed } from "./components/CallFeed.tsx";
import { CameraHealth } from "./components/CameraHealth.tsx";
import { LiveClipsPanel } from "./components/LiveClipsPanel.tsx";
import { DroidPanel } from "./components/DroidPanel.tsx";
import { JoinCard } from "./components/JoinCard.tsx";
import { Scoreboard } from "./components/Scoreboard.tsx";
import { SportWall } from "./components/SportWall.tsx";
import { VotesPanel } from "./components/VotesPanel.tsx";
import { WorldView } from "./components/WorldView.tsx";

// Only ping pong has a vision module and a rule pack; basketball exists as a labelled-synthetic script for UI work.
const SPORTS = [
  { id: "table_tennis", name: "Ping pong", live: true },
  { id: "basketball", name: "Basketball (synthetic demo only · not built)", live: false },
];

async function loadDemo(sport: string): Promise<MockScript> {
  const mod =
    sport === "basketball"
      ? await import("@trophy/state-client/fixtures/basketball-demo.json")
      : await import("@trophy/state-client/fixtures/table-tennis-demo.json");
  return mod.default as unknown as MockScript;
}

export function App() {
  const params = new URLSearchParams(location.search);
  const [session, setSession] = useState<Session>();
  const [demo, setDemo] = useState<MockScript>();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const [sport, setSport] = useState("table_tennis");
  const [ending, setEnding] = useState(false);
  const canStart = SPORTS.find((s) => s.id === sport)?.live ?? false;

  // reopen a game from the URL: /?g=<game_id>&k=<join_key>
  useEffect(() => {
    const g = params.get("g");
    const k = params.get("k");
    if (g && k) void open(() => joinDashboard(g, k));
    else if (params.get("demo")) void loadDemo(params.get("demo")!).then(setDemo);
  }, []); // once, on load

  async function open(f: () => Promise<Session>) {
    setBusy(true);
    setErr(undefined);
    try {
      const s = await f();
      history.replaceState(null, "", `/?g=${s.gameId}&k=${encodeURIComponent(s.joinKey)}`);
      setSession(s);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const source = useMemo<Source | undefined>(
    () =>
      demo
        ? { kind: "mock", script: demo }
        : session && { kind: "spacetime", uri: session.stdb.uri, module: session.stdb.module, gameId: session.gameId },
    [demo, session],
  );
  const v = useDashboard(source);

  if (!source) {
    return (
      <main className="lobby">
        <h1>Trophy</h1>
        <p className="muted">
          The AI referee for pickup games. Start a game, then scan the code with each camera phone.
        </p>
        <div className="row">
          <select value={sport} onChange={(e) => setSport(e.target.value)} aria-label="Sport">
            {SPORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button
            className="primary"
            disabled={busy || !canStart}
            title={canStart ? undefined : "Not built this weekend: watch the synthetic demo instead"}
            onClick={() =>
              void open(async () => {
                const g = await createGame(sport);
                return joinDashboard(g.game_id, g.join_key);
              })
            }
          >
            {busy ? "Starting…" : "Start a game"}
          </button>
          <button onClick={() => void loadDemo(sport).then(setDemo)}>Watch the synthetic demo</button>
        </div>
        {err && <p className="bad">Couldn't start: {err}</p>}
        <SportWall />
      </main>
    );
  }

  const teams = v.game?.teams ?? [];
  return (
    <div className="dash">
      {v.synthetic && (
        <div className="synthetic" role="status">
          {v.label && /synthetic/i.test(v.label)
            ? v.label
            : `SYNTHETIC DATA: ${v.label ?? "a scripted demo, not a real game"}`}
        </div>
      )}
      <header>
        <strong>Trophy</strong>
        <span className="muted">
          {v.game
            ? `${v.game.sport.replace("_", " ")} · ${v.game.status} · rally ${v.game.rally_no}`
            : v.ready
              ? "live state connected · waiting for the engine to publish the game"
              : "connecting…"}
        </span>
        {v.error && <span className="bad">Live state unavailable: {v.error}</span>}
        {session && v.game?.status === "live" && (
          <button
            disabled={ending}
            onClick={() => {
              setEnding(true);
              void ctl(session, "end_game").finally(() => setEnding(false));
            }}
          >
            End game
          </button>
        )}
        {session && v.game?.status === "ended" && (
          <a className="button" href={watchLink(session.gameId, session.joinKey)} target="_blank" rel="noreferrer">
            Open Trophy Watch ↗
          </a>
        )}
        <button className="ghost" onClick={() => location.assign("/")}>
          New game
        </button>
      </header>
      {session && <LiveClipsPanel session={session} />}
      <section className="grid">
        <div className="col">
          <Scoreboard scores={v.scores} teams={teams} server={v.game?.server_team_id ?? undefined} />
          <CallFeed calls={v.calls} challenges={v.challenges} cameras={v.cameras} votes={v.votes} session={session} />
        </div>
        <div className="col">
          <WorldView sport={v.game?.sport} observations={v.observations} trail={v.trail} />
          <VotesPanel calls={v.calls} votes={v.votes} />
          <AskPanel asks={v.asks} />
        </div>
        <div className="col">
          {session && <JoinCard session={session} />}
          <CameraHealth cameras={v.cameras} />
          <DroidPanel rules={v.houseRules} session={session} />
        </div>
      </section>
    </div>
  );
}
